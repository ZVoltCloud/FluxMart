"""
Discord Account Humanizer – 2026 Undetected Method
===================================================
Uses primp (Chrome TLS fingerprint) + Discord Gateway WebSocket session
to authenticate and update Discord profiles without triggering
"Unknown Session" (code 10020) errors.

Key anti-detection layers:
  1. Dynamic build number (fetched live via primp)
  2. Discord Gateway WebSocket IDENTIFY + heartbeat (active session)
  3. primp Chrome TLS fingerprint (browser-grade TLS)
  4. Discord Desktop Client identity (Electron 34.5.1 / Chrome 132)
  5. Randomized human-like delays between requests
  6. Proper header ordering matching real client requests
  7. Retry logic with rate-limit handling
"""

import io
import sys
import os
import re
import time
import uuid
import json
import base64
import random
import threading
import logging
import websocket
try:
    import inspect as _ws_insp
    _ws_required = [
        n for n, p in _ws_insp.signature(websocket.WebSocket.__init__).parameters.items()
        if n != 'self' and p.default is _ws_insp.Parameter.empty
    ]
    if _ws_required:
        from websocket._core import WebSocket as _RealWsClient
        websocket.WebSocket = _RealWsClient
    del _ws_insp, _ws_required
except Exception:
    pass
from pathlib import Path
from typing import Optional, List, Dict

import primp
from PIL import Image

from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Utils.utils import Config

log = logging.getLogger(__name__)


def _is_frozen() -> bool:
    if getattr(sys, 'frozen', False):
        return True
    try:
        return bool(__compiled__)
    except NameError:
        pass
    exe_name = os.path.basename(sys.executable).lower()
    if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw',
                         'python3.exe', 'python3'):
        return True
    return False


def get_base_path() -> str:
    if _is_frozen():
        _candidates = []
        try:
            _candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
        except Exception:
            pass
        try:
            _candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
        except Exception:
            pass
        try:
            _candidates.append(os.getcwd())
        except Exception:
            pass
        _extended = []
        for _c in _candidates:
            _cur = _c
            for _ in range(4):
                if _cur not in _extended:
                    _extended.append(_cur)
                _parent = os.path.dirname(_cur)
                if _parent == _cur:
                    break
                _cur = _parent
        for _d in _extended:
            if os.path.isdir(os.path.join(_d, 'data')):
                return _d
        if _extended:
            return _extended[0]
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_resource_path(relative_path: str) -> str:
    return os.path.join(get_base_path(), relative_path)


DISCORD_CLIENT_VERSION = "1.0.9171"
ELECTRON_VERSION       = "34.5.1"
CHROME_VERSION_ELECTRON = "132"
_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) discord/{DISCORD_CLIENT_VERSION} "
    f"Chrome/{CHROME_VERSION_ELECTRON}.0.0.0 Electron/{ELECTRON_VERSION} Safari/537.36"
)

_HUMANIZER_RETRY_LIMIT = 1
_HUMANIZER_BUILD_CACHE = None
_HUMANIZER_BUILD_LOCK = threading.Lock()


class DiscordGatewaySession:
    GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"

    def __init__(self, token: str, build_number: int):
        self.token = token
        self.build_number = build_number
        self._ws = None
        self._heartbeat_thread = None
        self._heartbeat_interval = 41.25
        self._sequence = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._session_id = None
        self._recv_thread = None

    def connect(self, timeout: float = 10.0) -> bool:
        """Connect to the gateway, identify, and wait for READY."""
        try:
            self._ws = websocket.WebSocket()
            self._ws.settimeout(10)
            self._ws.connect(self.GATEWAY_URL)

            hello_raw = self._ws.recv()
            hello = json.loads(hello_raw)
            if hello.get("op") != 10:
                log.warning("Gateway: expected Hello (op 10), got op %s", hello.get("op"))
                self.close()
                return False

            self._heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0

            time.sleep(self._heartbeat_interval * random.random() * 0.1)
            self._send_heartbeat()

            identify = {
                "op": 2,
                "d": {
                    "token": self.token,
                    "capabilities": 30717,
                    "properties": {
                        "os": "Windows",
                        "browser": "Discord Client",
                        "release_channel": "stable",
                        "client_version": DISCORD_CLIENT_VERSION,
                        "os_version": "10.0.26100",
                        "os_arch": "x64",
                        "app_arch": "x64",
                        "system_locale": "en-US",
                        "has_client_mods": False,
                        "browser_user_agent": _USER_AGENT,
                        "browser_version": ELECTRON_VERSION,
                        "client_build_number": self.build_number,
                        "native_build_number": random.randint(65600, 65800),
                        "client_event_source": None,
                    },
                    "presence": {
                        "status": "online",
                        "since": 0,
                        "activities": [],
                        "afk": False,
                    },
                    "compress": False,
                    "client_state": {
                        "guild_versions": {},
                    },
                },
            }
            self._ws.send(json.dumps(identify))

            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    raw = self._ws.recv()
                    if not raw:
                        continue
                    msg = json.loads(raw)

                    if msg.get("s") is not None:
                        self._sequence = msg["s"]

                    if msg.get("op") == 0 and msg.get("t") == "READY":
                        self._session_id = msg["d"].get("session_id")
                        self._ready.set()
                        break
                    elif msg.get("op") == 9:
                        log.warning("Gateway: invalid session during identify")
                        self.close()
                        return False
                    elif msg.get("op") == 1:
                        self._send_heartbeat()
                except Exception as e:
                    if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                        continue
                    log.debug(f"Gateway recv error during identify: {e}")
                    break

            if not self._ready.is_set():
                log.warning("Gateway: READY not received within timeout")
                self.close()
                return False

            self._stop.clear()
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()

            return True
        except Exception as e:
            log.warning(f"Gateway connect failed: {e}")
            self.close()
            return False

    def _send_heartbeat(self):
        try:
            self._ws.send(json.dumps({"op": 1, "d": self._sequence}))
        except Exception:
            pass

    def _heartbeat_loop(self):
        while not self._stop.is_set():
            self._stop.wait(self._heartbeat_interval)
            if self._stop.is_set():
                break
            self._send_heartbeat()

    def _recv_loop(self):
        """Keep receiving messages so the connection stays alive."""
        while not self._stop.is_set():
            try:
                if self._ws is None:
                    break
                raw = self._ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                if msg.get("s") is not None:
                    self._sequence = msg["s"]
                if msg.get("op") == 1:
                    self._send_heartbeat()
            except Exception as _e:
                if "timed out" in str(_e).lower() or "timeout" in str(_e).lower():
                    continue
                break

    def close(self):
        self._stop.set()
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
        self._ws = None

    @property
    def is_ready(self):
        return self._ready.is_set()


def _humanizer_fetch_build_number():
    global _HUMANIZER_BUILD_CACHE
    if _HUMANIZER_BUILD_CACHE:
        return _HUMANIZER_BUILD_CACHE

    FALLBACK = 519006
    try:
        with _HUMANIZER_BUILD_LOCK:
            if _HUMANIZER_BUILD_CACHE:
                return _HUMANIZER_BUILD_CACHE

            resp = primp.Client(verify=False).get("https://discord.com/login", timeout=10)
            if resp.status_code != 200:
                return FALLBACK

            asset_urls = re.findall(r'/assets/([a-zA-Z0-9_-]+)\.js', resp.text)
            if not asset_urls:
                return FALLBACK

            for asset_hash in reversed(asset_urls):
                try:
                    js_resp = primp.Client(verify=False).get(
                        f"https://discord.com/assets/{asset_hash}.js",
                        timeout=10
                    )
                    if js_resp.status_code != 200:
                        continue

                    match = re.search(r'buildNumber["\s:,]+(\d{4,7})', js_resp.text)
                    if match:
                        _HUMANIZER_BUILD_CACHE = int(match.group(1))
                        return _HUMANIZER_BUILD_CACHE
                except Exception:
                    continue

            return FALLBACK
    except Exception as e:
        log.warning(f"Humanizer build fetch failed: {e}")
        return FALLBACK


def _humanizer_build_xsp(build_number):
    return base64.b64encode(json.dumps({
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": DISCORD_CLIENT_VERSION,
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "has_client_mods": False,
        "browser_user_agent": _USER_AGENT,
        "browser_version": ELECTRON_VERSION,
        "client_build_number": build_number,
        "native_build_number": random.randint(65600, 65800),
        "client_event_source": None,
        "client_launch_id": str(uuid.uuid4()),
        "launch_signature": str(uuid.uuid4()),
        "client_heartbeat_session_id": str(uuid.uuid4()),
    }, separators=(",", ":")).encode()).decode()


_COMMON_TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "America/Toronto", "America/Vancouver", "Europe/London", "Europe/Paris",
    "Europe/Berlin", "Europe/Amsterdam", "Europe/Stockholm", "Europe/Madrid",
    "Australia/Sydney", "Australia/Melbourne", "Asia/Tokyo", "Asia/Singapore",
]


def _humanizer_headers(token, build_number, session_id: str = None):
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br",
        "accept-language": "en-US,en;q=0.9",
        "authorization": token,
        "content-type": "application/json",
        "origin": "https://discord.com",
        "referer": "https://discord.com/channels/@me",
        "user-agent": _USER_AGENT,
        "x-debug-options": "bugReporterEnabled",
        "x-discord-locale": "en-US",
        "x-discord-timezone": random.choice(_COMMON_TIMEZONES),
        "x-super-properties": _humanizer_build_xsp(build_number),
    }
    if session_id:
        headers["x-session-id"] = session_id
    return headers


def _humanizer_patch(url, payload, headers, proxy_url=None, attempt=0):
    try:
        kw = {"verify": False}
        if proxy_url:
            kw["proxy"] = proxy_url
        c = primp.Client(**kw)
        r = c.patch(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 429:
            retry_after = 2.0
            try:
                retry_after = float(r.json().get("retry_after", 2))
            except Exception:
                pass
            time.sleep(retry_after + random.uniform(0.5, 1.5))
            if attempt < _HUMANIZER_RETRY_LIMIT:
                return _humanizer_patch(url, payload, headers, proxy_url, attempt + 1)
        return r
    except Exception:
        if attempt < _HUMANIZER_RETRY_LIMIT:
            time.sleep(1.5)
            return _humanizer_patch(url, payload, headers, proxy_url, attempt + 1)
        return None


def _humanizer_post(url, payload, headers, proxy_url=None, attempt=0):
    try:
        kw = {"verify": False}
        if proxy_url:
            kw["proxy"] = proxy_url
        c = primp.Client(**kw)
        r = c.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 429:
            retry_after = 2.0
            try:
                retry_after = float(r.json().get("retry_after", 2))
            except Exception:
                pass
            time.sleep(retry_after + random.uniform(0.5, 1.5))
            if attempt < _HUMANIZER_RETRY_LIMIT:
                return _humanizer_post(url, payload, headers, proxy_url, attempt + 1)
        return r
    except Exception:
        if attempt < _HUMANIZER_RETRY_LIMIT:
            time.sleep(1.5)
            return _humanizer_post(url, payload, headers, proxy_url, attempt + 1)
        return None


def _check_captcha(r):
    """Check if response indicates a captcha challenge. Returns 'CAPTCHA' or None."""
    if r is None:
        return None
    try:
        response_json = r.json()
    except Exception:
        response_json = {}
    if any(k in response_json for k in ("captcha_key", "captcha_sitekey", "captcha_rqtoken")):
        return "CAPTCHA"
    text = r.text.lower() if r.text else ""
    if "checkpoint" in text or "captcha" in text:
        return "CAPTCHA"
    return None


def set_discord_avatar(token: str, avatar_base64: str, proxy_url: str = None) -> bool:
    try:
        build_number = _humanizer_fetch_build_number()
        headers = _humanizer_headers(token, build_number)
        if not avatar_base64.startswith("data:"):
            avatar_base64 = f"data:image/png;base64,{avatar_base64}"
        payload = {"avatar": avatar_base64}
        r = _humanizer_patch("https://discord.com/api/v9/users/@me", payload, headers, proxy_url)
        if r is None:
            return False
        cap = _check_captcha(r)
        if cap:
            return False
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def set_discord_bio(token: str, bio: str, proxy_url: str = None) -> bool:
    try:
        build_number = _humanizer_fetch_build_number()
        headers = _humanizer_headers(token, build_number)
        payload = {"bio": bio}
        r = _humanizer_patch("https://discord.com/api/v9/users/@me/profile", payload, headers, proxy_url)
        if r is None:
            return False
        cap = _check_captcha(r)
        if cap:
            return False
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def set_hypesquad(token: str, house_id: int, proxy_url: str = None) -> bool:
    try:
        build_number = _humanizer_fetch_build_number()
        headers = _humanizer_headers(token, build_number)
        payload = {"house_id": house_id}
        r = _humanizer_post("https://discord.com/api/v9/hypesquad/online", payload, headers, proxy_url)
        if r is None:
            return False
        cap = _check_captcha(r)
        if cap:
            return False
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def set_pronouns(token: str, pronouns: str, proxy_url: str = None) -> bool:
    try:
        build_number = _humanizer_fetch_build_number()
        headers = _humanizer_headers(token, build_number)
        payload = {"pronouns": pronouns}
        r = _humanizer_patch("https://discord.com/api/v9/users/@me/profile", payload, headers, proxy_url)
        if r is None:
            return False
        cap = _check_captcha(r)
        if cap:
            return False
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def set_display_name(token: str, display_name: str, proxy_url: str = None) -> bool:
    try:
        build_number = _humanizer_fetch_build_number()
        headers = _humanizer_headers(token, build_number)
        payload = {"global_name": display_name}
        r = _humanizer_patch("https://discord.com/api/v9/users/@me", payload, headers, proxy_url)
        if r is None:
            return False
        cap = _check_captcha(r)
        if cap:
            return False
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


class DiscordHuminazer:
    """Humanize Discord accounts using primp + Gateway WebSocket session.

    This is the proven method ported from human.py. The Gateway session
    keeps the token "online" so Discord doesn't reject API PATCH requests
    with "Unknown Session" (code 10020).
    """

    def __init__(self, worker_id: int) -> None:
        self.worker_id: int = worker_id
        self.profile_dir: Path = Path(get_resource_path("data/input/profiles"))
        self.avatar_dir: Path = self.profile_dir / "avatars"
        self.houses: List[str] = ["bravery", "brilliance", "balance"]

        config = Config.config
        h_cfg = config.get("humanizer", {})
        self.bios: Optional[List[str]] = (
            self._load_from_file("bio.txt") if h_cfg.get("bio", True) else None
        )
        self.names: Optional[List[str]] = (
            self._load_from_file("names.txt") if h_cfg.get("display_name", True) else None
        )
        self.pronouns_list: Optional[List[str]] = (
            self._load_from_file("pronouns.txt") if h_cfg.get("pronouns", True) else None
        )


    @property
    def config(self) -> dict:
        return Config.config


    def _load_from_file(self, filename: str) -> Optional[List[str]]:
        file_path = self.profile_dir / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return None

    def _get_random_bio(self) -> Optional[str]:
        return random.choice(self.bios) if self.bios else None

    def _get_random_display_name(self) -> Optional[str]:
        return random.choice(self.names) if self.names else None

    def _get_random_pronouns(self) -> Optional[str]:
        return random.choice(self.pronouns_list) if self.pronouns_list else None

    def _get_random_avatar(self) -> Optional[Path]:
        if not self.config.get("humanizer", {}).get("avatar", True):
            return None
        avatar_files = (
            list(self.avatar_dir.glob("*.png"))
            + list(self.avatar_dir.glob("*.jpg"))
            + list(self.avatar_dir.glob("*.jpeg"))
            + list(self.avatar_dir.glob("*.webp"))
        )
        return random.choice(avatar_files) if avatar_files else None

    def _prepare_avatar(self, path: Path) -> Optional[str]:
        """Convert any image to 256x256 JPEG for Discord avatar upload."""
        try:
            with Image.open(path) as img:
                img = img.convert("RGB")
                img = img.resize((256, 256), Image.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                data = buffer.getvalue()
                q = 70
                while len(data) > 2_000_000 and q > 20:
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=q)
                    data = buffer.getvalue()
                    q -= 10
            return base64.b64encode(data).decode("utf-8")
        except Exception:
            return None


    @staticmethod
    def _human_delay(min_s: float = 0.3, max_s: float = 0.8) -> None:
        time.sleep(random.uniform(min_s, max_s))


    def humanize_account(self, token: str, proxy_dict: Optional[Dict]) -> bool:
        """Humanize a Discord account: set avatar, bio, name, pronouns, hypesquad.

        Uses Gateway WebSocket session to keep the token alive during API calls.
        """
        try:
            proxy_url: Optional[str] = None

            if proxy_dict and isinstance(proxy_dict, dict):
                try:
                    server_url: str = proxy_dict.get("server", "")
                    if server_url:
                        if server_url.startswith("http://"):
                            server_url = server_url[7:]
                        elif server_url.startswith("https://"):
                            server_url = server_url[8:]

                        if "username" in proxy_dict and "password" in proxy_dict:
                            proxy_url = (
                                f"http://{proxy_dict['username']}:"
                                f"{proxy_dict['password']}@{server_url}"
                            )
                        else:
                            proxy_url = f"http://{server_url}"
                except Exception as e:
                    Logger.STATUS = (
                        f"{MskColor.YELLOW}Proxy parse fail, continuing: {e}"
                    )
                    Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                    proxy_url = None

            return self._update_profile(token, proxy_url)
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Humanization error: {str(e)}"
            Logger.queue_log(worker_id=self.worker_id, overwrite=False)
            return False


    def _patch(self, url: str, payload: dict, headers: dict, proxy_url: Optional[str], attempt: int = 0):
        try:
            kw = {"verify": False}
            if proxy_url:
                kw["proxy"] = proxy_url
            c = primp.Client(**kw)
            r = c.patch(url, json=payload, headers=headers, timeout=15)
            if r.status_code == 429:
                retry_after = 2.0
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass
                time.sleep(retry_after + random.uniform(0.5, 1.5))
                if attempt < _HUMANIZER_RETRY_LIMIT:
                    return self._patch(url, payload, headers, proxy_url, attempt + 1)
            return r
        except Exception:
            if attempt < _HUMANIZER_RETRY_LIMIT:
                time.sleep(1.5)
                return self._patch(url, payload, headers, proxy_url, attempt + 1)
            return None

    def _post(self, url: str, payload: dict, headers: dict, proxy_url: Optional[str], attempt: int = 0):
        try:
            kw = {"verify": False}
            if proxy_url:
                kw["proxy"] = proxy_url
            c = primp.Client(**kw)
            r = c.post(url, json=payload, headers=headers, timeout=15)
            if r.status_code == 429:
                retry_after = 2.0
                try:
                    retry_after = float(r.json().get("retry_after", 2))
                except Exception:
                    pass
                time.sleep(retry_after + random.uniform(0.5, 1.5))
                if attempt < _HUMANIZER_RETRY_LIMIT:
                    return self._post(url, payload, headers, proxy_url, attempt + 1)
            return r
        except Exception:
            if attempt < _HUMANIZER_RETRY_LIMIT:
                time.sleep(1.5)
                return self._post(url, payload, headers, proxy_url, attempt + 1)
            return None


    def _update_profile(self, token: str, proxy_url: Optional[str]) -> bool:
        try:
            succeeded = []
            failed_parts = []
            h_cfg = self.config.get("humanizer", {})

            build_number = _humanizer_fetch_build_number()

            gw = DiscordGatewaySession(token, build_number)
            gw_ok = gw.connect(timeout=10)

            time.sleep(random.uniform(0.4, 0.8))

            session_id = gw._session_id if gw_ok else None
            headers = _humanizer_headers(token, build_number, session_id=session_id)

            try:
                if h_cfg.get("display_name", True):
                    display_name = self._get_random_display_name()
                    if display_name:
                        try:
                            self._human_delay(1.8, 3.2)
                            r = self._patch(
                                "https://discord.com/api/v9/users/@me",
                                {"global_name": display_name[:32]},
                                headers, proxy_url
                            )
                            if r and r.status_code in (200, 201, 204) and not _check_captcha(r):
                                succeeded.append("name")
                            else:
                                failed_parts.append("name")
                        except Exception as e:
                            Logger.STATUS = f"{MskColor.YELLOW}Name error: {str(e)[:60]}"
                            Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                            failed_parts.append("name")

                want_bio = h_cfg.get("bio", True)
                want_pronouns = h_cfg.get("pronouns", True)
                profile_payload: dict = {}

                if want_bio:
                    bio_text = self._get_random_bio()
                    if bio_text:
                        profile_payload["bio"] = bio_text[:190]

                if want_pronouns:
                    pronouns = self._get_random_pronouns()
                    if pronouns:
                        profile_payload["pronouns"] = pronouns

                if profile_payload:
                    try:
                        self._human_delay(1.8, 3.2)
                        r = self._patch(
                            "https://discord.com/api/v9/users/@me/profile",
                            profile_payload, headers, proxy_url
                        )
                        if r and r.status_code in (200, 201, 204) and not _check_captcha(r):
                            if "bio" in profile_payload:
                                succeeded.append("bio")
                            if "pronouns" in profile_payload:
                                succeeded.append("pronouns")
                        else:
                            if "bio" in profile_payload:
                                failed_parts.append("bio")
                            if "pronouns" in profile_payload:
                                failed_parts.append("pronouns")
                    except Exception as e:
                        Logger.STATUS = f"{MskColor.YELLOW}Profile error: {str(e)[:60]}"
                        Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                        if "bio" in profile_payload:
                            failed_parts.append("bio")
                        if "pronouns" in profile_payload:
                            failed_parts.append("pronouns")

                if h_cfg.get("hypesquad", True):
                    house_id = random.randint(1, 3)
                    try:
                        self._human_delay(1.8, 3.2)
                        r = self._post(
                            "https://discord.com/api/v9/hypesquad/online",
                            {"house_id": house_id},
                            headers, proxy_url
                        )
                        if r and r.status_code in (200, 201, 204) and not _check_captcha(r):
                            succeeded.append("hypesquad")
                        else:
                            failed_parts.append("hypesquad")
                    except Exception as e:
                        Logger.STATUS = f"{MskColor.YELLOW}Hypesquad error: {str(e)[:60]}"
                        Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                        failed_parts.append("hypesquad")

                if h_cfg.get("avatar", True):
                    avatar_path = self._get_random_avatar()
                    if avatar_path:
                        avatar_b64 = self._prepare_avatar(avatar_path)
                        if avatar_b64:
                            try:
                                self._human_delay(2.0, 3.5)
                                r = self._patch(
                                    "https://discord.com/api/v9/users/@me",
                                    {"avatar": f"data:image/jpeg;base64,{avatar_b64}"},
                                    headers, proxy_url
                                )
                                if r and r.status_code in (200, 201, 204) and not _check_captcha(r):
                                    succeeded.append("avatar")
                                else:
                                    failed_parts.append("avatar")
                            except Exception as e:
                                Logger.STATUS = f"{MskColor.YELLOW}Avatar error: {str(e)[:60]}"
                                Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                                failed_parts.append("avatar")
                        else:
                            Logger.STATUS = f"{MskColor.YELLOW}Avatar: image prepare failed"
                            Logger.queue_log(worker_id=self.worker_id, overwrite=False)
                    else:
                        Logger.STATUS = f"{MskColor.GREY}Avatar: no files in profiles/avatars/"
                        Logger.queue_log(worker_id=self.worker_id, overwrite=False)

            finally:
                gw.close()

            if succeeded and not failed_parts:
                Logger.STATUS = f"{MskColor.GREEN}Humanized [all]"
            elif succeeded:
                Logger.STATUS = (
                    f"{MskColor.GREEN}Humanized [{'/'.join(succeeded)}]"
                )
            else:
                Logger.STATUS = f"{MskColor.RED}Humanize failed"
            Logger.queue_log(worker_id=self.worker_id, overwrite=False)

            return len(failed_parts) == 0

        except Exception as e:
            Logger.STATUS = (
                f"{MskColor.RED}Profile update error: {str(e)[:100]}"
            )
            Logger.queue_log(worker_id=self.worker_id, overwrite=False)
            return False
