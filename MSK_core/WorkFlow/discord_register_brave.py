import os

import sys

import time

import random

import re

import asyncio

import string

import tempfile

import shutil

import warnings

from pathlib import Path

from typing import Optional, Dict, Tuple, List

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

warnings.filterwarnings('ignore', category=DeprecationWarning)

from ..MskColors.color import MskColor

from ..Utils.utils import Utils, Config, get_base_path, get_resource_path

from ..Utils.logger import Logger

from ..Utils.proxy_manager import ProxyManager

COUNTRY_CODES = {

    "1": "United States", "44": "United Kingdom", "31": "Netherlands",

    "33": "France", "49": "Germany", "34": "Spain", "39": "Italy",

    "351": "Portugal", "46": "Sweden", "47": "Norway", "45": "Denmark",

    "358": "Finland", "48": "Poland", "420": "Czech Republic",

    "43": "Austria", "41": "Switzerland", "32": "Belgium",

    "353": "Ireland", "30": "Greece", "36": "Hungary", "40": "Romania",

    "359": "Bulgaria", "380": "Ukraine", "7": "Russia",

    "55": "Brazil", "52": "Mexico", "54": "Argentina", "57": "Colombia",

    "56": "Chile", "51": "Peru", "58": "Venezuela",

    "91": "India", "62": "Indonesia", "63": "Philippines",

    "66": "Thailand", "84": "Vietnam", "60": "Malaysia",

    "65": "Singapore", "81": "Japan", "82": "South Korea",

    "86": "China", "852": "Hong Kong", "886": "Taiwan",

    "90": "Turkey", "966": "Saudi Arabia", "971": "United Arab Emirates",

    "972": "Israel", "20": "Egypt", "27": "South Africa",

    "234": "Nigeria", "254": "Kenya", "61": "Australia", "64": "New Zealand",

}

class _PersistentLoop:

    """A persistent asyncio event loop running in a background thread.

    ZenDriver binds its browser process to the loop it was started on.

    Every subsequent CDP call MUST run on that same loop, otherwise the

    connection is refused (WinError 1225).  This helper keeps one loop

    alive for the lifetime of a registration attempt.

    """

    def __init__(self):

        self._loop = asyncio.new_event_loop()

        self._thread = None

        

        def _handle_exception(loop, context):

            msg = context.get("exception", context.get("message", ""))

            exc_str = str(msg) if isinstance(msg, Exception) else str(msg)

            _noise = (

                "Invalid InterceptionId",

                "Task exception was never retrieved",

                "ConnectionClosedError",

                "no close frame",

                "connection closed",

                "ConnectionClosed",

                "websocket",

                "target closed",

                "session closed",

            )

            if any(n.lower() in exc_str.lower() for n in _noise):

                return

            loop.default_exception_handler(context)

        self._loop.set_exception_handler(_handle_exception)

    def start(self):

        import threading

        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)

        self._thread.start()

    def run(self, coro, timeout=60):

        """Schedule *coro* on the persistent loop and block until done."""

        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)

        return fut.result(timeout=timeout)

    def stop(self):

        def _cancel_and_stop():

            try:

                for task in asyncio.all_tasks(self._loop):

                    task.cancel()

            except Exception:

                pass

            try:

                self._loop.stop()

            except Exception:

                pass

        try:

            self._loop.call_soon_threadsafe(_cancel_and_stop)

        except Exception:

            pass

        if self._thread and self._thread.is_alive():

            self._thread.join(timeout=3)

        try:

            pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]

            if pending:

                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        except Exception:

            pass

        try:

            self._loop.run_until_complete(self._loop.shutdown_asyncgens())

        except Exception:

            pass

        try:

            self._loop.close()

        except Exception:

            pass

def _get_browser_version(exe_path: str) -> Tuple[str, str]:

    """Get the major and full version of the browser binary on Windows."""

    try:

        import subprocess

        cmd = f'(Get-Item "{exe_path}").VersionInfo.ProductVersion'

        raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", cmd], timeout=3, creationflags=0x08000000).decode().strip()

        if raw and '.' in raw:

            major = raw.split('.')[0]

            return major, raw

    except Exception:

        pass

    return "136", "136.0.7103.92"

def _find_brave_executable() -> str:

    """Auto-detect Brave browser executable on Windows.

    

    Uses hardcoded paths as fallback when Nuitka mangles env vars

    like LOCALAPPDATA (truncating 'AppData' to 'AppDat' etc.).

    """

    if sys.platform != "win32":

        return ""

    

    candidates = []

    

    env_dirs = []

    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "PROGRAMW6432"):

        val = os.environ.get(var)

        if val:

            env_dirs.append(val)

    

    user_profile = os.environ.get("USERPROFILE", "")

    if user_profile:

        env_dirs.append(os.path.join(user_profile, "AppData", "Local"))

    

    for drive in ("C:", "D:"):

        env_dirs.extend([

            f"{drive}\\Program Files",

            f"{drive}\\Program Files (x86)",

        ])

    

    seen = set()

    unique_dirs = []

    for d in env_dirs:

        dn = os.path.normpath(d).lower()

        if dn not in seen:

            seen.add(dn)

            unique_dirs.append(d)

    

    for base_dir in unique_dirs:

        candidates.append(os.path.join(base_dir, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"))

    

    for path in candidates:

        if os.path.isfile(path):

            return os.path.normpath(path)

    return ""

def _find_chrome_executable() -> str:

    """Auto-detect Chrome/Chromium browser executable on Windows.

    Preferred over Brave because Chrome doesn't add Brave-specific headers.

    """

    if sys.platform != "win32":

        return ""

    candidates = []

    env_dirs = []

    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "PROGRAMW6432"):

        val = os.environ.get(var)

        if val:

            env_dirs.append(val)

    user_profile = os.environ.get("USERPROFILE", "")

    if user_profile:

        env_dirs.append(os.path.join(user_profile, "AppData", "Local"))

    for drive in ("C:", "D:"):

        env_dirs.extend([

            f"{drive}\\Program Files",

            f"{drive}\\Program Files (x86)",

        ])

    seen = set()

    unique_dirs = []

    for d in env_dirs:

        dn = os.path.normpath(d).lower()

        if dn not in seen:

            seen.add(dn)

            unique_dirs.append(d)

    for base_dir in unique_dirs:

        candidates.append(os.path.join(base_dir, "Google", "Chrome", "Application", "chrome.exe"))

        candidates.append(os.path.join(base_dir, "Chromium", "Application", "chrome.exe"))

    for path in candidates:

        if os.path.isfile(path):

            return os.path.normpath(path)

    return ""

class GeneratorStoppedError(Exception):

    """Raised when the user stops generation mid-flow."""

    pass

class DiscordRegisterBrave:

    """Discord account registration using Brave Browser CDP."""

    def __init__(self):

        self.proxy_manager = ProxyManager("data/input/proxies.txt")

        self.password = Utils.random_password()

        self._tab = None

        self._browser = None

        self._loop_helper: Optional[_PersistentLoop] = None

        self._zeus_refresh_token = ""

        self._zeus_client_id = ""

    def _check_stop(self):

        """Raise GeneratorStoppedError if user requested stop."""

        if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):

            raise GeneratorStoppedError("Stopped by user")

        if hasattr(self, '_trigger_parent') and getattr(self._trigger_parent, 'should_stop', False):

            raise GeneratorStoppedError("Stopped by user")

    def _sleep(self, seconds):

        """Sleep in small chunks, checking stop flag between each."""

        remaining = seconds

        while remaining > 0:

            self._check_stop()

            chunk = min(remaining, 0.5)

            time.sleep(chunk)

            remaining -= chunk

    def _run(self, coro, timeout=60):

        """Run an awaitable on the persistent loop."""

        if self._loop_helper is None:

            return None

        try:

            return self._loop_helper.run(coro, timeout=timeout)

        except Exception as e:

            if "Persistent loop not started" in str(e) or "Event loop is closed" in str(e):

                return None

            raise

    @property

    def config(self) -> Dict:

        return Config.config

    # NO custom fingerprinting JavaScript - browser runs with default behavior

    def _create_browser(self, headless: bool = False, proxy: Optional[Dict] = None, wm_pos: Optional[tuple] = None):

        """Start truedriver browser using Chrome (preferred) or Brave fallback, and return tab.

        Chrome is preferred over Brave because Brave adds browser-specific HTTP headers

        (X-Brave-*, Sec-CH-UA with Brave brand, braveRequestUUID) that are sent below

        the CDP layer and cannot be suppressed -- Discord's backend detects these and

        flags/locks the resulting token. Chrome via truedriver produces clean sessions.

        """

        import truedriver

        from truedriver.core.config import Config as ZenConfig

        self._loop_helper = _PersistentLoop()

        self._loop_helper.start()

        # Brave Browser mode: find Brave first, fallback to Chrome if needed

        browser_path = _find_brave_executable()

        _using_brave = True

        if not browser_path:

            browser_path = _find_chrome_executable()

            _using_brave = False

        if not browser_path:

            Logger.STATUS = f"{MskColor.RED}No Brave or Chrome browser found! Install Brave or Chrome."

            Logger.queue_log(worker_id=getattr(self, 'worker_id', 0))

            raise FileNotFoundError("No Brave or Chrome browser executable found on this system.")

        _geo_locale = "en-US"

        _geo_tz = "America/New_York"

        if proxy and proxy.get("server"):

            try:

                from ..Utils.geo_lookup import lookup_proxy_geo

                _geo_tz, _geo_locale = lookup_proxy_geo(proxy)

            except Exception:

                pass

        _lang_primary = _geo_locale  # e.g. "de-DE", "en-US"

        _lang_short = _geo_locale.split("-")[0] if "-" in _geo_locale else _geo_locale

        _accept_lang = f"{_geo_locale},{_lang_short};q=0.9,en;q=0.8" if _geo_locale != "en-US" else "en-US,en;q=0.9"

        extra_args = []

        if headless:

            extra_args.append("--window-position=-10000,-10000")

            if wm_pos:

                extra_args.append(f"--window-size={wm_pos[2]},{wm_pos[3]}")

        elif wm_pos:

            extra_args.append(f"--window-size={wm_pos[2]},{wm_pos[3]}")

            extra_args.append(f"--window-position={wm_pos[0]},{wm_pos[1]}")

        # Keep ONLY essential flags for basic browser operation
        extra_args.extend([
            "--no-first-run",
            "--no-default-browser-check",
            f"--lang={_lang_primary}",
        ])

        user_data_dir = None

        if getattr(self, "worker_id", None) is not None and self.config.get("data_saver_enabled"):

            profile_dir = os.path.join("data", "output", "profiles_brave", f"worker_{self.worker_id}")

            if self.config.get("update_browser_save"):

                if os.path.exists(profile_dir):

                    try:

                        shutil.rmtree(profile_dir, ignore_errors=True)

                    except Exception:

                        pass

            os.makedirs(profile_dir, exist_ok=True)

            user_data_dir = os.path.abspath(profile_dir)

            self._profile_dir = user_data_dir

            for _lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):

                _lock_path = os.path.join(user_data_dir, _lock_name)

                try:

                    if os.path.exists(_lock_path):

                        os.remove(_lock_path)

                except Exception:

                    pass

            if os.path.isdir(_ext_path):

                shutil.copytree(_ext_path, _tmp_ext, dirs_exist_ok=True)

                # Use the pool-managed current key (supports multi-key rotation)
                # instead of hardcoding the single "api_key" field from config.

                # Method 1: Patch manifest.json -- inject API key and make
                # declarativeNetRequest optional so the extension loads on
                # Brave/Chromium builds that don't support that permission.

                _manifest_path = os.path.join(_tmp_ext, "manifest.json")

                try:
                    if os.path.exists(_manifest_path):
                        import json as _nj
                        with open(_manifest_path, "r", encoding="utf-8") as _f:
                            _manifest = _nj.load(_f)

                        # Remove minimum_chrome_version -- it causes "version not supported"
                        # on Brave builds whose reported version doesn't satisfy the floor.
                        _manifest.pop("minimum_chrome_version", None)

                        _perms = _manifest.get("permissions", [])
                        if "declarativeNetRequest" in _perms:
                            _perms = [p for p in _perms if p != "declarativeNetRequest"]
                            _manifest["permissions"] = _perms
                            _opt = _manifest.get("optional_permissions", [])
                            if "declarativeNetRequest" not in _opt:
                                _opt.append("declarativeNetRequest")
                            _manifest["optional_permissions"] = _opt

                        with open(_manifest_path, "w", encoding="utf-8") as _f:
                            _nj.dump(_manifest, _f, indent=2)

                except Exception:
                    pass

        _proxy_auth_creds = None

        _proxy_ext_dir = None

        if proxy and proxy.get("server"):

            server_raw = proxy["server"]

            if "://" in server_raw:

                server_raw = server_raw.split("://", 1)[1]

            username = proxy.get("username", "")

            password = proxy.get("password", "")

            if username and password:

                _proxy_auth_creds = {"username": username, "password": password}

                try:

                    from ..Utils.proxy_auth_extension import create_proxy_auth_extension

                    _proxy_ext_dir = create_proxy_auth_extension(username, password)

                    self._proxy_ext_dir = _proxy_ext_dir

                except Exception as _e:

                    Logger.STATUS = f"{MskColor.YELLOW}Could not create proxy auth extension: {_e}"

                    Logger.queue_log(worker_id=getattr(self, 'worker_id', 0))

        _extensions_to_load = []

        if _proxy_ext_dir:

            _extensions_to_load.append(_proxy_ext_dir)

        if _extensions_to_load:

            _ext_csv = ",".join(_extensions_to_load)

            extra_args.append(f"--load-extension={_ext_csv}")

            extra_args.append(f"--disable-extensions-except={_ext_csv}")

        else:

            extra_args.append("--disable-extensions")

        # Only add Brave-specific flags when actually running Brave

        # These flags don't exist in Chrome and could be a tell when used there

        if _using_brave:
            extra_args.extend([
                "--disable-features=BraveShields,BraveAdblocker,BraveRewards,BraveNews,BraveSpeedreader",
                "--disable-brave-extension",
                "--disable-brave-update",
                "--no-pings",
            ])

        if not user_data_dir and _extensions_to_load:

            try:

                _tmp_profile = tempfile.mkdtemp(prefix="msk_brave_profile_")

                self._tmp_brave_profile = _tmp_profile

                user_data_dir = _tmp_profile

            except Exception:

                pass

        if user_data_dir:

            try:

                _default_dir = os.path.join(user_data_dir, "Default")

                os.makedirs(_default_dir, exist_ok=True)

                _prefs_path = os.path.join(_default_dir, "Preferences")

                import json as _pj

                import time as _pt

                _prefs = {}

                if os.path.exists(_prefs_path):

                    with open(_prefs_path, "r", encoding="utf-8") as _f:

                        try:

                            _prefs = _pj.load(_f)

                        except _pj.JSONDecodeError:

                            pass

                _prof = _prefs.setdefault("profile", {})

                if "created_time" not in _prof:

                    _prof["created_time"] = str(int(_pt.time() * 1_000_000))

                _prof.setdefault("name", "Default")

                _prof.setdefault("is_using_default_name", True)

                _prefs.setdefault("extensions", {}).setdefault("ui", {})["developer_mode"] = True

                # No Brave-specific fingerprinting settings

                with open(_prefs_path, "w", encoding="utf-8") as _f:

                    _pj.dump(_prefs, _f)

            except Exception as e:

                Logger.STATUS = f"{MskColor.YELLOW}Failed to set Developer Mode in Brave profile: {e}"

                Logger.queue_log(worker_id=getattr(self, 'worker_id', 0))

        zen_config = ZenConfig(

            headless=False,

            expert=False,

            browser_executable_path=browser_path,

            browser_args=extra_args,

            user_data_dir=user_data_dir,

        )

        # No custom browser args filtering - use truedriver defaults as-is
        zen_config._browser_args = extra_args

        for _ext_path in _extensions_to_load:

            try:

                zen_config.add_extension(_ext_path)

            except Exception as e:

                Logger.STATUS = f"{MskColor.RED}Error adding extension to truedriver: {e}"

                Logger.queue_log(worker_id=getattr(self, 'worker_id', 0))

        if proxy and proxy.get("server"):
            server_raw = proxy["server"]
            if "://" in server_raw:
                server_raw = server_raw.split("://", 1)[1]
            username = proxy.get("username", "")
            password = proxy.get("password", "")
            if username and password:
                zen_config.proxy = f"{username}:{password}@{server_raw}"
            else:
                zen_config.proxy = server_raw

        last_error = None

        for _ in range(2):

            try:

                browser = self._run(truedriver.start(config=zen_config))

                tab = self._run(browser.get("about:blank"))

                self._browser = browser

                self._tab = tab

                # Mask Brave Brand in Client Hints (Sec-CH-UA) and navigator.brave
                try:
                    import truedriver.cdp.network as _net_cdp
                    self._run(tab.send(_net_cdp.enable()))
                    _chrome_brands = [
                        _net_cdp.UserAgentBrandVersion(brand="Google Chrome", version="131"),
                        _net_cdp.UserAgentBrandVersion(brand="Chromium", version="131"),
                        _net_cdp.UserAgentBrandVersion(brand="Not_A Brand", version="24"),
                    ]
                    _chrome_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                    _ua_metadata = _net_cdp.UserAgentMetadata(
                        brands=_chrome_brands,
                        full_version="131.0.6778.86",
                        platform="Windows",
                        platform_version="10.0.0",
                        architecture="x86",
                        model="",
                        mobile=False,
                        bitness="64",
                    )
                    self._run(tab.send(_net_cdp.set_user_agent_override(
                        user_agent=_chrome_ua,
                        accept_language=_accept_lang,
                        platform="Win32",
                        user_agent_metadata=_ua_metadata,
                    )))
                except Exception:
                    pass

                try:
                    import truedriver.cdp.page as _page_cdp_init
                    _brave_stealth_js = """
                    (function() {
                        try {
                            delete Object.getPrototypeOf(navigator).brave;
                        } catch(e) {}
                        try {
                            delete navigator.brave;
                        } catch(e) {}
                        try {
                            Object.defineProperty(navigator, 'brave', {
                                get: () => undefined,
                                configurable: true
                            });
                        } catch(e) {}
                        try {
                            if (!window.chrome) {
                                window.chrome = {};
                            }
                            if (!window.chrome.runtime) {
                                window.chrome.runtime = {
                                    id: undefined,
                                    connect: function() { return {}; },
                                    sendMessage: function() {},
                                };
                            }
                        } catch(e) {}
                    })();
                    """
                    self._run(tab.send(_page_cdp_init.add_script_to_evaluate_on_new_document(source=_brave_stealth_js)))
                except Exception:
                    pass

                import truedriver.cdp.page as _page_nav_b

                self._run(tab.send(_page_nav_b.navigate("https://discord.com/register")))

                _start_load_b = time.time()

                while time.time() - _start_load_b < 15:

                    try:

                        ready = self._js("document.readyState")

                        if ready in ("interactive", "complete"):

                            break

                    except Exception:

                        pass

                    time.sleep(0.3)

                try:

                    import truedriver.cdp.page as _page

                    self._run(tab.send(_page.bring_to_front()))

                except Exception:

                    pass

                return tab

            except Exception as e:

                last_error = e

                time.sleep(2)

        raise Exception(str(last_error))

    def _cleanup(self):

        # Set tab to None FIRST so any concurrent _js() calls bail out immediately

        self._tab = None

        try:

            if self._browser:

                self._run(self._browser.stop(), timeout=3)

        except Exception:

            pass

        # Force-kill the browser process if still alive after graceful stop

        try:

            import subprocess

            _NO_WIN = 0x08000000

            if hasattr(self, '_browser_pid') and self._browser_pid:

                subprocess.run(["taskkill", "/F", "/PID", str(self._browser_pid), "/T"],

                               capture_output=True, creationflags=_NO_WIN)

        except Exception:

            pass

        self._browser = None

        self._tab = None

        try:

            if self._loop_helper:

                self._loop_helper.stop()

        except Exception:

            pass

        self._loop_helper = None

        if getattr(self, "_proxy_ext_dir", None):

            try:

                shutil.rmtree(self._proxy_ext_dir, ignore_errors=True)

            except Exception:

                pass

            self._proxy_ext_dir = None

        if getattr(self, "_proxy_auth_server", None):

            try:

                self._proxy_auth_server.stop()

            except Exception:

                pass

            self._proxy_auth_server = None

        if getattr(self, "_tmp_brave_profile", None):

            try:

                shutil.rmtree(self._tmp_brave_profile, ignore_errors=True)

            except Exception:

                pass

            self._tmp_brave_profile = None

        self._wipe_discord_data()

    def _wipe_discord_data(self):

        """Remove all Discord login/session data from the browser profile.

        Deletes cookies, localStorage, sessionStorage, IndexedDB, and

        any other Discord-related state so that no Discord account

        remains logged in across runs.

        """

        profile_dir = getattr(self, "_profile_dir", None)

        if not profile_dir or not os.path.exists(profile_dir):

            return

        import glob

        targets = [

            os.path.join(profile_dir, "**", "Cookies"),

            os.path.join(profile_dir, "**", "Cookies-journal"),

            os.path.join(profile_dir, "**", "Local Storage"),

            os.path.join(profile_dir, "**", "Session Storage"),

            os.path.join(profile_dir, "**", "IndexedDB"),

            os.path.join(profile_dir, "**", "Service Worker"),

            os.path.join(profile_dir, "**", "Web Data"),

            os.path.join(profile_dir, "**", "Web Data-journal"),

            os.path.join(profile_dir, "**", "Login Data"),

            os.path.join(profile_dir, "**", "Login Data-journal"),

            os.path.join(profile_dir, "**", "Extension State"),

            os.path.join(profile_dir, "**", "Extension Rules"),

            # "Local Extension Settings" excluded intentionally --

            # extension-mode captcha solving on subsequent runs.

        ]

        for pattern in targets:

            for path in glob.glob(pattern, recursive=True):

                try:

                    if os.path.isdir(path):

                        shutil.rmtree(path, ignore_errors=True)

                    elif os.path.isfile(path):

                        os.remove(path)

                except Exception:

                    pass

    @staticmethod

    def _unwrap_cdp_result(result):

        """Unwrap ZenDriver CDP evaluate() results.

        ZenDriver's evaluate() can return:

          - A plain Python value (str, int, bool, None)

          - A (RemoteObject, actual_value) tuple from CDP

          - A RemoteObject with a .value attribute

        This helper always returns the plain Python value.

        """

        if result is None:

            return None

        if isinstance(result, tuple):

            if len(result) >= 2:

                val = result[1]

                if val is not None:

                    return val

            if len(result) >= 1 and hasattr(result[0], 'value'):

                return result[0].value

            return None

        if hasattr(result, 'value') and not isinstance(result, (str, int, float, bool, list, dict)):

            return result.value

        return result

    def _js(self, script: str, timeout: int = 30):

        """Run JS on tab synchronously. Unwraps CDP RemoteObject tuples.

        Retries once on StopIteration which can surface from truedriver's

        internal CDP iteration (a coroutine is one-shot, so the retry

        must create a fresh evaluate() call).

        """

        # Guard: if tab was never created or browser was closed, return immediately

        if self._tab is None:

            return None

        # Guard: if user hit stop, don't bother running JS

        try:

            self._check_stop()

        except Exception:

            return None

        err_msg = ""

        for _attempt in range(2):

            try:

                if self._tab is None:

                    return None

                raw = self._run(self._tab.evaluate(script), timeout=timeout)

                return self._unwrap_cdp_result(raw)

            except RuntimeError as exc:

                if 'StopIteration' in str(exc) and _attempt == 0:

                    time.sleep(0.3)

                    continue

                err_msg = str(exc)[:120]

                break

            except Exception as e:

                err_msg = str(e)[:120]

                break

        else:

            return None

        noise_markers = ['timeout', 'exceptionid', 'uncaught', 'scriptid', 'linenumber',

                         'columnnumber', 'close frame', 'target closed', 'session closed',

                         'websocket', 'stopiteration', 'winerror', 'refused', 'connection',

                         'nonetype', 'has no attribute']

        is_noise = any(m in err_msg.lower() for m in noise_markers)

        if err_msg and not is_noise:

            try:

                Logger.STATUS = f"{MskColor.GREY}JS: {err_msg}"

                Logger.queue_log(worker_id=0)

            except Exception:

                pass

        return None

    def _check_passed(self) -> bool:

        """Check if registration succeeded: URL moved to channels/@me, or token in localStorage.

        Returns False if hCaptcha is still visible on the page."""

        if getattr(self, "_extracted_token", None):

            return True

        try:

            result = self._js("""

                (() => {

                    const url = window.location.href || '';

                    // Check if hCaptcha iframe is still present and visible

                    const hcapFrames = document.querySelectorAll('iframe[src*="hcaptcha"]');

                    for (const f of hcapFrames) {

                        const rect = f.getBoundingClientRect();

                        if (rect.width > 0 && rect.height > 0) return 'captcha_visible';

                    }

                    if (document.querySelector('[data-hcaptcha-widget-id]')) return 'captcha_visible';

                    // URL-based checks (strict: channels or @me only)

                    if (url.includes('/channels') || url.includes('/@me') || url.includes('/app')) {

                        // But NOT if still on register page

                        if (!url.includes('/register')) return 'passed_url';

                    }

                    if (url.includes('check-your-email') || url.includes('/verify')) return 'passed_url';

                    // Token in localStorage

                    try {

                        for (let i = 0; i < localStorage.length; i++) {

                            let k = localStorage.key(i);

                            if (k && k.toLowerCase().includes('token')) {

                                let v = localStorage.getItem(k);

                                if (v && v.length > 50 && !v.includes('{')) return 'passed_token';

                            }

                        }

                    } catch(e) {}

                    return 'not_passed';

                })()

            """)

            return result in ('passed_url', 'passed_token')

        except Exception:

            pass

        return False

    def _has_hcaptcha(self) -> bool:

        """Check if hCaptcha iframe or challenge is currently visible.

        Uses multiple signals to reliably detect hCaptcha presence:

        1. iframe with 'hcaptcha' in src attribute

        2. hCaptcha container div (#hcaptcha, [data-hcaptcha-widget-id])

        3. hCaptcha response textarea

        """

        return bool(self._js("""

            (() => {

                // Signal 1: iframe with hcaptcha/newassets in src or title

                const frames = document.querySelectorAll('iframe');

                for (const f of frames) {

                    const src = (f.getAttribute('src') || f.src || '').toLowerCase();

                    const title = (f.getAttribute('title') || f.title || '').toLowerCase();

                    if (src.includes('hcaptcha') || src.includes('newassets') || title.includes('hcaptcha')) {

                        const rect = f.getBoundingClientRect();

                        if (rect.width > 0 && rect.height > 0) return true;

                    }

                }

                // Signal 2: hCaptcha container elements

                if (document.querySelector('[data-hcaptcha-widget-id]')) return true;

                if (document.querySelector('#hcaptcha')) return true;

                if (document.querySelector('.h-captcha')) return true;

                // Signal 3: hCaptcha response textarea (injected by the script)

                const textareas = document.querySelectorAll('textarea');

                for (const ta of textareas) {

                    const name = (ta.getAttribute('name') || '').toLowerCase();

                    if (name.includes('hcaptcha') || name.includes('h-captcha-response')) return true;

                }

                return false;

            })()

        """))

    def _extract_token(self) -> Optional[str]:

        """Extract Discord token from localStorage.

        Discord stores token as: localStorage['token'] = '"MTQ4NzU1..."'

        The value has embedded quotes that need stripping.

        """

        raw = self._js("localStorage.getItem('token')")

        token = self._clean_token(raw)

        if token:

            return token

        raw = self._js("""

            (function() {

                for (var i = 0; i < localStorage.length; i++) {

                    var k = localStorage.key(i);

                    var v = localStorage.getItem(k) || '';

                    v = v.replace(/"/g, '').trim();

                    if (v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1 && v.indexOf('<') === -1) return v;

                }

                return null;

            })()

        """)

        token = self._clean_token(raw)

        if token:

            return token

        return None

    @staticmethod

    def _clean_token(raw) -> Optional[str]:

        """Validate and clean a raw token value."""

        if raw is None:

            return None

        if not isinstance(raw, str):

            raw = str(raw)

        token = raw.strip().strip('"').strip("'").strip()

        if len(token) > 50 and '.' in token and '{' not in token and '<' not in token and not token.startswith('('):

            return token

        return None

    def _create_email(self, worker_id: int) -> Tuple[Optional[str], str]:

        """Generate email based on selected provider.

        

        Supports: CyberTemp, Mailcow, Zeus, Hotmail007, Lution.

        Features: Fast Mails (pre-buying pool), Wait for Restock (infinite retry), Multi Buy (provider fallback).

        """

        email_providers = self.config.get("email_providers") or {}

        email = None

        email_address = ""

        email_password = self.password

        fast_mails = self.config.get("fast_mails") or {}

        if fast_mails.get("enabled", False):

            try:

                from .email_pool import EmailPool

                pool = EmailPool.instance()

                account = pool.get_email(worker_id=worker_id, timeout=120)

                if account:

                    self._zeus_refresh_token = account.get('refresh_token', '')

                    self._zeus_client_id = account.get('client_id', '')

                    return account['email'], account['password']

                else:

                    Logger.STATUS = f"{MskColor.RED}Email pool exhausted"

                    Logger.queue_log(worker_id=worker_id)

                    return None, email_password

            except Exception as e:

                Logger.STATUS = f"{MskColor.RED}Email pool error: {str(e)[:60]}"

                Logger.queue_log(worker_id=worker_id)

        restock_wait = self.config.get("restock_wait", False)

        if email_providers.get("cybertemp", {}).get("enabled", False):

            cybertemp_key = email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", "")

            domain = email_providers.get("cybertemp", {}).get("domain", "random")

            if not domain or domain == "random":

                try:

                    from ..Helper.mail import MskMailApi as _MailApiBr

                    _api_tmp_br = _MailApiBr(api_key=cybertemp_key)

                    _domains_br = _api_tmp_br.get_domains(domain_type="discord")

                    domain = random.choice(_domains_br) if _domains_br else Utils.get_domain()

                except Exception:

                    domain = Utils.get_domain()

            use_real_usernames = self.config.get("real_usernames", False)

            username = Utils.generate_real_username(use_api=use_real_usernames)

            email_address = f"{username}@{domain}"

            try:

                from ..Helper.mail import MskMailApi

                email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)

                Logger.STATUS = f"{MskColor.PRIMARY}CyberTemp email created: {email}"

                Logger.queue_log(worker_id=worker_id)

            except Exception as mail_err:

                Logger.STATUS = f"{MskColor.RED}CyberTemp email creation failed: {str(mail_err)[:60]}"

                Logger.queue_log(worker_id=worker_id)

                email = email_address

        elif email_providers.get("mailcow", {}).get("enabled", False):

            mc = email_providers.get("mailcow", {})

            host_url = mc.get("host_url", "")

            if host_url and not host_url.startswith("http"):

                host_url = f"https://{host_url}"

            api_key = mc.get("api_key", "")

            domain = mc.get("domain", "").strip()

            if not domain:

                Logger.STATUS = f"{MskColor.RED}Mailcow domain not configured."

                Logger.queue_log(worker_id=worker_id)

                return None, email_password

            try:

                from ..Helper.mail import MailcowApi

                mailcow_api = MailcowApi(host_url=host_url, api_key=api_key)

                use_real_usernames = self.config.get("real_usernames", False)

                username = Utils.generate_real_username(use_api=use_real_usernames)

                email_address = f"{username}@{domain}"

                email = mailcow_api.create_account(email=email_address, password=email_password)

                if email:

                    Logger.STATUS = f"{MskColor.PRIMARY}Mailcow email created: {email}"

                    Logger.queue_log(worker_id=worker_id)

                else:

                    email = email_address

            except Exception as mail_err:

                Logger.STATUS = f"{MskColor.RED}Mailcow error: {str(mail_err)[:60]}"

                Logger.queue_log(worker_id=worker_id)

                email = email_address

        elif email_providers.get("duckmail", {}).get("enabled", False):

            dm = email_providers.get("duckmail", {})

            dm_key = dm.get("api_key", "")

            domain = dm.get("domain", "").strip()

            try:

                from ..Helper.mail import DuckMailApi

                import random as _random

                duck_api = DuckMailApi(api_key=dm_key)

                if not domain:

                    domains = duck_api.get_domains() or []

                    domain = _random.choice(domains) if domains else ""

                if not domain:

                    Logger.STATUS = f"{MskColor.RED}DuckMail: no domain available"

                    Logger.queue_log(worker_id=worker_id)

                    return None, email_password

                use_real_usernames = self.config.get("real_usernames", False)

                username = Utils.generate_real_username(use_api=use_real_usernames)

                email_address = f"{username}@{domain}"

                email = duck_api.create_account(email=email_address, password=email_password)

                Logger.STATUS = f"{MskColor.PRIMARY}DuckMail email created: {email}"

                Logger.queue_log(worker_id=worker_id)

            except Exception as mail_err:

                Logger.STATUS = f"{MskColor.RED}DuckMail error: {str(mail_err)[:60]}"

                Logger.queue_log(worker_id=worker_id)

                email = email_address

        elif email_providers.get("zeus", {}).get("enabled", False):

            zeus_config = email_providers.get("zeus", {})

            from ..Helper.mail import ZeusApi

            zeus_api = ZeusApi(api_key=zeus_config.get("api_key", ""), account_type=zeus_config.get("account_type", "HOTMAIL"))

            while True:

                try:

                    account_data = zeus_api.create_account()

                    if account_data:

                        email = account_data['email']

                        email_password = account_data['password']

                        Logger.STATUS = f"{MskColor.PRIMARY}Zeus account purchased: {email}"

                        Logger.queue_log(worker_id=worker_id)

                        self._zeus_refresh_token = account_data.get('refresh_token', '')

                        self._zeus_client_id = account_data.get('client_id', '')

                        break

                    elif not restock_wait:

                        return None, email_password

                    else:

                        Logger.STATUS = f"{MskColor.YELLOW}Zeus no stock, waiting for restock..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                except Exception as mail_err:

                    err_str = str(mail_err).lower()

                    is_stock = any(kw in err_str for kw in ['insufficient', 'stock', 'quantity'])

                    if is_stock and restock_wait:

                        Logger.STATUS = f"{MskColor.YELLOW}Zeus no stock, retrying..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                        continue

                    elif is_stock:

                        Logger.STATUS = f"{MskColor.RED}Zeus no stock"

                    else:

                        Logger.STATUS = f"{MskColor.RED}Zeus error: {str(mail_err)[:60]}"

                    Logger.queue_log(worker_id=worker_id)

                    return None, email_password

        elif email_providers.get("hotmail007", {}).get("enabled", False):

            h007_config = email_providers.get("hotmail007", {})

            from ..Helper.mail import Hotmail007Api

            h007_api = Hotmail007Api(api_key=h007_config.get("api_key", ""), mail_type=h007_config.get("mail_type", "hotmail"))

            while True:

                try:

                    account_data = h007_api.create_account()

                    if account_data:

                        email = account_data['email']

                        email_password = account_data['password']

                        Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007 account purchased: {email}"

                        Logger.queue_log(worker_id=worker_id)

                        self._zeus_refresh_token = account_data.get('refresh_token', '')

                        self._zeus_client_id = account_data.get('client_id', '')

                        break

                    elif not restock_wait:

                        return None, email_password

                    else:

                        Logger.STATUS = f"{MskColor.YELLOW}Hotmail007 no stock, waiting for restock..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                except Exception as mail_err:

                    err_str = str(mail_err).lower()

                    is_stock = any(kw in err_str for kw in ['insufficient', 'stock', 'quantity'])

                    if is_stock and restock_wait:

                        Logger.STATUS = f"{MskColor.YELLOW}Hotmail007 no stock, retrying..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                        continue

                    elif is_stock:

                        Logger.STATUS = f"{MskColor.RED}Hotmail007 no stock"

                    else:

                        Logger.STATUS = f"{MskColor.RED}Hotmail007 error: {str(mail_err)[:60]}"

                    Logger.queue_log(worker_id=worker_id)

                    return None, email_password

        elif email_providers.get("lution", {}).get("enabled", False):

            lution_config = email_providers.get("lution", {})

            from ..Helper.mail import LutionApi

            lution_api = LutionApi(api_key=lution_config.get("api_key", ""), category=lution_config.get("account_type", "hotmail"))

            while True:

                try:

                    account_data = lution_api.create_account()

                    if account_data:

                        email = account_data['email']

                        email_password = account_data['password']

                        Logger.STATUS = f"{MskColor.PRIMARY}Lution account purchased: {email}"

                        Logger.queue_log(worker_id=worker_id)

                        self._zeus_refresh_token = account_data.get('refresh_token', '')

                        self._zeus_client_id = account_data.get('client_id', '')

                        break

                    elif not restock_wait:

                        return None, email_password

                    else:

                        Logger.STATUS = f"{MskColor.YELLOW}Lution no stock, waiting for restock..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                except Exception as mail_err:

                    err_str = str(mail_err).lower()

                    is_stock = any(kw in err_str for kw in ['stock', 'quantity'])

                    if is_stock and restock_wait:

                        Logger.STATUS = f"{MskColor.YELLOW}Lution no stock, retrying..."

                        Logger.queue_log(worker_id=worker_id)

                        time.sleep(2)

                        continue

                    elif is_stock:

                        Logger.STATUS = f"{MskColor.RED}Lution no stock"

                    else:

                        Logger.STATUS = f"{MskColor.RED}Lution error: {str(mail_err)[:60]}"

                    Logger.queue_log(worker_id=worker_id)

                    return None, email_password

        else:

            cybertemp_key = self.config.get("cybertemp_api_key", "")

            domain = (self.config.get("email_providers") or {}).get("cybertemp", {}) or {}

            domain = domain.get("domain", "random")

            if not domain or domain == "random":

                try:

                    from ..Helper.mail import MskMailApi as _MailApiBr2

                    _api_tmp_br2 = _MailApiBr2(api_key=cybertemp_key)

                    _domains_br2 = _api_tmp_br2.get_domains(domain_type="discord")

                    domain = random.choice(_domains_br2) if _domains_br2 else Utils.get_domain()

                except Exception:

                    domain = Utils.get_domain()

            use_real_usernames = self.config.get("real_usernames", False)

            username = Utils.generate_real_username(use_api=use_real_usernames)

            email_address = f"{username}@{domain}"

            try:

                from ..Helper.mail import MskMailApi

                email = MskMailApi(api_key=cybertemp_key).create_account(email=email_address, password=email_password)

            except Exception:

                email = email_address

        if not email:

            email = email_address if email_address else f"{Utils.random_string()}@{Utils.get_domain()}"

        return email, email_password

    def _fill_field(self, selectors_js: str, value: str, field_name: str, worker_id: int) -> bool:

        """Fill a single React-controlled input field.

        Uses the _valueTracker reset hack so React's controlled-component

        state actually picks up the programmatic value change.

        Fully synchronous -- no async/await -- so ZenDriver evaluate()

        returns the result directly.

        """

        safe_val = value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("`", "\\`").replace("\n", "\\n")

        result = self._js(f"""

            (() => {{

                const selectors = {selectors_js};

                let el = null;

                for (const sel of selectors) {{

                    try {{

                        const candidate = document.querySelector(sel);

                        if (candidate && candidate.offsetParent !== null) {{

                            el = candidate;

                            break;

                        }}

                    }} catch(e) {{}}

                }}

                if (!el) {{

                    // Last resort: search ALL visible inputs

                    const allInputs = document.querySelectorAll('input');

                    for (const inp of allInputs) {{

                        const rect = inp.getBoundingClientRect();

                        if (rect.width <= 0 || rect.height <= 0) continue;

                        const name = (inp.name || '').toLowerCase();

                        const ph = (inp.placeholder || '').toLowerCase();

                        const label = (inp.getAttribute('aria-label') || '').toLowerCase();

                        const fieldLower = '{field_name}'.toLowerCase();

                        if (name.includes(fieldLower) || ph.includes(fieldLower) || label.includes(fieldLower)) {{

                            el = inp;

                            break;

                        }}

                    }}

                }}

                if (!el) return 'NOT_FOUND';

                el.scrollIntoView({{block: 'center', behavior: 'instant'}});

                el.focus();

                el.click();

                const nativeSetter = Object.getOwnPropertyDescriptor(

                    window.HTMLInputElement.prototype, 'value'

                ).set;

                nativeSetter.call(el, '{safe_val}');

                // React tracks input values internally via _valueTracker.

                // If we don't reset it, React thinks the value hasn't changed

                // and silently ignores the dispatched input/change events.

                const tracker = el._valueTracker;

                if (tracker) {{

                    tracker.setValue('');  // Force React to see a "change"

                }}

                el.dispatchEvent(new Event('input', {{ bubbles: true }}));

                el.dispatchEvent(new Event('change', {{ bubbles: true }}));

                return el.value === '{safe_val}' ? 'OK' : 'VALUE_MISMATCH';

            }})()

        """)

        if result == 'NOT_FOUND':

            Logger.STATUS = f"{MskColor.RED}Field '{field_name}' not found on page"

            Logger.queue_log(worker_id=worker_id)

            return False

        elif result == 'VALUE_MISMATCH':

            Logger.STATUS = f"{MskColor.YELLOW}Field '{field_name}' value didn't persist"

            Logger.queue_log(worker_id=worker_id)

            return False

        elif result == 'OK':

            return True

        else:

            Logger.STATUS = f"{MskColor.YELLOW}Field '{field_name}' result: {str(result)[:60]}"

            Logger.queue_log(worker_id=worker_id)

            return False

    def _fill_form(self, email: str, username: str, worker_id: int):

        """Fill Discord registration form field by field, then immediately submit.

        Each field is filled in a separate synchronous JS call with

        React _valueTracker reset to ensure controlled components

        pick up the programmatic value changes.

        After DOB is selected the submit button is clicked in the same

        async JS call so there is no extra round-trip delay.

        """

        display_name = username[:8]

        self._fill_field(

            '["input[name=\\"email\\"]", "input[type=\\"email\\"]", "input[autocomplete=\\"email\\"]", "input[placeholder*=\\"email\\" i]", "input[aria-label*=\\"email\\" i]"]',

            email, "email", worker_id

        )

        time.sleep(0.1)

        self._fill_field(

            '["input[name=\\"global_name\\"]", "input[name=\\"display_name\\"]", "input[name=\\"displayName\\"]", "input[aria-label*=\\"display\\" i]", "input[placeholder*=\\"display\\" i]"]',

            display_name, "display", worker_id

        )

        time.sleep(0.1)

        self._fill_field(

            '["input[name=\\"username\\"]", "input[autocomplete=\\"username\\"]", "input[aria-label*=\\"username\\" i]", "input[placeholder*=\\"username\\" i]"]',

            username, "username", worker_id

        )

        time.sleep(0.1)

        self._fill_field(

            '["input[name=\\"password\\"]", "input[type=\\"password\\"]", "input[autocomplete=\\"new-password\\"]", "input[aria-label*=\\"password\\" i]", "input[placeholder*=\\"password\\" i]"]',

            self.password, "password", worker_id

        )

        time.sleep(0.15)

        month_idx = random.randint(0, 11)

        day = str(random.randint(1, 28))

        year = str(random.randint(1995, 2007))

        self._js(f"""

        (async () => {{

            const delay = ms => new Promise(r => setTimeout(r, ms));

            const selectOption = async (dropdownLabelRegex, targetValue, isIndex = false) => {{

                const allElements = Array.from(document.querySelectorAll('*'));

                let btn = allElements.find(el => {{

                    const label = el.getAttribute('aria-label') || '';

                    return dropdownLabelRegex.test(label) && (el.getAttribute('role') === 'button' || el.hasAttribute('aria-haspopup'));

                }});

                if (!btn) {{

                    const textElem = allElements.find(el => dropdownLabelRegex.test(el.innerText) && (el.tagName === 'SPAN' || el.tagName === 'DIV'));

                    if (textElem) btn = textElem.closest('[role="button"], [aria-haspopup="listbox"], [class*="container"]');

                }}

                if (!btn) {{

                    const clickable = allElements.find(el => {{

                        const text = (el.innerText || '').trim();

                        return dropdownLabelRegex.test(text) && el.offsetParent !== null

                            && (el.tagName === 'DIV' || el.tagName === 'SPAN')

                            && el.getBoundingClientRect().width > 30;

                    }});

                    if (clickable) btn = clickable.closest('[class*="css-"]') || clickable;

                }}

                if (!btn) return false;

                btn.scrollIntoView({{behavior: 'instant', block: 'center'}});

                btn.click();

                await delay(200);

                let options = Array.from(document.querySelectorAll('[role="option"]'));

                if (options.length === 0) return false;

                if (isIndex) {{

                    const target = options[targetValue - 1];

                    if (target) {{ target.scrollIntoView({{block:'nearest'}}); target.click(); return true; }}

                    return false;

                }}

                // Exact match only -- avoid partial matches
                let target = options.find(o => o.innerText.trim() === targetValue);

                if (target) {{ target.scrollIntoView({{block:'nearest'}}); target.click(); return true; }}

                let container = null;

                let el = options[0];

                while (el && el !== document.body) {{

                    const s = window.getComputedStyle(el);

                    if (s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflow === 'auto' || s.overflow === 'scroll') {{

                        container = el; break;

                    }}

                    el = el.parentElement;

                }}

                if (!container) return false;

                // Reset scroll to top to scan complete list
                container.scrollTop = 0;
                await delay(80);

                for (let i = 0; i < 250; i++) {{

                    options = Array.from(document.querySelectorAll('[role="option"]'));

                    target = options.find(o => o.innerText.trim() === targetValue);

                    if (target) break;

                    container.scrollTop += 120;

                    await delay(25);

                }}

                if (!target) return false;

                target.scrollIntoView({{block: 'nearest'}});

                await delay(40);

                target.click();

                return true;

            }};

            await selectOption(/Month|Maand|Mois|Mes|Mês|Mese|Monat/i, {month_idx + 1}, true);

            await delay(100);

            await selectOption(/Day|Dag|Jour|Día|Dia|Giorno|Tag/i, "{day}");

            await delay(100);

            await selectOption(/Year|Jaar|Année|Año|Ano|Anno|Jahr/i, "{year}");

            await delay(150);

            await delay(150);

            // Handle Terms of Service / consent checkbox -- multi-language, multi-country

            try {{

                const tosKw = [

                    'terms of service', 'terms and conditions', 'privacy policy',

                    'nutzungsbedingungen', 'datenschutz',

                    'condiciones de uso', 'privacidad',

                    'conditions utilisation', 'politique confidentialite',

                    'termini di servizio', 'informativa sulla privacy',

                    'termos de servico', 'politica de privacidade',

                    'gebruiksvoorwaarden', 'privacybeleid',

                    'warunki korzystania', 'polityka prywatnosci',

                    'kullanim kosullari', 'gizlilik politikasi',

                    'syarat layanan', 'kebijakan privasi',

                    'agree', 'consent', 'accept', 'i agree', 'i accept',

                    'setuju', 'kabul', 'akzeptiere', 'acepto'

                ];

                const hasTos = (el) => {{

                    const t = (el.innerText || el.textContent || '').toLowerCase();

                    return tosKw.some(kw => t.includes(kw));

                }};

                const clickCb = (cb) => {{

                    if (cb && !cb.checked) {{

                        cb.scrollIntoView({{block: 'center'}});

                        cb.click();

                    }}

                }};

                // Strategy 1: label with TOS text containing a checkbox

                for (const lbl of Array.from(document.querySelectorAll('label'))) {{

                    if (!hasTos(lbl)) continue;

                    const cb = lbl.querySelector('input[type="checkbox"]');

                    if (cb) {{

                        clickCb(cb); await delay(80);

                        if (!cb.checked) {{ cb.click(); await delay(80); }}

                    }} else {{

                        lbl.scrollIntoView({{block: 'center'}}); lbl.click(); await delay(150);

                    }}

                    break;

                }}

                // Strategy 2: unchecked checkbox whose parent or next sibling has TOS text

                for (const cb of Array.from(document.querySelectorAll('input[type="checkbox"]'))) {{

                    if (cb.checked) continue;

                    const par = cb.closest('label,div,li,p,span') || cb.parentElement;

                    if ((par && hasTos(par)) || (cb.nextElementSibling && hasTos(cb.nextElementSibling))) {{

                        clickCb(cb); await delay(80); break;

                    }}

                }}

            }} catch(e) {{}}

            // Click Create Account immediately after DOB is set

            const submitBtn = document.querySelector('button[type="submit"]');

            if (submitBtn) {{

                const r = submitBtn.getBoundingClientRect();

                if (r.width > 0 && r.height > 0) {{

                    submitBtn.scrollIntoView({{block: 'center'}});

                    submitBtn.click();

                    return;

                }}

            }}

            const keywords = ['create account', 'continue', 'register', 'sign up', 'submit'];

            const allButtons = document.querySelectorAll('button, div[role="button"]');

            for (const btn of allButtons) {{

                const text = (btn.innerText || '').trim().toLowerCase();

                const rect = btn.getBoundingClientRect();

                if (rect.width <= 0 || rect.height <= 0) continue;

                for (const kw of keywords) {{

                    if (text.includes(kw)) {{

                        btn.scrollIntoView({{block: 'center'}});

                        btn.click();

                        return;

                    }}

                }}

            }}

        }})();

        """)

    def _submit_form(self, worker_id: int = 0):

        """Click the Create Account / submit button.

        Uses multiple strategies:

        1. button[type="submit"]

        2. Button containing text "Create Account" / "Continue" / "Register"

        3. Any large visible button at the bottom of the form

        """

        result = self._js("""

            (() => {

                // Strategy 1: Standard submit button

                const submitBtn = document.querySelector('button[type="submit"]');

                if (submitBtn) {

                    const rect = submitBtn.getBoundingClientRect();

                    if (rect.width > 0 && rect.height > 0) {

                        submitBtn.scrollIntoView({block: 'center'});

                        submitBtn.click();

                        return 'submit_btn';

                    }

                }

                // Strategy 2: Button by text content

                const keywords = ['create account', 'continue', 'register', 'sign up', 'submit'];

                const allButtons = document.querySelectorAll('button, div[role="button"]');

                for (const btn of allButtons) {

                    const text = (btn.innerText || '').trim().toLowerCase();

                    const rect = btn.getBoundingClientRect();

                    if (rect.width <= 0 || rect.height <= 0) continue;

                    for (const kw of keywords) {

                        if (text.includes(kw)) {

                            btn.scrollIntoView({block: 'center'});

                            btn.click();

                            return 'text_btn:' + kw;

                        }

                    }

                }

                // Strategy 3: Any large button that looks like a primary action

                let bestBtn = null;

                let bestArea = 0;

                for (const btn of allButtons) {

                    const rect = btn.getBoundingClientRect();

                    if (rect.width <= 100 || rect.height <= 30) continue;

                    const area = rect.width * rect.height;

                    // Must be in the lower half of the viewport

                    if (rect.top < window.innerHeight * 0.4) continue;

                    if (area > bestArea) {

                        bestArea = area;

                        bestBtn = btn;

                    }

                }

                if (bestBtn) {

                    bestBtn.scrollIntoView({block: 'center'});

                    bestBtn.click();

                    return 'large_btn';

                }

                return 'not_found';

            })()

        """)

        if result and result != 'not_found':

            pass

        else:

            Logger.STATUS = f"{MskColor.RED}Submit button not found -- retrying with click..."

            Logger.queue_log(worker_id=worker_id)

            self._js("""

                (() => {

                    const active = document.activeElement;

                    if (active) {

                        active.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));

                        active.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));

                    }

                })()

            """)

    def _verify_email_browser(self, verification_url: str, worker_id: int, timeout: int = 90) -> bool:

        """Navigate to verification link and solve captcha if needed."""

        try:

            resolved_url = verification_url

            if 'click.discord.com' in verification_url:
                try:
                    import requests as req
                    _proxies = None
                    if getattr(self, '_proxy_data', None) and self._proxy_data.get('server'):
                        _s = self._proxy_data['server']
                        _u = self._proxy_data.get('username', '')
                        _p = self._proxy_data.get('password', '')
                        _host = _s.split('://')[-1]
                        _p_url = f'http://{_u}:{_p}@{_host}' if _u and _p else f'http://{_host}'
                        _proxies = {'http': _p_url, 'https': _p_url}
                    _ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                    resp = req.get(verification_url, allow_redirects=False, timeout=10, headers={'User-Agent': _ua}, proxies=_proxies)
                    loc = resp.headers.get('Location', '')
                    if loc and 'discord.com' in loc:
                        resolved_url = loc
                except Exception:
                    resolved_url = verification_url

            import json as _nav_json

            # Use CDP Page.navigate instead of JS window.location.href to avoid
            # triggering the Chromium "Save password?" bubble which freezes the browser.
            try:
                import truedriver.cdp.page as _page_ev_nav
                self._run(self._tab.send(_page_ev_nav.navigate(resolved_url)), timeout=15)
            except Exception:
                # Fallback to JS navigation if CDP navigate fails
                self._js(f"window.location.href = {_nav_json.dumps(resolved_url)};")

            # Wait for page to load -- poll instead of fixed sleep

            _load_start = time.time()

            while time.time() - _load_start < 8:

                ready = self._js("document.readyState")

                if ready == 'complete':

                    break

                time.sleep(0.3)

            time.sleep(0.5)

            auto_solve = self.config.get("auto_solver_captcha", False)

            _solver_ai = self.config.get("solver_ai") or {}

            success_keywords = ["done", "verified", "email verified", "you're all set", "success", "verification successful"]

            def _page_verified() -> bool:

                """Single fast check: page text OR URL indicates success."""

                try:

                    raw = self._js("document.body.innerText")

                    if raw and any(kw in str(raw).lower() for kw in success_keywords):

                        return True

                except Exception:

                    pass

                try:

                    url = str(self._js("window.location.href") or "").lower()

                    if '/channels' in url or '/@me' in url:

                        return True

                except Exception:

                    pass

                return False

            # Click the "Verify Email" button -- poll until found or timeout

            _btn_found = False

            for _vatt in range(12):

                if _page_verified():

                    Logger.STATUS = f"{MskColor.GREEN}Email verified!"

                    Logger.queue_log(worker_id=worker_id)

                    return True

                _clicked = self._js("""

                    (() => {

                        const keywords = ['verify email', 'verify', 'confirm email', 'confirm'];

                        const els = document.querySelectorAll(

                            'button, a, div[role="button"], span[role="button"]');

                        for (const el of els) {

                            const text = (el.innerText || el.textContent || '').trim().toLowerCase();

                            const rect = el.getBoundingClientRect();

                            if (rect.width <= 0 || rect.height <= 0) continue;

                            for (const kw of keywords) {

                                if (text.includes(kw)) {

                                    el.scrollIntoView({block: 'center'});

                                    el.click();

                                    return 'clicked:' + kw;

                                }

                            }

                        }

                        const sb = document.querySelector('button[type="submit"]');

                        if (sb) {

                            const r = sb.getBoundingClientRect();

                            if (r.width > 0 && r.height > 0) { sb.click(); return 'submit'; }

                        }

                        return null;

                    })()

                """)

                if _clicked:

                    _btn_found = True

                    # After clicking button, poll for result quickly

                    for _ in range(20):

                        time.sleep(0.3)

                        if _page_verified():

                            Logger.STATUS = f"{MskColor.GREEN}Email verified!"

                            Logger.queue_log(worker_id=worker_id)

                            return True

                        if self._has_hcaptcha():

                            break

                    break

                time.sleep(0.5)

            start_time = time.time()

            while time.time() - start_time < timeout:

                if _page_verified():

                    Logger.STATUS = f"{MskColor.GREEN}Email verified!"

                    Logger.queue_log(worker_id=worker_id)

                    return True

                if self._has_hcaptcha():

                    if _any_solver:

                        _email_cap_retries = getattr(self, '_email_cap_retries', 0)

                        if _email_cap_retries >= 3:

                            break

                        self._email_cap_retries = _email_cap_retries + 1

                        Logger.STATUS = f"{MskColor.YELLOW}Email captcha detected, solving..."

                        Logger.queue_log(worker_id=worker_id)

                        _cap_result = self._solve_hcaptcha_if_present(worker_id, _context='email_verify')

                        if _cap_result == 'FAILED':

                            break

                        # Poll quickly after captcha solve -- don't sleep a fixed amount

                        _post_cap = time.time()

                        while time.time() - _post_cap < 10:

                            time.sleep(0.2)

                            if _page_verified():

                                Logger.STATUS = f"{MskColor.GREEN}Email verified (captcha solved)!"

                                Logger.queue_log(worker_id=worker_id)

                                return True

                        continue

                    else:

                        Logger.STATUS = f"{MskColor.YELLOW}Email captcha detected, waiting for manual solve..."

                        Logger.queue_log(worker_id=worker_id)

                        while time.time() - start_time < timeout:

                            if _page_verified():

                                Logger.STATUS = f"{MskColor.GREEN}Email verified!"

                                Logger.queue_log(worker_id=worker_id)

                                return True

                            if not self._has_hcaptcha():

                                time.sleep(0.3)

                                break

                            time.sleep(0.5)

                time.sleep(0.2)

            return False

        except Exception as e:

            Logger.STATUS = f"{MskColor.RED}Verification Error: {str(e)[:60]}"

            Logger.queue_log(worker_id=worker_id)

            return False

    def _fire_smart_trigger(self, trigger_type: str):

        """Signal the smart multi-thread controller that this worker's trigger has fired."""

        smart_cfg = self.config.get('smart_multithread', {})

        if not smart_cfg.get('enabled'):

            return

        if smart_cfg.get('trigger', 'captcha_solved') == trigger_type:

            if not getattr(self, '_smart_trigger_fired', False):

                self._smart_trigger_fired = True

                parent = getattr(self, '_trigger_parent', None)

                if parent is not None:

                    parent._smart_trigger_fired = True

    def _solve_hcaptcha_if_present(self, worker_id: int, _context: str = 'register'):

        """Solve hCaptcha with captcha-loop detection.

        Returns:

            True           - captcha solved successfully

            False          - no captcha found / auto-solve disabled

            'FAILED'       - all strikes exhausted, caller should restart browser

            'CAPTCHA_LOOP' - captcha reappeared after MAX_LOOP_STRIKES solve attempts;

        """

        auto_solve = self.config.get("auto_solver_captcha", False)

        if not auto_solve:
            return False

        solver_ai = self.config.get("solver_ai") or {}

        text_ai_enabled = auto_solve and any(solver_ai.get(p, False) for p in ("cloudflare", "groq", "openrouter"))

        captcha_found = False

        for _ in range(20):

            if self._has_hcaptcha():

                captcha_found = True

                break

            time.sleep(0.5)

        if not captcha_found:
            return False

        # Wait for challenge to be ready -- handles both auto-triggered and checkbox flows

        _challenge_ready = False

        _checkbox_attempted = False

        _start = time.time()

        while time.time() - _start < 40:

            _state = self._js("""

                (() => {

                    const frames = document.querySelectorAll('iframe');

                    for (const f of frames) {

                        const src = (f.getAttribute('src') || '').toLowerCase();

                        if (!src.includes('hcaptcha')) continue;

                        const r = f.getBoundingClientRect();

                        if (r.height > 300) {

                            try {

                                const doc = f.contentDocument || f.contentWindow.document;

                                if (!doc) return 'ready';

                                const prompt = doc.querySelector('.prompt-text, h2.prompt-text, [id^="prompt-text"]');

                                if (prompt && prompt.innerText.trim().length > 3) return 'ready';

                                const imgs = doc.querySelectorAll('img');

                                let loaded = 0;

                                for (const img of imgs) {

                                    const r2 = img.getBoundingClientRect();

                                    if (r2.width > 30 && r2.height > 30 && img.complete) loaded++;

                                }

                                if (loaded >= 2) return 'ready';

                                const canvas = doc.querySelectorAll('canvas');

                                for (const c of canvas) {

                                    const r3 = c.getBoundingClientRect();

                                    if (r3.width > 50 && r3.height > 50) return 'ready';

                                }

                            } catch(e) {

                                // Cross-origin: contentDocument throws -- frame IS open

                                // but we can't peek inside. Treat as ready for text solver.

                                return 'ready';

                            }

                            // Large iframe visible but couldn't confirm content -- still ready

                            return 'ready';

                        } else if (r.height > 20 && r.height < 150 && r.width > 100) {

                            try {

                                const doc = f.contentDocument || f.contentWindow.document;

                                if (doc) {

                                    const cb = doc.querySelector('div#checkbox, #checkbox');

                                    if (cb && cb.getAttribute('aria-checked') === 'true') return 'checkbox_done';

                                }

                            } catch(e) {}

                            return 'has_checkbox';

                        }

                    }

                    return 'waiting';

                })()

            """)

            if _state == 'ready':

                _challenge_ready = True

                break

            elif _state == 'has_checkbox' and not _checkbox_attempted:

                _iframe_rect = self._js("""

                    (() => {

                        for (const f of document.querySelectorAll('iframe')) {

                            const src = (f.getAttribute('src') || '').toLowerCase();

                            if (src.includes('hcaptcha')) {

                                const r = f.getBoundingClientRect();

                                if (r.height > 20 && r.height < 150 && r.width > 100) {

                                    return r.x + ',' + r.y + ',' + r.width + ',' + r.height;

                                }

                            }

                        }

                        return '';

                    })()

                """)

                if _iframe_rect:

                    try:

                        _x, _y, _w, _h = map(float, _iframe_rect.split(','))

                        import truedriver.cdp.input_ as input_cdp

                        _cx = int(_x + 30)

                        _cy = int(_y + _h / 2)

                        self._run(self._tab.send(input_cdp.dispatch_mouse_event(

                            type_="mousePressed", x=_cx, y=_cy, button=input_cdp.MouseButton.LEFT, click_count=1

                        )))

                        time.sleep(0.05)

                        self._run(self._tab.send(input_cdp.dispatch_mouse_event(

                            type_="mouseReleased", x=_cx, y=_cy, button=input_cdp.MouseButton.LEFT, click_count=1

                        )))

                    except Exception:

                        pass

                _checkbox_attempted = True

            elif _state == 'checkbox_done':

                _challenge_ready = True

                break

            time.sleep(1)

            

            # Only use URL/pass shortcuts in 'register' context.

            # In 'email_verify' the URL already contains '/verify', so

            # _check_passed() would match it and return True before the

            # challenge is actually solved — preventing the text solver from running.

            if _context == 'register':

                if self._check_passed():

                    return True

                url = self._js("window.location.href") or ""

                _has = self._has_hcaptcha()

                if ('check-your-email' in url or '/verify' in url or '/channels' in url) and not _has:

                    return True

        if _challenge_ready:
            # Don't log here - already logged by caller
            pass

        # ── Captcha loop detection setup ───────────────────────────────────────

        # solve strategies. After MAX_LOOP_STRIKES failures, returns 'CAPTCHA_LOOP'

        MAX_LOOP_STRIKES = 4

        _loop_strike = 0   # incremented each time a solve attempt ends with captcha still present

        Logger.queue_log(worker_id=worker_id)

        _nop_start = time.time()

        _last_interaction_check = _nop_start

        _nop_solved = False

        solved = self._js("""

            (() => {

                const ta = document.querySelector('textarea[name="h-captcha-response"]');

                if (ta && ta.value && ta.value.length > 20) return true;

                return false;

            })()

        """)

        if solved:

            Logger.queue_log(worker_id=worker_id)

            time.sleep(2)

            if self._has_hcaptcha():

                _loop_strike += 1

                Logger.queue_log(worker_id=worker_id)

                if _loop_strike >= MAX_LOOP_STRIKES:

                    Logger.STATUS = f"{MskColor.RED}captcha loop"

                    Logger.queue_log(worker_id=worker_id)

                    return "CAPTCHA_LOOP"

            else:
                _nop_solved = True

                return True

        if time.time() - _last_interaction_check > 35:

            # Check if the challenge iframe is still large and visible.

            # Cross-origin contentDocument access is blocked -- use geometry only.

            _is_interacting = self._js("""

                (() => {

                    const frames = document.querySelectorAll('iframe');

                    for (const f of frames) {

                        const src = (f.getAttribute('src') || '').toLowerCase();

                        if (!src.includes('hcaptcha')) continue;

                        const r = f.getBoundingClientRect();

                        if (r.width > 200 && r.height > 200) return true;

                    }

                    return false;

                })()

            """)

            if not _is_interacting:

                Logger.queue_log(worker_id=worker_id)

                return "FAILED"

            _last_interaction_check = time.time()

        if not self._has_hcaptcha():

            if self._check_passed():

                return True

            time.sleep(2)

            if self._check_passed():

                return True

        time.sleep(1)

        _loop_strike += 1

        Logger.queue_log(worker_id=worker_id)

        if _loop_strike >= MAX_LOOP_STRIKES:

            Logger.STATUS = f"{MskColor.RED}captcha loop"

            Logger.queue_log(worker_id=worker_id)

            return "CAPTCHA_LOOP"

        # ── Captcha loop detection ─────────────────────────────────────────────

        # MAX_STRIKES: total per-attempt retries

        MAX_STRIKES = 8

        text_solver_enabled = text_ai_enabled

        _solve_attempt_count = 0  # counts total text solve attempts in this call

        for strike in range(1, MAX_STRIKES + 1):

            if not self._has_hcaptcha():

                # Captcha is not visible -- wait and check if registration passed

                for _ in range(16):

                    if self._check_passed():

                        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved"

                        Logger.queue_log(worker_id=worker_id)

                        self._fire_smart_trigger('captcha_solved')

                        return True

                    time.sleep(0.5)

                url = self._js("window.location.href") or ""

                if any(k in url for k in ('check-your-email', '/verify', '/channels', '/@me', '/app')):

                    Logger.STATUS = f"{MskColor.GREEN}Captcha Solved"

                    Logger.queue_log(worker_id=worker_id)

                    self._fire_smart_trigger('captcha_solved')

                    return True

                if _context == 'register' and 'register' in url:

                    Logger.STATUS = f"{MskColor.YELLOW}Captcha dismissed, re-submitting form (strike {strike}/{MAX_STRIKES})..."

                    Logger.queue_log(worker_id=worker_id)

                    self._submit_form(worker_id=worker_id)

                    time.sleep(2)

                else:

                    time.sleep(1)

                reappeared = False

                for _ in range(12):

                    if self._has_hcaptcha():

                        reappeared = True

                        break

                    if self._check_passed():

                        return True

                    time.sleep(0.5)

                if not reappeared:

                    if self._check_passed():

                        return True

                    continue

            if text_solver_enabled:

                _solve_attempt_count += 1

                try:

                    from .text_solver_truedriver import TruedriverTextSolver

                    ts = TruedriverTextSolver(self, worker_id)

                    ts_result = ts.solve()

                    if ts_result > 0:

                        self._fire_smart_trigger('captcha_solved')

                        # Check if captcha reappeared after a successful text solve

                        time.sleep(1.0)

                        if self._has_hcaptcha():

                            _loop_strike += 1

                            Logger.STATUS = f"{MskColor.YELLOW}Captcha reappeared after text solve (loop {_loop_strike}/{MAX_LOOP_STRIKES})"

                            Logger.queue_log(worker_id=worker_id)

                            if _loop_strike >= MAX_LOOP_STRIKES:

                                Logger.STATUS = f"{MskColor.RED}captcha loop"

                                Logger.queue_log(worker_id=worker_id)

                                return "CAPTCHA_LOOP"

                            continue

                        return True

                    elif ts_result == -3.0:

                        Logger.STATUS = f"{MskColor.RED}AI provider blocked, falling back to manual..."

                        Logger.queue_log(worker_id=worker_id)

                    else:

                        pass

                except Exception as e:

                    Logger.STATUS = f"{MskColor.RED}Text Solver crashed: {str(e)}"

                    Logger.queue_log(worker_id=worker_id)

                # Even if solver returned failure, captcha might actually be solved

                time.sleep(0.5)

                if not self._has_hcaptcha():

                    time.sleep(0.5)

                    if self._check_passed():

                        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved"

                        Logger.queue_log(worker_id=worker_id)

                        self._fire_smart_trigger('captcha_solved')

                        return True

                    url = self._js("window.location.href") or ""

                    if 'check-your-email' in url or '/verify' in url or '/channels' in url:

                        Logger.STATUS = f"{MskColor.GREEN}Captcha Solved"

                        Logger.queue_log(worker_id=worker_id)

                        self._fire_smart_trigger('captcha_solved')

                        return True

                else:

                    # Captcha still present after text solve attempt -- check loop

                    _loop_strike += 1

                    if _loop_strike >= MAX_LOOP_STRIKES:

                        Logger.STATUS = f"{MskColor.RED}captcha loop"

                        Logger.queue_log(worker_id=worker_id)

                        return "CAPTCHA_LOOP"

            try:

                Logger.STATUS = f"{MskColor.YELLOW}Waiting for captcha to solved"

                Logger.queue_log(worker_id=worker_id)

                _cap_wait = time.time()

                while self._has_hcaptcha() and time.time() - _cap_wait < 120:

                    if self._check_passed():

                        return True

                    time.sleep(2)

                if self._check_passed():

                    return True

                # After waiting, if captcha is still there track the loop

                if self._has_hcaptcha():

                    _loop_strike += 1

                    if _loop_strike >= MAX_LOOP_STRIKES:

                        Logger.STATUS = f"{MskColor.RED}captcha loop"

                        Logger.queue_log(worker_id=worker_id)

                        return "CAPTCHA_LOOP"

            except Exception as e:

                err_str = str(e)

                if "VPN_BLOCKED" in err_str:

                    raise

                Logger.STATUS = f"{MskColor.RED}Captcha error (attempt {strike}): {err_str[:50]}"

                Logger.queue_log(worker_id=worker_id)

        Logger.STATUS = f"{MskColor.RED}Captcha failed after {MAX_STRIKES} attempts -- restarting browser..."

        Logger.queue_log(worker_id=worker_id)

        return "FAILED"

    @staticmethod

    def _censor_token(token: str) -> str:

        if not token or not isinstance(token, str):

            return "N/A"

        if len(token) > 20:

            return token[:6] + "*" * (len(token) - 10) + token[-4:]

        return token

    def print_stats(self, worker_id, token, elapsed_time, startup_time, hcap_wait, hcap_solve,

                    humanize_time, email_verify_time, phone_verify_time, phone_verified, humanize_status, ev_status):

        logs_cfg = self.config.get("logs") or {}

        display_token = token

        if logs_cfg.get("censor_token", False):

            display_token = self._censor_token(token)

        phone_status = f"{MskColor.GREEN}Phone Verified" if phone_verified else f"{MskColor.RED}Not Phone Verified"

        _show_data_usage = (self.config.get("proxies") or {}).get("enabled", False) or bool(self.config.get("data_saver", False))

        stats = [

            ("Token", display_token, True),

            ("Generation Time", f"{elapsed_time:.2f}s", logs_cfg.get("generation_time", True)),

            ("Browser Startup Time", f"{startup_time:.2f}s", logs_cfg.get("startup_time", False)),

            ("hCaptcha Waiting Time", f"{hcap_wait:.2f}s", logs_cfg.get("hcaptcha_waiting", False)),

            ("hCaptcha Solving Time", f"{hcap_solve:.2f}s", logs_cfg.get("hcaptcha_solving", True)),

            ("Humanize Time", f"{humanize_time:.2f}s", logs_cfg.get("humanize_time", True)),

            ("Email Verify Time", f"{email_verify_time:.2f}s", logs_cfg.get("verify_time", True)),

            ("Phone Verify Time", f"{phone_verify_time:.2f}s", logs_cfg.get("phone_verify_time", True)),

            ("Data Usage", f"{getattr(self, '_network_bytes', 0) / (1024 * 1024):.2f} MB", _show_data_usage),

            ("Total Time", f"{email_verify_time + humanize_time + elapsed_time + startup_time + phone_verify_time:.2f}s", logs_cfg.get("total_time", True)),

            ("Status", f"{humanize_status}, {ev_status}, {phone_status}", True)

        ]

        Logger.queue_stats(worker_id, stats)

    def register(self, worker_id: int, on_browser_closed=None) -> str:

        self.worker_id = worker_id

        wm, slot_idx = None, None

        try:

            from ..Utils.utils import rehabilitate_environment_paths, init_browserforge_path, ensure_truedriver_deps

            rehabilitate_environment_paths()

            init_browserforge_path()

            ensure_truedriver_deps()

            start_time_startup = time.time()

            headless_mode = self.config.get("headless", False)

            _text_solver = self.config.get("auto_solver_captcha", False)

            if headless_mode and not _text_solver:
                Logger.STATUS = f"{MskColor.RED}You have to turn on any auto solver to use headless or turn it off"

                Logger.queue_log(worker_id=worker_id)

                return "HeadlessNoSolverSelected"

            Logger.STATUS = f"{MskColor.PRIMARY}Starting Brave Browser"

            Logger.queue_log(worker_id=worker_id)

            proxy_data = None

            if (self.config.get("proxies") or {}).get("enabled", False):

                proxy_data = self.proxy_manager.get_proxy(worker_id=worker_id)
                self._proxy_data = proxy_data

                if not proxy_data:

                    proxy_data = self.proxy_manager.wait_for_proxies(worker_id)

                if proxy_data:

                    if (self.config.get("proxies") or {}).get("remove_after_use", False):

                        if not (hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False)):

                            self.proxy_manager.remove_proxy(proxy_data)

                    server = proxy_data.get("server", "")

                    host_port = server.split("://")[-1]

                    username = proxy_data.get("username", "")

                    password = proxy_data.get("password", "")

                    full_proxy = f"{username}:{password}@{host_port}" if username and password else host_port

                    Logger.STATUS = f"{MskColor.PRIMARY}Using Proxy: {full_proxy} for thread {worker_id}"

                    Logger.queue_log(worker_id=worker_id)

            headless_mode = self.config.get("headless", False)

            

            wm = getattr(self.controller, '_wm', None) if hasattr(self, 'controller') and self.controller else None

            slot_idx, pos = None, None

            launch_lock_acquired = False

            if wm:

                slot_idx, pos = wm.acquire_slot()

                wm.launch_lock.acquire()

                launch_lock_acquired = True

            try:

                tab = self._create_browser(headless=headless_mode, proxy=proxy_data, wm_pos=pos)

                

                if wm:

                    import uuid

                    uid = str(uuid.uuid4())

                    try:

                        self._run(tab.get("about:blank"))

                        self._js(f"document.title = '{uid}';")

                        wm.find_and_register_by_title(uid, slot_idx, pos)

                    except:

                        pass

                

            finally:

                if wm and launch_lock_acquired:

                    try:

                        wm.launch_lock.release()

                        launch_lock_acquired = False

                    except:

                        pass

            self._extracted_token = None

            self._fingerprint = None

            import truedriver.cdp.network as net_cdp

            self._network_bytes = 0

            

            self._run(tab.send(net_cdp.enable()))

            async def data_listener(event: net_cdp.DataReceived):

                self._network_bytes += event.encoded_data_length

            tab.add_handler(net_cdp.DataReceived, data_listener)

            async def _global_token_listener(event: net_cdp.RequestWillBeSent):

                try:

                    headers = getattr(event.request, "headers", {})

                    for k, v in headers.items():

                        if k.lower() == 'authorization' and v:

                            raw_v = str(v).strip().strip('"').strip("'")

                            if len(raw_v) > 50 and '.' in raw_v and '{' not in raw_v:

                                self._extracted_token = raw_v

                        elif k.lower() == 'x-fingerprint' and v:

                            self._fingerprint = str(v).strip()

                except Exception:

                    pass

            tab.add_handler(net_cdp.RequestWillBeSent, _global_token_listener)

            if self.config.get("data_saver_enabled"):

                Logger.STATUS = f"{MskColor.PRIMARY}Data Saver Enabled: Cleaning Discord Data & Blocking Media..."

                Logger.queue_log(worker_id=worker_id)

                

                self._run(tab.send(net_cdp.clear_browser_cookies()))

                self._js("""

                    (() => {

                        try { localStorage.clear(); } catch(e) {}

                        try { sessionStorage.clear(); } catch(e) {}

                        try {

                            if (window.indexedDB) {

                                indexedDB.databases().then(dbs => {

                                    dbs.forEach(db => { try { indexedDB.deleteDatabase(db.name); } catch(e) {} });

                                }).catch(() => {});

                            }

                        } catch(e) {}

                    })()

                """)

                _BLOCKED_URLS = [

                    "*api/science*", "*sentry.io*", "*sentry-cdn*",

                    "*discord.com/api/*/track*", "*discord.com/api/*/experiments*",

                    "*discord.com/api/*/activities*",

                    "*.mp4*", "*.webm*", "*.mov*", "*.avi*",

                    "*discord.com/assets/*.png", "*discord.com/assets/*.jpg", "*discord.com/assets/*.webp",

                    "*discord.com/assets/*.svg", "*discord.com/assets/*.gif",

                    "*cdn.discordapp.com/*.png", "*cdn.discordapp.com/*.jpg", "*cdn.discordapp.com/*.webp",

                    "*cdn.discordapp.com/*.gif",

                    "*discord.com/api/*/tutorial*", "*discord.com/api/*/guild-discovery*",

                    "*discord.com/api/*/sticker*", "*discord.com/api/*/promotions*",

                    "*discord.com/api/*/outbound-promotions*",

                    "*discord.com/api/*/remote-auth*", "*discord.com/api/*/connections*",

                    "*fonts.googleapis.com*", "*fonts.gstatic.com*",

                    "*discord.com/assets/*.woff*", "*discord.com/assets/*.ttf*",

                ]

                self._run(tab.send(net_cdp.set_blocked_ur_ls(urls=_BLOCKED_URLS)))

                _JS_BLOCK_PATTERNS = [

                    "api/science", "sentry.io", "sentry-cdn",

                    "/api/v9/track", "/api/v9/experiments", "/api/v9/activities",

                    "/api/v9/tutorial", "/api/v9/guild-discovery", "/api/v9/sticker",

                    "/api/v9/promotions", "/api/v9/outbound-promotions",

                    "/api/v9/remote-auth", "/api/v9/connections",

                    "fonts.googleapis.com", "fonts.gstatic.com",

                ]

                _JS_SAFE_DOMAINS = [

                    "hcaptcha.com", "imgs.hcaptcha.com", "newassets.hcaptcha.com",

                ]

                import json as _json

                _patterns_json = _json.dumps(_JS_BLOCK_PATTERNS)

                _safe_json = _json.dumps(_JS_SAFE_DOMAINS)

                _js_blocker = f"""(function(){{

  try{{if(window.location&&window.location.hostname&&window.location.hostname.indexOf('hcaptcha.com')!==-1)return;}}catch(e){{}}

  var BLOCKED={_patterns_json};

  var SAFE={_safe_json};

  function isSafe(u){{return SAFE.some(function(s){{return u.indexOf(s)!==-1;}});}}

  function shouldBlock(u){{if(!u||isSafe(u))return false;var l=u.toLowerCase();return BLOCKED.some(function(p){{return l.indexOf(p)!==-1;}});}}

  try{{

    var oFetch=window.fetch;

    window.fetch=function(input,init){{

      var url=(typeof input==='string')?input:(input&&input.url?input.url:'');

      if(shouldBlock(url))return Promise.resolve(new Response('',{{status:204,statusText:'Blocked'}}));

      return oFetch.call(this,input,init);

    }};

  }}catch(e){{}}

  try{{

    var oOpen=XMLHttpRequest.prototype.open;

    XMLHttpRequest.prototype.open=function(m,url){{

      if(shouldBlock(String(url)))this.__msk_blocked=true;

      return oOpen.apply(this,arguments);

    }};

    var oSend=XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.send=function(){{

      if(this.__msk_blocked){{this.abort();return;}}

      return oSend.apply(this,arguments);

    }};

  }}catch(e){{}}

}})();"""

                try:

                    import truedriver.cdp.page as _page_cdp

                    self._run(tab.send(_page_cdp.add_script_to_evaluate_on_new_document(

                        source=_js_blocker

                    )))

                except Exception:

                    pass

            _fp_settings = self.config.get("fingerprint_settings", {})

            _use_custom_fp = _fp_settings.get("use_custom_fingerprint", False)

            if _use_custom_fp:

                try:

                    from ..Utils.custom_fingerprint import (

                        pop_custom_fingerprint,

                        extract_snowflake_from_fingerprint,

                        snowflake_to_age,

                    )

                    _custom_fp = pop_custom_fingerprint(self.config)

                    if _custom_fp:

                        self._fingerprint = _custom_fp

                        _snowflake = extract_snowflake_from_fingerprint(_custom_fp)

                        _age = snowflake_to_age(_snowflake)

                        _fp_preview = (_custom_fp[:36] + "...") if len(_custom_fp) > 36 else _custom_fp

                        Logger.STATUS = f"{MskColor.PRIMARY}Using custom fingerprint >> {_fp_preview} [{_age} old]"

                        Logger.queue_log(worker_id=worker_id)

                        _cdp_fetch_ok = False

                        try:

                            import truedriver.cdp.fetch as _fetch_cdp

                            _fp_capture = _custom_fp

                            async def _experiments_fp_interceptor(event: _fetch_cdp.RequestPaused):

                                try:

                                    _url = str(event.request.url) if event.request else ""

                                    if '/api/' in _url and '/experiments' in _url:

                                        import json as _fj, base64 as _fb64

                                        _resp = _fj.dumps({

                                            "fingerprint": _fp_capture,

                                            "assignments": [],

                                            "guild_experiments": []

                                        })

                                        await tab.send(_fetch_cdp.fulfill_request(

                                            request_id=event.request_id,

                                            response_code=200,

                                            response_headers=[

                                                _fetch_cdp.HeaderEntry(name="content-type", value="application/json")

                                            ],

                                            body=_fb64.b64encode(_resp.encode()).decode()

                                        ))

                                    else:

                                        await tab.send(_fetch_cdp.continue_request(

                                            request_id=event.request_id

                                        ))

                                except Exception:

                                    try:

                                        await tab.send(_fetch_cdp.continue_request(

                                            request_id=event.request_id

                                        ))

                                    except Exception:

                                        pass

                            tab.add_handler(_fetch_cdp.RequestPaused, _experiments_fp_interceptor)

                            self._run(tab.send(_fetch_cdp.enable(

                                patterns=[_fetch_cdp.RequestPattern(url_pattern="*experiments*")]

                            )))

                            _cdp_fetch_ok = True

                        except Exception:

                            pass

                        # FALLBACK 1: Force x-fingerprint header at CDP network layer

                        # (in case Fetch domain is unavailable; CDP wins over JS-set headers)

                        try:

                            import truedriver.cdp.network as _net_cdp_fp

                            self._run(tab.send(_net_cdp_fp.set_extra_http_headers(

                                headers={"x-fingerprint": _custom_fp}

                            )))

                        except Exception:

                            pass

                        # FALLBACK 2: JS injection via addScriptToEvaluateOnNewDocument

                        # Overrides window.fetch in the page context before Discord's scripts run

                        import json as _cfp_json

                        _cfp_escaped = _cfp_json.dumps(_custom_fp)

                        _fp_inject_js = f"""(function(){{

  try{{if(window.location&&window.location.hostname&&window.location.hostname.indexOf('hcaptcha.com')!==-1)return;}}catch(e){{}}

  var _msk_cfp={_cfp_escaped};

  var _origFetch=window.fetch;

  window.fetch=function(input,init){{

    var url=(typeof input==='string')?input:(input&&input.url?input.url:'');

    if(url&&url.indexOf('/api/')!==-1&&url.indexOf('/experiments')!==-1){{

      var body=JSON.stringify({{fingerprint:_msk_cfp,assignments:[],guild_experiments:[]}});

      return Promise.resolve(new Response(body,{{status:200,headers:{{'Content-Type':'application/json'}}}}));

    }}

    return _origFetch.call(this,input,init);

  }};

}})();"""

                        try:

                            import truedriver.cdp.page as _page_cdp2

                            self._run(tab.send(_page_cdp2.add_script_to_evaluate_on_new_document(

                                source=_fp_inject_js

                            )))

                        except Exception:

                            pass

                except Exception:

                    pass

            elapsed_time_startup = time.time() - start_time_startup

            from ..Helper.mail import suppress_output

            

            with suppress_output():

                try:

                    curr_url = self._js("window.location.href") or ""

                    if "discord.com/register" not in curr_url:

                        self._js("window.location.href = 'https://discord.com/register';")

                except Exception:

                    pass

            time.sleep(1)

            start_wait = time.time()

            found_form = False

            while time.time() - start_wait < 60:

                form_ready = self._js("""

                    (() => {

                        // 1. Document must be fully loaded

                        if (document.readyState !== 'complete') return 'not_ready';

                        // 2. Email + password inputs must exist and be visible

                        const email = document.querySelector('input[name="email"]');

                        if (!email) return 'no_email';

                        const emailRect = email.getBoundingClientRect();

                        if (emailRect.width <= 0 || emailRect.height <= 0) return 'email_hidden';

                        const password = document.querySelector('input[name="password"]');

                        if (!password) return 'no_password';

                        const pwRect = password.getBoundingClientRect();

                        if (pwRect.width <= 0 || pwRect.height <= 0) return 'pw_hidden';

                        // 3. Check DOB dropdowns are present

                        const allEls = document.querySelectorAll('[role="button"], [aria-haspopup="listbox"]');

                        let hasDob = false;

                        for (const el of allEls) {

                            const label = (el.getAttribute('aria-label') || '').toLowerCase();

                            if (/month|maand|mois|mes|monat/i.test(label)) { hasDob = true; break; }

                        }

                        if (!hasDob) {

                            const selects = document.querySelectorAll('[class*="select"], [class*="listbox"]');

                            if (selects.length >= 3) hasDob = true;

                        }

                        if (!hasDob) return 'no_dob';

                        // 4. Verify React has hydrated — input must have React internals

                        const reactKeys = Object.keys(email);

                        const hasReact = reactKeys.some(k =>

                            k.startsWith('__reactFiber') ||

                            k.startsWith('__reactInternalInstance') ||

                            k.startsWith('__reactProps')

                        );

                        if (!hasReact) return 'react_pending';

                        // 5. Submit button must exist and be visible

                        const submitBtn = document.querySelector('button[type="submit"]');

                        if (!submitBtn) return 'no_submit';

                        const btnRect = submitBtn.getBoundingClientRect();

                        if (btnRect.width <= 0 || btnRect.height <= 0) return 'submit_hidden';

                        return 'ready';

                    })()

                """)

                if form_ready == 'ready':

                    found_form = True

                    self._fire_smart_trigger('page_load')

                    break

                time.sleep(1)

            if not found_form:

                has_input = self._js("""

                    (() => {

                        const el = document.querySelector('input[name="email"]');

                        if (!el) return false;

                        const rect = el.getBoundingClientRect();

                        return rect.width > 0 && rect.height > 0;

                    })()

                """)

                if has_input:

                    found_form = True

                    Logger.STATUS = f"{MskColor.YELLOW}DOB dropdowns not detected, proceeding anyway"

                    Logger.queue_log(worker_id=worker_id)

                else:

                    raw_text = self._js("document.body.innerText")

                    page_text = str(raw_text).lower() if raw_text else ""

                    if any(kw in page_text for kw in ["403", "access denied", "cloudflare", "checking your browser"]):

                        Logger.STATUS = f"{MskColor.RED}Discord blocked this IP. Try different proxy/VPN."

                        Logger.queue_log(worker_id=worker_id)

                        return "RateLimited"

                    if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):

                        return "RateLimited"

                    Logger.STATUS = f"{MskColor.RED}Registration form not found"

                    Logger.queue_log(worker_id=worker_id)

                    return "RateLimited"

            if hasattr(self, 'controller') and getattr(self.controller, 'should_stop', False):

                return "RateLimited"

                

            time.sleep(0.5)

            start_time = time.time()

            Logger.STATUS = f"{MskColor.SECONDARY}Filling Form"

            Logger.queue_log(worker_id=worker_id)

            email_address, email_password = self._create_email(worker_id)

            if not email_address:

                return "Invalid"

            discord_username = Utils.sanitize_username(Utils.random_string())

            self._fill_form(email_address, discord_username, worker_id)

            # Inject language override for hCaptcha BEFORE form submit (text solver only)

            # Force English so the accessibility challenge menu is always in English.

            _solver_ai = self.config.get("solver_ai") or {}

            _text_ai_on = any(_solver_ai.get(p, False) for p in ("cloudflare", "groq", "openrouter"))

            if _text_ai_on:

                self._js("""

                    (() => {

                        if (window.__hcLangPatched) return;

                        window.__hcLangPatched = true;

                        const srcDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'src');

                        Object.defineProperty(HTMLIFrameElement.prototype, 'src', {

                            set(val) {

                                if (typeof val === 'string' && val.toLowerCase().includes('hcaptcha.com')) {

                                    try {

                                        const u = new URL(val);

                                        u.searchParams.set('hl', 'en');

                                        val = u.toString();

                                    } catch(e) {}

                                }

                                srcDesc.set.call(this, val);

                            },

                            get() { return srcDesc.get.call(this); },

                            configurable: true

                        });

                        const origSetAttr = HTMLIFrameElement.prototype.setAttribute;

                        HTMLIFrameElement.prototype.setAttribute = function(name, value) {

                            if (name === 'src' && typeof value === 'string' && value.toLowerCase().includes('hcaptcha.com')) {

                                try {

                                    const u = new URL(value);

                                    u.searchParams.set('hl', 'en');

                                    value = u.toString();

                                } catch(e) {}

                            }

                            return origSetAttr.call(this, name, value);

                        };

                    })()

                """)

            # Wait for the async DOB+submit JS to complete (~1s), then call

            # _submit_form as a fallback in case the embedded click didn't fire.

            time.sleep(1.2)

            self._check_stop()

            self._submit_form(worker_id=worker_id)

            self._fire_smart_trigger('fill_info')

            hcap_wait_start = time.time()

            hcap_time_wait = 0.0

            hcap_time_solve = 0.0

            auto_solve = self.config.get("auto_solver_captcha", False)

            _solver_ai = self.config.get("solver_ai") or {}

            _any_solver = auto_solve and any(_solver_ai.get(p, False) for p in ("cloudflare", "groq", "openrouter"))

            hcaptcha_appeared = False

            for _ in range(30):

                self._check_stop()

                if self._has_hcaptcha():

                    hcaptcha_appeared = True

                    break

                if self._check_passed():

                    break

                url = self._js("window.location.href") or ""

                if 'check-your-email' in url or '/verify' in url or '/channels' in url:

                    break

                self._sleep(0.5)

            hcap_time_wait = time.time() - hcap_wait_start

            hcap_solve_start = time.time()

            self._check_stop()

            if hcaptcha_appeared:

                if _any_solver:

                    self._check_stop()

                    solve_result = self._solve_hcaptcha_if_present(worker_id)

                    if solve_result == "FAILED":

                        return "EndlessCaptcha"

                    self._fire_smart_trigger('captcha_solved')

                    self._sleep(3)

                else:

                    Logger.STATUS = f"{MskColor.YELLOW}Captcha detected. Waiting for manual solve..."

                    Logger.queue_log(worker_id=worker_id)

                    start_w = time.time()

                    while time.time() - start_w < 300:

                        self._check_stop()

                        if self._check_passed():

                            break

                        url = self._js("window.location.href") or ""

                        if 'check-your-email' in url or '/verify' in url:

                            break

                        if not self._has_hcaptcha():

                            self._sleep(3)

                            if self._check_passed():

                                break

                        self._sleep(2)

                    self._fire_smart_trigger('captcha_solved')

            else:

                self._fire_smart_trigger('captcha_solved')

                self._sleep(2)

            hcap_time_solve = time.time() - hcap_solve_start

            if hcaptcha_appeared and not self._check_passed():

                url_after = self._js("window.location.href") or ""

                if self._has_hcaptcha() and '/channels' not in url_after and '/@me' not in url_after and 'check-your-email' not in url_after:

                    Logger.STATUS = f"{MskColor.RED}hCaptcha not solved"

                    Logger.queue_log(worker_id=worker_id)

                    return "EndlessCaptcha"

            elapsed_time = time.time() - start_time

            token = None

            if getattr(self, "_extracted_token", None):

                token = self._extracted_token

            if not token:

                quick_start = time.time()

                while time.time() - quick_start < 5:

                    token = self._extract_token()

                    if token:

                        break

                    if getattr(self, "_extracted_token", None):

                        token = self._extracted_token

                        break

                    time.sleep(0.5)

            if not token:

                try:

                    self._js("window.location.href = 'https://discord.com/app';")

                except Exception:

                    pass

                time.sleep(3)

                if getattr(self, "_extracted_token", None):

                    token = self._extracted_token

            if not token:

                extract_start = time.time()

                while time.time() - extract_start < 15:

                    token = self._extract_token()

                    if token:

                        break

                    raw = self._js("""

                        (() => {

                            // Method 1: localStorage direct read

                            try {

                                const direct = localStorage.getItem('token');

                                if (direct) {

                                    const t = direct.replace(/"/g, '').trim();

                                    if (t.length > 50 && t.indexOf('.') > -1) return t;

                                }

                            } catch(e) {}

                            // Method 2: scan all localStorage keys

                            try {

                                for (let i = 0; i < localStorage.length; i++) {

                                    const k = localStorage.key(i);

                                    let v = localStorage.getItem(k) || '';

                                    v = v.replace(/"/g, '').trim();

                                    if (v.length > 50 && v.indexOf('.') > -1 && v.indexOf('{') === -1 && v.indexOf('<') === -1) {

                                        return v;

                                    }

                                }

                            } catch(e) {}

                            // Method 3: React fiber tree traversal on document root

                            // Walk the fiber tree to find UserSettingsStore / TokenStore

                            try {

                                function walkFiber(fiber, depth) {

                                    if (!fiber || depth > 200) return null;

                                    try {

                                        const memoized = fiber.memoizedState;

                                        if (memoized && memoized.queue && memoized.memoizedState) {

                                            const s = memoized.memoizedState;

                                            if (typeof s === 'string' && s.length > 50 && s.indexOf('.') > -1 && s.indexOf('{') === -1) {

                                                return s;

                                            }

                                        }

                                    } catch(e) {}

                                    try {

                                        const stateNode = fiber.stateNode;

                                        if (stateNode && stateNode.token && typeof stateNode.token === 'string' && stateNode.token.length > 50) {

                                            return stateNode.token;

                                        }

                                    } catch(e) {}

                                    let result = null;

                                    if (fiber.child) result = walkFiber(fiber.child, depth + 1);

                                    if (!result && fiber.sibling) result = walkFiber(fiber.sibling, depth + 1);

                                    return result;

                                }

                                const root = document.getElementById('app-mount') || document.querySelector('[class*="app"]');

                                if (root) {

                                    const fiberKey = Object.keys(root).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));

                                    if (fiberKey) {

                                        const t = walkFiber(root[fiberKey], 0);

                                        if (t) return t;

                                    }

                                }

                            } catch(e) {}

                            return null;

                        })()

                    """)

                    token = self._clean_token(raw)

                    if token:

                        break

                    time.sleep(2)

            token_verify_enabled = self.config.get("token_verify", True)

            start_time_verify = time.time()

            ev_status = False

            if token_verify_enabled:

                email_providers = self.config.get("email_providers") or {}

                from ..Helper.mail import MskMailApi, suppress_output

                mail_api = None

                verify_kwargs = {"email": email_address, "timeout": 120, "poll_interval": 3}

                if email_providers.get("cybertemp", {}).get("enabled", False):

                    from ..Helper.mail import MskMailApi

                    cybertemp_key = email_providers.get("cybertemp", {}).get("api_key", "") or self.config.get("cybertemp_api_key", "")

                    mail_api = MskMailApi(api_key=cybertemp_key)

                elif email_providers.get("duckmail", {}).get("enabled", False):

                    from ..Helper.mail import DuckMailApi

                    duckmail_key = email_providers.get("duckmail", {}).get("api_key", "")

                    mail_api = DuckMailApi(api_key=duckmail_key)

                    verify_kwargs["password"] = email_password

                elif email_providers.get("mailcow", {}).get("enabled", False):

                    from ..Helper.mail import MailcowApi

                    mc = email_providers.get("mailcow", {})

                    mail_api = MailcowApi(host_url=mc.get("host_url", ""), api_key=mc.get("api_key", ""))

                    verify_kwargs["password"] = email_password

                elif email_providers.get("zeus", {}).get("enabled", False):

                    from ..Helper.mail import ZeusApi

                    z = email_providers.get("zeus", {})

                    mail_api = ZeusApi(api_key=z.get("api_key", ""), account_type=z.get("account_type", "HOTMAIL"))

                    verify_kwargs["password"] = email_password

                    verify_kwargs["refresh_token"] = self._zeus_refresh_token

                    verify_kwargs["client_id"] = self._zeus_client_id

                elif email_providers.get("hotmail007", {}).get("enabled", False):

                    from ..Helper.mail import Hotmail007Api

                    h = email_providers.get("hotmail007", {})

                    mail_api = Hotmail007Api(api_key=h.get("api_key", ""), mail_type=h.get("mail_type", "hotmail"))

                    verify_kwargs["password"] = email_password

                    verify_kwargs["refresh_token"] = self._zeus_refresh_token

                    verify_kwargs["client_id"] = self._zeus_client_id

                elif email_providers.get("lution", {}).get("enabled", False):

                    from ..Helper.mail import LutionApi

                    l = email_providers.get("lution", {})

                    mail_api = LutionApi(api_key=l.get("api_key", ""), category=l.get("account_type", "hotmail"))

                    verify_kwargs["password"] = email_password

                    verify_kwargs["refresh_token"] = self._zeus_refresh_token

                    verify_kwargs["client_id"] = self._zeus_client_id

                else:

                    mail_api = MskMailApi(api_key=self.config.get("cybertemp_api_key", ""))

                Logger.STATUS = f"{MskColor.PRIMARY}Verifying Email..."

                Logger.queue_log(worker_id=worker_id)

                _stop_fn = lambda: getattr(getattr(self, 'controller', None), 'should_stop', False)

                verify_kwargs['stop_signal'] = _stop_fn

                with suppress_output():

                    v_url = mail_api.get_verification_url(**verify_kwargs)

                if v_url:

                    linkverify_path = get_resource_path("data/output/linkverify.txt")

                    os.makedirs(os.path.dirname(linkverify_path), exist_ok=True)

                    with open(linkverify_path, "a", encoding="utf-8") as f:

                        f.write(f"{email_address}: {v_url}\n")

                    ev_status = self._verify_email_browser(v_url, worker_id)

                else:

                    pass

            else:

                Logger.STATUS = f"{MskColor.YELLOW}Skipping Email Verify (Token Verify OFF) - Creating Unclaimed Token..."

                Logger.queue_log(worker_id=worker_id)

            elapsed_time_verify = time.time() - start_time_verify

            self._fire_smart_trigger('email_verify')

            if ev_status:
                self._sleep(1.0)
                verified_token = self._extract_token()
                if verified_token:
                    token = verified_token
            elif not token:
                fallback = self._extract_token()
                if fallback:
                    token = fallback

            phone_verify_start = time.time()

            phone_verified = False

            phone_verify_time = 0.0

            humanize_start = time.time()

            humanize_time = 0.0

            humanize_status = f"{MskColor.GREY}Skipped"

            humanize_cfg = self.config.get("humanizer") or {}

            if humanize_cfg.get("enabled", False) and token and isinstance(token, str) and len(token) > 50:

                Logger.STATUS = f"{MskColor.LIGHTBLUE}Humanizing account..."

                Logger.queue_log(worker_id=worker_id)

                try:

                    from ..Helper.huminazer import DiscordHuminazer

                    humanizer = DiscordHuminazer(worker_id=worker_id)

                    h_result = humanizer.humanize_account(token, proxy_data)

                    humanize_status = f"{MskColor.GREEN}Humanized" if h_result else f"{MskColor.RED}Failed"

                except Exception as he:

                    humanize_status = f"{MskColor.RED}Error"

                    Logger.STATUS = f"{MskColor.RED}Humanize error: {str(he)[:50]}"

                    Logger.queue_log(worker_id=worker_id)

                humanize_time = time.time() - humanize_start

            ev_status_str = f"{MskColor.GREEN}Email Verified" if ev_status else f"{MskColor.RED}Unclaimed"

            if ev_status:

                Logger.STATUS = f"{MskColor.GREEN}Account Created & Verified!"

            else:

                Logger.STATUS = f"{MskColor.PRIMARY}Account Created (Unverified)!"

            Logger.queue_log(worker_id=worker_id)

            if not token or not isinstance(token, str) or len(token) <= 50:

                Logger.STATUS = f"{MskColor.RED}Token extraction failed"

                Logger.queue_log(worker_id=worker_id)

                return "Invalid"

            else:

                output_path = os.path.join(get_base_path(), "data", "output", "tokens.txt")

                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                save_fp = self.config.get("save_fingerprint", False)

                with open(output_path, "a") as f:

                    if save_fp and getattr(self, '_fingerprint', None):

                        f.write(f"{email_address}:{self.password}:{token}:{self._fingerprint}\n")

                    else:

                        f.write(f"{email_address}:{self.password}:{token}\n")

                generation_status = "Valid"

                try:

                    from .token_checker import check_token_safe

                    # Pass proxy_data so the check hits Discord from the same IP

                    # as registration. Without this, DataImpulse/datacenter proxies

                    # cause Discord to return 403 on /settings from a mismatched IP,

                    # which is incorrectly interpreted as a locked token.

                    _tc = check_token_safe(token, proxy=proxy_data if (self.config.get("proxies") or {}).get("enabled", False) else None)

                    if not _tc.get("valid"):

                        Logger.STATUS = f"{MskColor.RED}Token Invalid"

                        generation_status = "Invalid"

                    elif _tc.get("locked") or _tc.get("email_required") or _tc.get("phone_required"):

                        Logger.STATUS = f"{MskColor.ORANGE}Token Locked"

                        generation_status = "Locked"

                    else:

                        Logger.STATUS = f"{MskColor.GREEN}Token Valid"

                        generation_status = "Valid"

                        try:

                            import base64 as _b64

                            from ..Utils.custom_fingerprint import snowflake_to_age

                            _uid_b64 = token.split('.')[0]

                            _uid_b64 += '=' * ((4 - len(_uid_b64) % 4) % 4)

                            _uid = _b64.b64decode(_uid_b64).decode()

                            _acc_age = snowflake_to_age(_uid)

                            Logger.STATUS = f"{MskColor.LIGHTBLUE}Account Age: {_acc_age}"

                        except Exception:

                            pass

                    Logger.queue_log(worker_id=worker_id)

                except Exception:

                    Logger.STATUS = f"{MskColor.RED}Token Check Failed"

                    generation_status = "Invalid"

                    Logger.queue_log(worker_id=worker_id)

                Logger.STATUS = f"{MskColor.GREEN}Token Generated!"

                Logger.queue_log(worker_id=worker_id)

            try:

                try:

                    if sys.stdout:

                        sys.stdout.write("\n")

                except Exception:

                    pass

                self.print_stats(

                    worker_id, token or "N/A", elapsed_time, elapsed_time_startup,

                    hcap_time_wait, hcap_time_solve, humanize_time,

                    elapsed_time_verify, phone_verify_time, phone_verified,

                    humanize_status, ev_status_str

                )

            except Exception:

                pass

            try:

                _humanized_bool = "Humanized" in (humanize_status or "")

                self.last_result = {

                    "token":          str(token) if token else "",

                    "email":          str(email_address) if email_address else "",

                    "status":         generation_status,

                    "humanized":      _humanized_bool,

                    "phone_verified": bool(phone_verified),

                    "email_verified": bool(ev_status),

                    "gen_time":       round(float(elapsed_time or 0.0), 1),

                    "hcap_time":      round(float(hcap_time_solve or 0.0), 1),

                    "email_time":     round(float(elapsed_time_verify or 0.0), 1),

                    "phone_time":     round(float(phone_verify_time or 0.0), 1),

                    "humanize_time":  round(float(humanize_time or 0.0), 1),

                }

            except Exception:

                pass

            return generation_status

        except GeneratorStoppedError:

            return "Stopped"

        except Exception as e:

            err = str(e)

            if "Stopped by user" in err:

                return "Stopped"

            elif "Errno 2" in err or "No such file" in err:

                Logger.STATUS = f"{MskColor.RED}Brave Error: Browser not found (EXE path issue). Full error: {err[:100]}"

            elif "browser" in err.lower() and "executable" in err.lower():

                Logger.STATUS = f"{MskColor.RED}Brave Error: Brave not installed or not found at expected paths"

            elif "StopIteration" in err:

                Logger.STATUS = f"{MskColor.YELLOW}Brave: CDP iteration error, restarting..."

            elif "closed file" in err.lower() or "I/O operation" in err:

                Logger.STATUS = f"{MskColor.YELLOW}Brave: I/O recovered, restarting..."

            else:

                Logger.STATUS = f"{MskColor.RED}Brave Error: {err[:100]}"

            Logger.queue_log(worker_id=worker_id)

            return "Invalid"

        finally:

            self._cleanup()

            if on_browser_closed:

                on_browser_closed(worker_id)

            if wm and slot_idx is not None:

                try:

                    wm.release(slot_idx)

                except Exception:

                    pass

            

            try:

                import gc

                gc.collect()

            except:

                pass

