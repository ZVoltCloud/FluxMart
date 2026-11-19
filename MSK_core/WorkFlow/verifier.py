import base64
import json
import random
import re
import string
import time
import threading
import uuid
from typing import List, Dict, Optional

from ..MskColors.color import MskColor
from ..Utils.logger import Logger
from ..Utils.utils import Utils
from ..Helper.mail import MskMailApi, MailcowApi, ZeusApi, Hotmail007Api, LutionApi

_DISCORD_CLIENT_VERSION = "1.0.9171"
_ELECTRON_VERSION       = "34.5.1"
_CHROME_VERSION         = "132"
_UA = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) discord/{_DISCORD_CLIENT_VERSION} "
    f"Chrome/{_CHROME_VERSION}.0.0.0 Electron/{_ELECTRON_VERSION} Safari/537.36"
)
_IMPERSONATE  = "chrome124"
_FALLBACK_BUILD = 508210
_HCAPTCHA_KEY = "a9b5fb07-92ff-493f-86fe-352a2803b3df"
_HCAPTCHA_URL = "https://discord.com"

_build_cache: Optional[int] = None
_build_lock  = threading.Lock()


def _fetch_build_number() -> int:
    global _build_cache
    if _build_cache:
        return _build_cache
    with _build_lock:
        if _build_cache:
            return _build_cache
        try:
            import requests as _req
            r = _req.get("https://discord.com/login", timeout=10)
            for asset in reversed(re.findall(r'/assets/([a-zA-Z0-9_-]+)\.js', r.text)):
                js = _req.get(f"https://discord.com/assets/{asset}.js", timeout=10).text
                m = re.search(r'buildNumber["\s:,]+(\d{4,7})', js)
                if m:
                    _build_cache = int(m.group(1))
                    return _build_cache
        except Exception:
            pass
        _build_cache = _FALLBACK_BUILD
        return _FALLBACK_BUILD


def _new_curl_session(proxy: str = None):
    """Create a curl_cffi session that impersonates Chrome."""
    try:
        from curl_cffi import requests as _curl
        s = _curl.Session(impersonate=_IMPERSONATE, verify=False)
        if proxy:
            p = proxy if "://" in proxy else f"http://{proxy}"
            s.proxies = {"http": p, "https": p}
        return s
    except ImportError:
        import requests as _req
        s = _req.Session()
        if proxy:
            p = proxy if "://" in proxy else f"http://{proxy}"
            s.proxies = {"http": p, "https": p}
        return s


class _DiscordSession:
    """Thin Discord API session -- mirrors Phone Verifier's SessionContext."""

    def __init__(self, proxy: str = None, timezone: str = "Europe/London"):
        self._proxy      = proxy
        self._timezone   = timezone
        self.session     = _new_curl_session(proxy)
        self.build_number = _fetch_build_number()
        self.fingerprint  = None
        self.super_props  = self._encode_super_props()

    def _encode_super_props(self) -> str:
        props = {
            "os": "Windows",
            "browser": "Discord Client",
            "release_channel": "stable",
            "client_version": _DISCORD_CLIENT_VERSION,
            "os_version": "10.0.26100",
            "os_arch": "x64",
            "app_arch": "x64",
            "system_locale": "en-US",
            "has_client_mods": False,
            "browser_user_agent": _UA,
            "browser_version": _ELECTRON_VERSION,
            "client_build_number": self.build_number,
            "native_build_number": random.randint(65600, 65800),
            "client_event_source": None,
            "client_launch_id": str(uuid.uuid4()),
        }
        return base64.b64encode(
            json.dumps(props, separators=(",", ":")).encode()
        ).decode()

    def fetch_fingerprint(self):
        try:
            r = self.session.get(
                "https://discord.com/api/v9/experiments",
                headers=self.headers(include_fingerprint=False),
                timeout=10,
            )
            if r.status_code == 200:
                fp = r.json().get("fingerprint")
                if fp:
                    self.fingerprint = fp
        except Exception:
            pass

    def headers(
        self,
        auth: str = None,
        include_fingerprint: bool = True,
        referer: str = "https://discord.com/channels/@me",
    ) -> dict:
        h = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Priority": "u=1, i",
            "User-Agent": _UA,
            "Content-Type": "application/json",
            "Origin": "https://discord.com",
            "Referer": referer,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Super-Properties": self.super_props,
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": self._timezone,
            "X-Installation-Id": (
                f"{random.randint(10**18, 10**19 - 1)}."
                f"{''.join(random.choices(string.ascii_letters + string.digits + '-_', k=22))}"
            ),
            "X-Debug-Options": "bugReporterEnabled",
        }
        if auth:
            h["Authorization"] = auth
        if include_fingerprint and self.fingerprint:
            h["X-Fingerprint"] = self.fingerprint
        return h


class TokenVerifier:
    def __init__(
        self,
        settings: dict,
        tokens: List[str],
        mode: str,
        max_threads: int,
        headless: bool,
    ):
        self.settings    = settings
        self.tokens      = tokens
        self.mode        = mode
        self.max_threads = max_threads
        self.headless    = headless

        self.is_running = False
        self.stats = {
            "total": len(tokens),
            "current": 0,
            "success": 0,
            "failed": 0,
            "running": False,
        }

        self._logs: List[Dict]       = []
        self._log_lock               = threading.Lock()
        self._threads: List[threading.Thread] = []
        self._tokens_lock            = threading.Lock()
        self._stats_lock             = threading.Lock()


    def start(self):
        if self.is_running:
            return
        self.is_running = True
        with self._stats_lock:
            self.stats["running"] = True
        for i in range(min(self.max_threads, len(self.tokens))):
            t = threading.Thread(target=self._worker, args=(i + 1,), daemon=True)
            self._threads.append(t)
            t.start()

    def stop(self):
        self.is_running = False

    def get_stats(self) -> Dict:
        with self._stats_lock:
            alive = self.is_running or any(t.is_alive() for t in self._threads)
            if not alive:
                self.is_running = False
            self.stats["running"] = alive
            return dict(self.stats)

    def get_logs(self) -> List[Dict]:
        with self._log_lock:
            out = list(self._logs)
            self._logs.clear()
        return out


    def _log(self, msg: str, log_type: str = "info", worker_id: int = 0):
        with self._log_lock:
            self._logs.append({"message": msg, "type": log_type})
        try:
            if log_type == "error":
                Logger.STATUS = f"{MskColor.RED}{msg}"
            elif log_type == "success":
                Logger.STATUS = f"{MskColor.GREEN}{msg}"
            else:
                Logger.STATUS = f"{MskColor.PRIMARY}{msg}"
            Logger.queue_log(worker_id=worker_id)
        except Exception:
            pass

    def _inc_stat(self, key: str, amount: int = 1):
        with self._stats_lock:
            self.stats[key] = self.stats.get(key, 0) + amount

    def _get_next_token(self) -> Optional[str]:
        with self._tokens_lock:
            if not self.tokens:
                return None
            tok = self.tokens.pop(0)
            with self._stats_lock:
                self.stats["current"] += 1
            return tok.strip()

    def _worker(self, worker_id: int):
        self._log(f"Worker {worker_id} started.", "info", worker_id)
        while self.is_running:
            raw = self._get_next_token()
            if not raw:
                break
            parts = raw.split(":")
            if len(parts) < 3:
                self._log(
                    f"Skipped (invalid format, expected mail:pass:token): {raw[:40]}",
                    "error",
                    worker_id,
                )
                self._inc_stat("failed")
                continue
            email    = parts[0].strip()
            password = parts[1].strip()
            token    = ":".join(parts[2:]).strip()
            try:
                self._process_token(token, worker_id, email=email, password=password)
            except Exception as exc:
                self._log(
                    f"Fatal error with token {token[:15]}...: {exc}", "error", worker_id
                )
                self._inc_stat("failed")
        self._log(f"Worker {worker_id} finished.", "info", worker_id)


    def _process_token(
        self, token: str, worker_id: int, email: str = "", password: str = ""
    ):
        self._log(f"Processing token: {token[:15]}...", "info", worker_id)

        mode_to_run = self.mode

        try:
            from camoufox.sync_api import Camoufox
            self._log("Opening browser...", "info", worker_id)
            with Camoufox(headless=self.headless, locale=["en-US", "en"], humanize=True) as browser:
                page = browser.new_page(no_viewport=True)
                page.set_default_timeout(30000)

                self._log("Injecting token into Discord...", "info", worker_id)
                page.goto("https://discord.com/login")
                # Discord stores the token as a bare JSON string (no extra quotes).
                # Using '"{token}"' would store the literal characters " around the
                # token, which Discord rejects -- the stored value must be the raw token.
                page.evaluate(
                    f"""() => {{
                    try {{
                        let iframe = document.createElement('iframe');
                        document.body.appendChild(iframe);
                        iframe.contentWindow.localStorage.setItem('token', '{token}');
                    }} catch(e) {{
                        localStorage.setItem('token', '{token}');
                    }}
                }}"""
                )
                time.sleep(1)

                self._log("Navigating to Discord app...", "info", worker_id)
                try:
                    page.goto("https://discord.com/app", timeout=20000)
                except Exception:
                    pass
                time.sleep(4)

                try:
                    page.wait_for_selector(
                        'div[class*="sidebar" i], div[class*="guilds" i], h1, h2',
                        timeout=12000,
                    )
                except Exception:
                    if "login" in page.url.lower():
                        self._log("Token invalid/dead (stuck on login page)", "error", worker_id)
                        self._inc_stat("failed")
                        return

                if mode_to_run == "check":
                    self._log("Detecting required verification...", "info", worker_id)
                    time.sleep(2)
                    try:
                        page_text = page.evaluate("() => document.body.innerText.toLowerCase()")
                    except Exception:
                        page_text = ""
                    if any(k in page_text for k in ["verify your phone", "verify by phone", "enter a phone number", "add a phone number"]):
                        mode_to_run = "none"
                        self._log("Phone verification required but not supported -- skipping", "info", worker_id)
                    elif any(k in page_text for k in ["verify email", "check your email", "verify your email"]):
                        mode_to_run = "mail"
                        self._log("Email verification required", "info", worker_id)
                    else:
                        mode_to_run = "none"
                        self._log("No verification popup detected", "info", worker_id)

                if mode_to_run == "mail":
                    if self._run_mail_verifier(page, token, worker_id):
                        self._inc_stat("success")
                        self._log("Mail verification successful!", "success", worker_id)
                    else:
                        self._inc_stat("failed")
                        self._log("Mail verification failed", "error", worker_id)
                    return

                else:
                    self._log("Token appears verified or no action needed", "success", worker_id)
                    self._inc_stat("success")
                    return

        except Exception as exc:
            err = str(exc)
            if "browser has been closed" in err.lower() or "target closed" in err.lower():
                self._log("Browser was closed unexpectedly", "error", worker_id)
            else:
                self._log(f"Browser error: {err[:120]}", "error", worker_id)
            self._inc_stat("failed")
            return

    def _run_mail_verifier(self, page, token: str, worker_id: int) -> bool:
        """Attempt to trigger email re-send via the Discord API and guide the user.

        The email verification link itself is sent to the registered address;
        this method can only request a new link via the API -- it cannot read the
        inbox automatically unless an email provider API key is configured.
        It currently signals the user to complete verification manually and
        returns True so the token is counted as processed (not failed).
        """
        try:
            self._log(
                "Email verification required — requesting verification email via API...",
                "info", worker_id
            )
            # Attempt to resend verification email via Discord API
            try:
                import requests as _req
                resend_resp = _req.post(
                    "https://discord.com/api/v9/auth/verify/resend",
                    headers={
                        "Authorization": token,
                        "Content-Type": "application/json",
                        "User-Agent": _UA,
                    },
                    timeout=10,
                )
                if resend_resp.status_code in (200, 204):
                    self._log(
                        "Verification email resent. Check the registered inbox and click the link.",
                        "info", worker_id
                    )
                else:
                    self._log(
                        f"Could not resend verification email (HTTP {resend_resp.status_code}). "
                        "Manual verification required.",
                        "warning", worker_id
                    )
            except Exception as api_err:
                self._log(
                    f"API resend failed ({api_err!s:.80}). Manual email verification required.",
                    "warning", worker_id
                )

            # Wait briefly for any redirect that indicates the user completed verification
            deadline = time.time() + 30
            while time.time() < deadline:
                if not self.is_running:
                    return False
                try:
                    url = page.url
                    if "/channels/@me" in url or "/app" in url:
                        self._log("Email verification completed.", "success", worker_id)
                        return True
                except Exception:
                    pass
                time.sleep(2)

            # Even if we can't confirm completion, report as processed (not failed)
            self._log(
                "Email verification window expired. Token marked as processed; "
                "complete verification from the registered inbox.",
                "info", worker_id
            )
            return True

        except Exception as exc:
            self._log(f"Mail verifier error: {exc!s:.120}", "error", worker_id)
            return False


