import random
import re
import string
import json
import time
import sys
import os
import requests
from datetime import datetime

from pathlib import Path
from typing import Any, Dict, Tuple, Set, Optional, List, Callable
import tls_client

# ── Single source of truth for environment detection ──
# All path/frozen detection is in env.py. These are re-exported for
# backward compatibility so existing `from .utils import get_base_path` keeps working.
from .env import (
    is_frozen as _is_frozen,
    get_base_path,
    get_resource_path,
    get_config_path,
    init_browserforge_path,
    rehabilitate_environment_paths,
    init_exe_environment,
)


def ensure_truedriver_deps():
    """Fix missing package data files for Nuitka EXE mode.
    
    truedriver depends on packages (emoji, grapheme, etc.) that have
    non-Python data files (JSON, etc.). Nuitka onefile mode compiles the
    Python code but can skip embedding these data files, causing
    FileNotFoundError at runtime.
    
    This function finds the Nuitka temp extraction directory, checks each
    dependency for missing data subdirectories, and copies them from the
    system Python installation.
    """
    if not _is_frozen():
        return
    
    import shutil
    
    PACKAGES_WITH_DATA = [
        ("emoji", ["unicode_codes"]),
        ("grapheme", ["data"]),
        ("mss", []),
        ("deprecated", []),
    ]
    
    temp_dir = os.environ.get("TEMP", os.environ.get("TMP", ""))
    nuitka_base = None
    
    if temp_dir and os.path.isdir(temp_dir):
        try:
            for entry in os.listdir(temp_dir):
                full = os.path.join(temp_dir, entry)
                if entry.startswith("ONEFIL") and os.path.isdir(full):
                    if any(os.path.isdir(os.path.join(full, p)) for p, _ in PACKAGES_WITH_DATA):
                        nuitka_base = full
                        break
                elif entry.startswith("OND") and os.path.isdir(full):
                    if any(os.path.isdir(os.path.join(full, p)) for p, _ in PACKAGES_WITH_DATA):
                        nuitka_base = full
                        break
        except OSError:
            pass
    
    if not nuitka_base:
        return
    
    user_profile = os.environ.get("USERPROFILE", "")
    if not user_profile:
        return
    
    site_packages_dirs = []
    
    py_programs = os.path.join(user_profile, "AppData", "Local", "Programs", "Python")
    if os.path.isdir(py_programs):
        for ver_dir in os.listdir(py_programs):
            sp = os.path.join(py_programs, ver_dir, "Lib", "site-packages")
            if os.path.isdir(sp):
                site_packages_dirs.append(sp)
    
    for drive in ("C:", "D:"):
        for pyver in ("Python310", "Python311", "Python312", "Python39", "Python313"):
            sp = os.path.join(drive + os.sep, pyver, "Lib", "site-packages")
            if os.path.isdir(sp):
                site_packages_dirs.append(sp)
    
    if not site_packages_dirs:
        return
    
    for pkg_name, data_subdirs in PACKAGES_WITH_DATA:
        pkg_dir_nuitka = os.path.join(nuitka_base, pkg_name)
        if not os.path.isdir(pkg_dir_nuitka):
            continue
        
        real_pkg_dir = None
        for sp in site_packages_dirs:
            candidate = os.path.join(sp, pkg_name)
            if os.path.isdir(candidate):
                real_pkg_dir = candidate
                break
        
        if not real_pkg_dir:
            continue
        
        if data_subdirs:
            for subdir in data_subdirs:
                target = os.path.join(pkg_dir_nuitka, subdir)
                source = os.path.join(real_pkg_dir, subdir)
                if os.path.isdir(source) and not os.path.isdir(target):
                    try:
                        shutil.copytree(source, target)
                    except Exception:
                        pass
        else:
            try:
                for item in os.listdir(real_pkg_dir):
                    src = os.path.join(real_pkg_dir, item)
                    dst = os.path.join(pkg_dir_nuitka, item)
                    if os.path.isdir(src) and not os.path.exists(dst):
                        shutil.copytree(src, dst)
                    elif os.path.isfile(src) and not src.endswith('.py') and not os.path.exists(dst):
                        shutil.copy2(src, dst)
            except Exception:
                pass

ensure_zendriver_deps = ensure_truedriver_deps  # kept for backwards compatibility
ensure_nodriver_deps = ensure_truedriver_deps    # kept for backwards compatibility


_VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

_DEPENDENCY_STATUS: Dict[str, bool] = {}


def _check_vcredist_installed() -> bool:
    """Check Windows registry for Microsoft Visual C++ 2015-2022 Redistributable x64."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        keys_to_check = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\Installer\Dependencies\VC,redist.x64,amd64,14.40,bundle"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\Installer\Dependencies\,,amd64,14.0,bundle"),
        ]
        for hive, key_path in keys_to_check:
            try:
                key = winreg.OpenKey(hive, key_path)
                try:
                    installed, _ = winreg.QueryValueEx(key, "Installed")
                    if installed == 1:
                        winreg.CloseKey(key)
                        return True
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except (FileNotFoundError, OSError):
                continue

        dll_paths = []
        system32 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
        syswow64 = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "SysWOW64")
        for folder in (system32, syswow64):
            for dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
                dll_paths.append(os.path.join(folder, dll))
        if any(os.path.isfile(p) for p in dll_paths):
            return True

        return False
    except Exception:
        return True


def _preload_greenlet():
    """Pre-check greenlet native module to provide a clear error instead of a crash."""
    try:
        import greenlet
        _DEPENDENCY_STATUS["greenlet"] = True
    except (ImportError, OSError) as e:
        _DEPENDENCY_STATUS["greenlet"] = False
        err = str(e)
        is_dll_error = any(kw in err.lower() for kw in ["pyd", "dll", "loadlibrary", "specified module", "cannot open", "no such file"])
        try:
            print(
                "\n[!] greenlet native module failed to load.\n"
                f"    Error: {err}\n"
                "    This usually means Microsoft Visual C++ Redistributable x64 is not installed.\n"
                f"    Download it from: {_VCREDIST_URL}\n"
                "    After installing VC++ Redistributable, restart the application.\n"
            )
        except Exception:
            pass
    except Exception:
        _DEPENDENCY_STATUS["greenlet"] = False


def _check_tls_client() -> bool:
    """Verify tls_client loads and its native DLL is functional."""
    try:
        import tls_client as _tc
        session = _tc.Session(client_identifier="chrome_120", random_tls_extension_order=False)
        _DEPENDENCY_STATUS["tls_client"] = True
        return True
    except (ImportError, OSError) as e:
        _DEPENDENCY_STATUS["tls_client"] = False
        err = str(e)
        try:
            print(
                "\n[!] tls_client native library failed to load.\n"
                f"    Error: {err}\n"
                "    This means token checking (valid/locked/invalid) will NOT work correctly.\n"
                "    Fix: Install Microsoft Visual C++ Redistributable x64 from:\n"
                f"         {_VCREDIST_URL}\n"
                "    Then restart the application.\n"
            )
        except Exception:
            pass
        return False
    except Exception as e:
        _DEPENDENCY_STATUS["tls_client"] = True
        return True


def _check_truedriver() -> bool:
    """Verify truedriver (Brave/Chromium CDP) imports correctly."""
    try:
        import truedriver
        _DEPENDENCY_STATUS["truedriver"] = True
        return True
    except (ImportError, OSError) as e:
        _DEPENDENCY_STATUS["truedriver"] = False
        err = str(e)
        try:
            print(
                "\n[!] truedriver (Brave/Chromium automation) failed to import.\n"
                f"    Error: {err}\n"
                "    Brave/Chromium registration will not work.\n"
                "    Fix: Run installer.bat to reinstall dependencies.\n"
            )
        except Exception:
            pass
        return False
    except Exception:
        _DEPENDENCY_STATUS["truedriver"] = True
        return True


def run_dependency_scan(verbose: bool = True) -> Dict[str, Any]:
    """Run a comprehensive scan of all required native dependencies.

    Checks:
      - Microsoft Visual C++ Redistributable x64 (2015-2022)
      - greenlet native module
      - tls_client native DLL
      - truedriver (Brave/Chromium CDP automation)
      - Brave browser executable

    Returns a dict with 'ok' (bool), 'issues' (list of str), and per-component status.
    """
    results: Dict[str, Any] = {
        "ok": True,
        "issues": [],
        "vcredist_x64": False,
        "greenlet": False,
        "tls_client": False,
        "nodriver": False,  # kept for backwards compat
        "truedriver": False,
        "brave_found": False,
    }

    if sys.platform != "win32":
        results["ok"] = True
        results["issues"].append("Dependency scan only runs on Windows.")
        return results

    if verbose:
        try:
            print("\n[MSK] ── Dependency Scan ──────────────────────────────────────")
        except Exception:
            pass

    vc = _check_vcredist_installed()
    results["vcredist_x64"] = vc
    if not vc:
        results["ok"] = False
        msg = (
            "Microsoft Visual C++ Redistributable x64 NOT found.\n"
            f"  Download: {_VCREDIST_URL}\n"
            "  This is REQUIRED for tls_client and greenlet to work.\n"
            "  Without it, tokens will appear invalid/locked on this PC."
        )
        results["issues"].append(msg)
        if verbose:
            try:
                print(f"[MSK] [FAIL] {msg}")
            except Exception:
                pass
    else:
        if verbose:
            try:
                print("[MSK] [ OK ] Visual C++ Redistributable x64 (2015-2022) -- installed")
            except Exception:
                pass

    gl = _DEPENDENCY_STATUS.get("greenlet", None)
    if gl is None:
        _preload_greenlet()
        gl = _DEPENDENCY_STATUS.get("greenlet", False)
    results["greenlet"] = gl
    if not gl:
        results["ok"] = False
        msg = (
            "greenlet native module failed to load.\n"
            "  This causes broken async/CDP browser control → locked tokens.\n"
            f"  Fix: Install VC++ Redistributable from {_VCREDIST_URL}"
        )
        results["issues"].append(msg)
        if verbose:
            try:
                print(f"[MSK] [FAIL] {msg}")
            except Exception:
                pass
    else:
        if verbose:
            try:
                print("[MSK] [ OK ] greenlet native module -- loaded")
            except Exception:
                pass

    tc = _check_tls_client()
    results["tls_client"] = tc
    if not tc:
        results["ok"] = False
        msg = (
            "tls_client native DLL failed to load.\n"
            "  Token checking (valid/locked/invalid) will produce wrong results.\n"
            f"  Fix: Install VC++ Redistributable from {_VCREDIST_URL}"
        )
        results["issues"].append(msg)
        if verbose:
            try:
                print(f"[MSK] [FAIL] {msg}")
            except Exception:
                pass
    else:
        if verbose:
            try:
                print("[MSK] [ OK ] tls_client native DLL -- loaded")
            except Exception:
                pass

    zd = _check_truedriver()
    results["truedriver"] = zd
    results["nodriver"] = zd  # backwards compat
    if not zd:
        results["ok"] = False
        msg = (
            "truedriver failed to import.\n"
            "  Brave/Chromium registration will not work.\n"
            "  Fix: Run installer.bat to reinstall Python dependencies."
        )
        results["issues"].append(msg)
        if verbose:
            try:
                print(f"[MSK] [FAIL] {msg}")
            except Exception:
                pass
    else:
        if verbose:
            try:
                print("[MSK] [ OK ] truedriver (Brave/Chromium CDP) -- imported")
            except Exception:
                pass

    brave_path = _find_brave_exe_for_scan()
    results["brave_found"] = bool(brave_path)
    if not brave_path:
        results["ok"] = False
        msg = (
            "Brave browser not found on this PC.\n"
            "  Download and install from: https://brave.com/download\n"
            "  Brave is required for the Brave/Chromium registration method."
        )
        results["issues"].append(msg)
        if verbose:
            try:
                print(f"[MSK] [WARN] {msg}")
            except Exception:
                pass
    else:
        if verbose:
            try:
                print(f"[MSK] [ OK ] Brave browser -- found at: {brave_path}")
            except Exception:
                pass

    if verbose:
        try:
            if results["ok"]:
                print("[MSK] ── All dependencies OK. No issues found. ──────────────\n")
            else:
                print(f"[MSK] ── {len(results['issues'])} issue(s) found. See above for fixes. ──\n")
        except Exception:
            pass

    return results


def _find_brave_exe_for_scan() -> str:
    """Find Brave executable for dependency scan (standalone, no class needed)."""
    if sys.platform != "win32":
        return ""
    candidates = []
    dirs = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA", "PROGRAMW6432"):
        val = os.environ.get(var)
        if val:
            dirs.append(val)
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        dirs.append(os.path.join(user_profile, "AppData", "Local"))
    for drive in ("C:", "D:"):
        dirs.extend([f"{drive}\\Program Files", f"{drive}\\Program Files (x86)"])
    seen = set()
    unique_dirs = []
    for d in dirs:
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


rehabilitate_environment_paths()
init_browserforge_path()
ensure_zendriver_deps()
_preload_greenlet()
_check_tls_client()

try:
    _dep_scan = run_dependency_scan(verbose=False)
    if not _dep_scan["ok"]:
        _issue_count = len(_dep_scan["issues"])
        try:
            print(
                f"\n[MSK] WARNING: {_issue_count} dependency issue(s) detected on this PC.\n"
                "[MSK] Tokens may appear invalid or locked due to missing native libraries.\n"
                f"[MSK] Install VC++ Redistributable x64 from: {_VCREDIST_URL}\n"
            )
        except Exception:
            pass
except Exception:
    pass


def is_exe_mode() -> bool:
    """Check if running as frozen executable."""
    return _is_frozen()


# get_config_path is imported from .env at the top of this file


def load_config() -> Dict[str, Any]:
    """Load config from config.json (always external, writable)."""
    config_path = get_config_path()
    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
            if "language" not in config:
                config["language"] = "en"
            return config
    except FileNotFoundError:
        print(f"[!] Warning: {config_path} not found. Using defaults.")
        return {"language": "en"}
    except json.JSONDecodeError:
        try:
            with open(config_path, encoding="utf-8-sig") as f2:
                config = json.load(f2)
                if "language" not in config:
                    config["language"] = "en"
                with open(config_path, "w", encoding="utf-8") as fw:
                    json.dump(config, fw, indent=4, ensure_ascii=False)
                return config
        except Exception:
            pass
        print(f"[!] Warning: Could not load config (JSON error)")
        try:
            backup_path = config_path + ".corrupted"
            import shutil
            shutil.copy2(config_path, backup_path)
            print(f"[!] Corrupted config backed up to: {backup_path}")
            os.remove(config_path)
        except Exception as backup_err:
            print(f"[!] Could not back up corrupted config: {backup_err}")
        return {"language": "en"}
    except Exception as e:
        print(f"[!] Warning: Could not load config: {e}")
        return {"language": "en"}


def save_config(config: Dict[str, Any]) -> bool:
    """Save config to config.json using atomic write to prevent corruption."""
    config_path = get_config_path()
    try:
        config_dir = os.path.dirname(config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)

        ordered_config = {"language": config.get("language", "en")}
        for key, value in config.items():
            if key != "language":
                ordered_config[key] = value

        tmp_path = config_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(ordered_config, f, indent=4)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass

            import shutil
            shutil.move(tmp_path, config_path)
        except (OSError, IOError):
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(ordered_config, f, indent=4)
        return True
    except Exception as e:
        print(f"[!] Error saving config to {config_path}: {e}")
        try:
            if os.path.exists(config_path + ".tmp"):
                os.remove(config_path + ".tmp")
        except Exception:
            pass
        return False


class _ConfigProperty:
    """Descriptor that always reads config fresh from file."""
    def __get__(self, obj, objtype=None):
        return load_config()
    
    def __set__(self, obj, value):
        save_config(value)


class Config:
    """Config class that always reads fresh from config.json."""
    config = _ConfigProperty()


class RateLimitChecker:
    DEFAULT_PASSWORD = "$MskTUSiCE2169#"
    
    @staticmethod
    def check_rate_limit(response) -> Optional[int]:
        """Check if response has rate limit and return wait time in seconds."""
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                return int(float(retry_after))
            try:
                data = response.json()
                return int(data.get("retry_after", 5))
            except:
                return 5
        return None
    
    @staticmethod
    def handle_rate_limit(response, logger_func=None) -> bool:
        """Handle rate limit by waiting. Returns True if rate limited."""
        wait_time = RateLimitChecker.check_rate_limit(response)
        if wait_time:
            if logger_func:
                logger_func(f"Rate limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
            return True
        return False
    
    @staticmethod
    def check_account_ratelimit(logger_func: Optional[Callable] = None) -> int:
        """
        Passively check Discord's rate limit status WITHOUT triggering one.
        Uses lightweight read-only endpoints that reveal rate limit state via
        response headers (X-RateLimit-Remaining, Retry-After) instead of the
        old approach of sending a real registration POST.
        Returns wait time in seconds if rate limited, otherwise returns 1.
        """
        try:
            import requests as _req

            headers = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.5",
                "DNT": "1",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-GPC": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
                "Referer": "https://discord.com/register",
                "Origin": "https://discord.com",
            }

            # ── Primary: hit the experiments endpoint (lightweight, read-only) ──
            endpoints = [
                "https://discord.com/api/v9/experiments",
                "https://discord.com/api/v9/gateway",
            ]

            for url in endpoints:
                try:
                    resp = _req.get(url, headers=headers, timeout=10)

                    # Explicit 429 = rate limited
                    if resp.status_code == 429:
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            wait = int(float(retry_after)) + 1
                        else:
                            try:
                                data = resp.json()
                                wait = int(float(data.get("retry_after", 5))) + 1
                            except Exception:
                                wait = 10
                        if logger_func:
                            logger_func(f"Rate limit detected. Wait time: {wait}s")
                        return wait

                    # Check rate limit headers on successful responses
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    reset_after = resp.headers.get("X-RateLimit-Reset-After")

                    if remaining is not None:
                        try:
                            if int(remaining) <= 0 and reset_after:
                                wait = int(float(reset_after)) + 1
                                if logger_func:
                                    logger_func(f"Rate limit bucket exhausted. Wait time: {wait}s")
                                return wait
                        except (ValueError, TypeError):
                            pass

                    # If we got a successful response, IP is not rate limited
                    if resp.status_code in (200, 201, 204, 401, 403):
                        return 1

                except _req.exceptions.ConnectionError:
                    continue
                except _req.exceptions.Timeout:
                    continue
                except Exception:
                    continue

            # All endpoints failed to respond -- assume no rate limit
            return 1

        except Exception as e:
            if logger_func:
                logger_func(f"Rate limit check failed: {e}")
            return 1
    
    @staticmethod
    def countdown_timer(duration: int, logger_func: Optional[Callable] = None) -> None:
        """
        Display a countdown timer while waiting for rate limit to expire.
        """
        for i in range(duration):
            if sys.stdout:
                try:
                    sys.stdout.write(
                        f"\r                    \033[38;2;192;192;192m[\033[90mMsk\033[38;2;192;192;192m]\033[0m >> \033[93m[{i+1:02d}/{duration}]\033[0m Waiting before generating next token...    "
                    )
                    sys.stdout.flush()
                except Exception:
                    pass
            time.sleep(1)
        print()
    
    @staticmethod
    def wait_for_ratelimit(logger_func: Optional[Callable] = None) -> bool:
        """
        Check for rate limit and wait if necessary.
        Returns True if rate limited and waited, False otherwise.
        """
        wait_time = RateLimitChecker.check_account_ratelimit(logger_func)
        if wait_time > 1:
            if logger_func:
                logger_func(f"Rate limited - waiting {wait_time} seconds...")
            RateLimitChecker.countdown_timer(wait_time, logger_func)
            return True
        return False


class Utils:
    @staticmethod
    def proxy_dict_to_url(proxy_dict: Dict[str, str]) -> str:
        import re as _re
        from urllib.parse import quote
        server_url = _re.sub(r'^[a-z0-9+\-.]+://', '', proxy_dict['server'])
        username = proxy_dict.get('username', '')
        password = proxy_dict.get('password', '')
        if username and password:
            return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{server_url}"
        return f"http://{server_url}"

    @staticmethod
    def check_discord_token(token: str, proxy: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        session = tls_client.Session(client_identifier="chrome_120")
        
        if proxy:
            proxy_url = Utils.proxy_dict_to_url(proxy_dict=proxy)
            session.proxies = {'http': proxy_url, 'https': proxy_url}

        try:
            r = session.get("https://discord.com/api/v9/users/@me", headers={"Authorization": token})
            if r.status_code != 200:
                return {"status": "Invalid"}

            user_data = r.json()
            email_verified = user_data.get("verified", False)
            phone = user_data.get("phone")

            r2 = session.get("https://discord.com/api/v9/users/@me/settings", headers={"Authorization": token})
            if r2.status_code == 200:
                return {"status": "Valid"}
            elif r2.status_code == 403:
                if not email_verified:
                    return {"status": "EmailVerify"}
                elif phone is None:
                    return {"status": "Locked"}
                else:
                    return {"status": "Locked"}
        except Exception:
            return {"status": "Invalid"}

        return {"status": "Invalid"}

    @staticmethod
    def random_password(length: int = 12) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    def random_string(length: int = 16) -> str:
        allowed_chars = string.ascii_lowercase + string.digits + "_"
        first_char = random.choice(string.ascii_lowercase + string.digits)
        middle = ''.join(random.choice(allowed_chars) for _ in range(max(length - 2, 0)))
        last_char = random.choice(string.ascii_lowercase + string.digits) if length > 1 else ""
        result = first_char + middle + last_char
        result = re.sub(r'_{2,}', '_', result)
        return result

    @staticmethod
    def sanitize_username(username: str) -> str:
        """Remove characters that Discord rejects in usernames (dots, hashes, etc)."""
        username = re.sub(r'[.#@!$%^&*()+=\[\]{}<>|\\/:;"\'?~`,]', '', username)
        username = re.sub(r'_{2,}', '_', username)
        username = username.strip('_')
        if len(username) < 2:
            username = username + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return username

    @staticmethod
    def generate_real_username(use_api: bool = False) -> str:
        """Generate a realistic username, optionally using an API."""
        if use_api:
            try:
                import requests
                resp = requests.get('https://randomuser.me/api/?inc=login', timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_user = data['results'][0]['login']['username']
                    return Utils.sanitize_username(raw_user)
            except Exception:
                pass
        
        # Fallback: Generate realistic usernames using multiple patterns
        # that mimic real human username choices
        
        # Common first name prefixes (short, natural)
        first_parts = [
            "alex", "sam", "chris", "jordan", "taylor", "casey", "riley", "avery",
            "quinn", "parker", "morgan", "dakota", "reese", "hayden", "finley",
            "rowan", "sage", "river", "skyler", "emery", "marley", "arlow", "kendall",
            "spencer", "drew", "blake", "cameron", "elliot", "francis", "harper",
            "jamie", "kennedy", "lennon", "marlowe", "oakley", "peyton", "quincy",
            "reagan", "sawyer", "teagan", "valentine", "winter", "xander", "yates",
            "zephyr", "adrian", "bailey", "corey", "devon", "elliot", "finnegan",
            "grayson", "hudson", "ivan", "jasper", "kieran", "logan", "maxwell",
            "nolan", "owen", "preston", "quentin", "roman", "sebastian", "tristan",
            "ulysses", "vaughn", "wesley", "xavier", "york", "zane", "aiden",
            "brandon", "caleb", "dylan", "ethan", "felix", "gabe", "henry", "isaac",
            "jack", "kyle", "liam", "mason", "noah", "oliver", "peter", "quinn",
            "ryan", "simon", "thomas", "victor", "william", "xander", "yusuf", "zach"
        ]
        
        # Common last name / noun suffixes
        last_parts = [
            "smith", "jones", "williams", "brown", "davis", "miller", "wilson",
            "moore", "taylor", "anderson", "thomas", "jackson", "white", "harris",
            "martin", "thompson", "garcia", "martinez", "robinson", "clark", "rodriguez",
            "lewis", "lee", "walker", "hall", "allen", "young", "hernandez", "king",
            "wright", "lopez", "hill", "scott", "green", "adams", "baker", "gonzalez",
            "nelson", "carter", "mitchell", "perez", "roberts", "turner", "phillips",
            "campbell", "parker", "evans", "edwards", "collins", "stewart", "sanchez",
            "morris", "rogers", "reed", "cook", "morgan", "bell", "murphy", "bailey",
            "rivera", "cooper", "richardson", "cox", "howard", "ward", "torres",
            "peterson", "gray", "ramirez", "james", "watson", "brooks", "kelly",
            "sanders", "price", "bennett", "wood", "barnes", "ross", "henderson",
            "coleman", "jenkins", "perry", "powell", "long", "patterson", "hughes",
            "flores", "washington", "butler", "simmons", "foster", "gonzales",
            "bryant", "alexander", "russell", "griffin", "diaz", "hayes"
        ]
        
        # Common word combinations (adjective + noun, verb + noun, etc.)
        word_combos = [
            ("swift", "fox"), ("silent", "wolf"), ("bright", "star"), ("calm", "sea"),
            ("dark", "knight"), ("deep", "ocean"), ("fast", "runner"), ("gentle", "breeze"),
            ("happy", "soul"), ("jolly", "roger"), ("keen", "eye"), ("lively", "spirit"),
            ("merry", "maker"), ("nimble", "mind"), ("proud", "heart"), ("quiet", "storm"),
            ("rapid", "fire"), ("steady", "hand"), ("tidy", "coder"), ("vivid", "dream"),
            ("wild", "card"), ("young", "blood"), ("zealous", "zen"), ("bold", "move"),
            ("brave", "heart"), ("clever", "fox"), ("daring", "doer"), ("eager", "beaver"),
            ("fierce", "lion"), ("glad", "tidings"), ("honest", "abe"), ("kind", "spirit"),
            ("loyal", "friend"), ("noble", "cause"), ("polite", "society"), ("smart", "cookie"),
            ("true", "north"), ("wise", "owl"), ("witty", "banter"), ("zesty", "lemon"),
            ("agile", "mind"), ("alert", "eagle"), ("awake", "dreamer"), ("blissful", "ignorance"),
            ("cool", "cat"), ("dark", "horse"), ("deep", "thinker"), ("fast", "lane"),
            ("golden", "hour"), ("holy", "moly"), ("iron", "will"), ("jazz", "hand"),
            ("kind", "red"), ("lucky", "charm"), ("magic", "touch"), ("night", "owl"),
            ("open", "book"), ("prime", "time"), ("quick", "silver"), ("red", "baron"),
            ("silver", "lining"), ("tough", "cookie"), ("urban", "legend"), ("vivid", "imagination"),
            ("wild", "west"), ("xray", "vision"), ("young", "gun"), ("zen", "master")
        ]
        
        # Choose generation strategy randomly
        strategy = random.randint(1, 8)
        
        if strategy == 1:
            # FirstName + LastName + number (most realistic)
            first = random.choice(first_parts)
            last = random.choice(last_parts)
            num = random.randint(1, 9999)
            fmt = random.randint(1, 4)
            if fmt == 1:
                username = f"{first}{last}{num}"
            elif fmt == 2:
                username = f"{first}.{last}{num}"
            elif fmt == 3:
                username = f"{first}_{last}{num}"
            else:
                username = f"{first.capitalize()}{last.capitalize()}{num}"
                
        elif strategy == 2:
            # Adjective + Noun + number (word combo)
            adj, noun = random.choice(word_combos)
            num = random.randint(1, 9999)
            fmt = random.randint(1, 5)
            if fmt == 1:
                username = f"{adj}{noun}{num}"
            elif fmt == 2:
                username = f"{adj}_{noun}{num}"
            elif fmt == 3:
                username = f"{adj}{noun}_{num}"
            elif fmt == 4:
                username = f"{adj.capitalize()}{noun.capitalize()}{num}"
            else:
                username = f"{adj}{random.choice(['', '_'])}{noun}{num}"
                
        elif strategy == 3:
            # FirstName + adjective + number
            first = random.choice(first_parts)
            adj = random.choice([w[0] for w in word_combos])
            num = random.randint(1, 9999)
            username = f"{first}{adj}{num}"
            
        elif strategy == 4:
            # Verb-style + noun (action oriented)
            verbs = ["run", "jump", "fly", "swim", "code", "play", "read", "write",
                     "draw", "sing", "dance", "build", "create", "make", "do", "go",
                     "see", "know", "think", "feel", "love", "like", "want", "need"]
            nouns = ["fox", "wolf", "hawk", "eagle", "lion", "tiger", "bear", "shark",
                     "dragon", "phoenix", "raven", "falcon", "panther", "cobra", "viper",
                     "storm", "shadow", "blaze", "frost", "thunder", "mist", "dawn", "dusk"]
            verb = random.choice(verbs)
            noun = random.choice(nouns)
            num = random.randint(1, 9999)
            fmt = random.randint(1, 3)
            if fmt == 1:
                username = f"{verb}{noun}{num}"
            elif fmt == 2:
                username = f"{verb}_{noun}{num}"
            else:
                username = f"{verb.capitalize()}{noun.capitalize()}{num}"
                
        elif strategy == 5:
            # Two first names (double name)
            first1 = random.choice(first_parts)
            first2 = random.choice(first_parts)
            num = random.randint(1, 999)
            fmt = random.randint(1, 3)
            if fmt == 1:
                username = f"{first1}{first2}{num}"
            elif fmt == 2:
                username = f"{first1}.{first2}{num}"
            else:
                username = f"{first1}_{first2}{num}"
                
        elif strategy == 6:
            # Short word + year (birth year style)
            words = ["gamer", "coder", "dev", "pro", "master", "king", "queen", "boss",
                     "chief", "captain", "commander", "general", "admiral", "major",
                     "colonel", "captain", "lieutenant", "sergeant", "corporal", "private"]
            word = random.choice(words)
            year = random.randint(1990, 2008)
            fmt = random.randint(1, 3)
            if fmt == 1:
                username = f"{word}{year}"
            elif fmt == 2:
                username = f"{word}_{year}"
            else:
                username = f"{word.capitalize()}{year}"
                
        elif strategy == 7:
            # Initials + last name + number
            initials = ''.join(random.choices(string.ascii_lowercase, k=random.randint(2, 3)))
            last = random.choice(last_parts)
            num = random.randint(10, 9999)
            username = f"{initials}{last}{num}"
            
        else:
            # Pronounceable syllables (consonant + vowel + optional consonant)
            syllables = [
                "ba", "be", "bi", "bo", "bu", "da", "de", "di", "do", "du",
                "fa", "fe", "fi", "fo", "fu", "ga", "ge", "gi", "go", "gu",
                "ha", "he", "hi", "ho", "hu", "ja", "je", "ji", "jo", "ju",
                "ka", "ke", "ki", "ko", "ku", "la", "le", "li", "lo", "lu",
                "ma", "me", "mi", "mo", "mu", "na", "ne", "ni", "no", "nu",
                "pa", "pe", "pi", "po", "pu", "ra", "re", "ri", "ro", "ru",
                "sa", "se", "si", "so", "su", "ta", "te", "ti", "to", "tu",
                "va", "ve", "vi", "vo", "vu", "wa", "we", "wi", "wo", "wu",
                "za", "ze", "zi", "zo", "zu", "bri", "bra", "bre", "bro",
                "cli", "cla", "cle", "clo", "cru", "dra", "dre", "dri", "dro",
                "flu", "fla", "fle", "flo", "gla", "gle", "glo", "gra", "gre",
                "gri", "gro", "pri", "pra", "pre", "pro", "sli", "sla", "sle",
                "slo", "spi", "spa", "spe", "spo", "sti", "sta", "ste", "sto",
                "tri", "tra", "tre", "tro", "vri", "vra", "vre", "vro"
            ]
            num_syllables = random.randint(2, 4)
            base = ''.join(random.choices(syllables, k=num_syllables))
            num = random.randint(10, 9999)
            username = f"{base}{num}"
        
        return Utils.sanitize_username(username)

    @staticmethod
    def random_username(use_api: bool = False) -> str:
        return Utils.generate_real_username(use_api=use_api)

    @staticmethod
    def sanitize_email_local(local_part: str) -> str:
        """Sanitize the local part of an email address for Discord compatibility."""
        local_part = re.sub(r'[#!$%^&*()+=\[\]{}<>|\\/:;"\'?~`,]', '', local_part)
        local_part = re.sub(r'\.{2,}', '.', local_part)
        local_part = local_part.strip('.')
        if len(local_part) < 2:
            local_part = local_part + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return local_part

    @staticmethod
    def random_birthday() -> Tuple[str, str, str]:
        day = str(random.randint(1, 28))
        month = random.choice([
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ])
        year = str(random.randint(1980, 2007))
        return day, month, year
    
    DISCORD_DOMAINS = [
        "rainga.ng",
        "diddyricky.fr",
        "lonard-os.com",
        "diddyricky.store",
        "diddyricky.com",
        "soniot.fr",
        "saturn.monster",
        "soniot.info",
        "diddyricky.info",
        "soniot.online",
        "soniot.store"
    ]

    @staticmethod
    def get_domain(max_retries: int = 3) -> str:
        return random.choice(Utils.DISCORD_DOMAINS)


class JsInjection:
    def __init__(self, js_files: Optional[List[str]] = None) -> None:
        base_path = self._get_js_base_path()
        files = js_files or ["utils.js", "performance.js"]
        self._scripts: Dict[str, str] = {}

        for fname in files:
            path = base_path / fname
            if path.exists():
                try:
                    self._scripts[fname] = path.read_text(encoding="utf-8")
                except Exception:
                    self._scripts[fname] = ""
            else:
                self._scripts[fname] = ""

        self._injected_context_ids: Set[int] = set()

    def _get_js_base_path(self) -> Path:
        """Get the JS base path, handling frozen executable."""
        if _is_frozen():
            return Path(get_base_path()) / "MSK_core" / "JS"
        return Path(__file__).parent.parent / "JS"

    def setup_js(self, page: Any) -> None:
        ctx_id = id(page)
        if ctx_id in self._injected_context_ids:
            return

        add_init = getattr(page, "add_init_script", None)
        for name, code in self._scripts.items():
            if not code:
                continue
            if callable(add_init):
                try:
                    page.add_init_script(code)
                except Exception:
                    pass
            try:
                page.evaluate(f"(function(){{ {code} }})()")
            except Exception:
                pass

        self._injected_context_ids.add(ctx_id)

    def call(self, page: Any, func_name: str, *args: Any) -> Any:
        raw = json.dumps(list(args), ensure_ascii=False)
        js_args = raw.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")

        js_expr = f"""
        (() => {{
            const fnRef = (window.utils && window.utils['{func_name}']) || window['{func_name}'];
            if (typeof fnRef !== 'function') {{
                throw new Error('Function not found: {func_name}');
            }}
            return fnRef(...JSON.parse(`{js_args}`));
        }})()
        """
        return page.evaluate(js_expr)

    def open_accessibility_challenge(self, frame: Any) -> Any:
        return self.call(frame, "openAccessibilityChallenge")

    def answer_accessibility_question(self, frame: Any, answer: str) -> Any:
        return self.call(frame, "answerAccessibilityQuestion", answer)

    def set_input(self, page: Any, selector: str, value: str) -> Any:
        return self.call(page, "setInput", selector, value)

    def click_checkbox(self, page: Any, selector: str) -> Any:
        return self.call(page, "clickCheckbox", selector)

    def click_element(self, page: Any, selector: str) -> Any:
        return self.call(page, "clickElement", selector)

    def set_dropdown(self, page: Any, label: str, value: str) -> Any:
        return self.call(page, "setDropdown", label, value)

    def click_all_checkboxes(self, page: Any) -> Any:
        return self.call(page, "clickAllCheckboxes")

    def wait_for_discord_token(self, page: Any, timeout: int = 5000) -> Any:
        return self.call(page, "waitForDiscordToken", timeout)
