"""
FluxMart — Nuitka Build Script
Compiles the project into a single Windows EXE using Nuitka.

Usage:
  python exe.py               # normal build
  python exe.py --skip-clean  # keep previous build cache
  python exe.py --delete-source  # wipe source after build
"""

import os
import sys
import shutil
import subprocess
import site
import stat
import time
import importlib.util
from pathlib import Path


OUTPUT_NAME = "FluxMart"
DIST_DIR    = "dist"
BUILD_DIR   = "build"
ENTRY_POINT = "gui_main.py"

MIN_DISK_GB = 4.0
MIN_RAM_GB  = 2.0


def _banner(text: str, char: str = "=", width: int = 72):
    print(f"\n{char * width}")
    print(f"   {text}")
    print(f"{char * width}")

def _step(n: int, total: int, label: str):
    print(f"\n[{n}/{total}] {label} ...")

def _ok(msg: str):   print(f"  [OK]   {msg}")
def _info(msg: str): print(f"  [>>]   {msg}")
def _warn(msg: str): print(f"  [!]    {msg}")
def _fail(msg: str): print(f"\n  [FAIL] {msg}")


def module_exists(name: str) -> bool:
    """Return True if a top-level module/package is importable."""
    try:
        return importlib.util.find_spec(name.split(".")[0]) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def find_package_dir(pkg: str) -> str | None:
    """Return the filesystem directory of a package, or None."""
    try:
        spec = importlib.util.find_spec(pkg)
        if spec:
            if spec.origin:
                return os.path.dirname(spec.origin)
            locs = list(spec.submodule_search_locations or [])
            if locs:
                return locs[0]
    except Exception:
        pass
    for sp in (site.getsitepackages() or []) + [site.getusersitepackages()]:
        cand = os.path.join(sp, pkg)
        if os.path.isdir(cand):
            return cand
    return None


def force_rmtree(path: str, retries: int = 5, delay: float = 2.0) -> bool:
    """Forcefully remove a directory tree, killing locking processes if needed."""

    def _onerror(func, fpath, _exc):
        try:
            os.chmod(fpath, stat.S_IWRITE)
            func(fpath)
        except Exception:
            pass

    for attempt in range(retries):
        if not os.path.exists(path):
            return True
        try:
            shutil.rmtree(path, onerror=_onerror)
        except Exception:
            pass
        if not os.path.exists(path):
            return True
        if attempt < retries - 1:
            for proc in ["cc1plus.exe", "gcc.exe", "g++.exe", "ld.exe", "as.exe"]:
                try:
                    subprocess.run(["taskkill", "/F", "/IM", proc],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
            time.sleep(delay)

    try:
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", path],
                       capture_output=True, timeout=30)
    except Exception:
        pass
    return not os.path.exists(path)


def check_python_version():
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 11):
        _fail(f"Python 3.11+ required — found {major}.{minor}")
        sys.exit(1)
    _ok(f"Python {major}.{minor}")


def check_disk_space():
    try:
        _, _, free = shutil.disk_usage(".")
        free_gb = free / 1024 ** 3
        if free_gb < MIN_DISK_GB:
            _warn(f"Only {free_gb:.1f} GB free — need ≥{MIN_DISK_GB} GB.  Build may fail.")
        else:
            _ok(f"Disk space: {free_gb:.1f} GB free")
    except Exception:
        pass


def check_ram():
    try:
        import psutil
        avail_gb = psutil.virtual_memory().available / 1024 ** 3
        if avail_gb < MIN_RAM_GB:
            _warn(f"Only {avail_gb:.1f} GB RAM available — Nuitka needs ≥{MIN_RAM_GB} GB")
        else:
            _ok(f"RAM available: {avail_gb:.1f} GB")
    except ImportError:
        pass


def check_antivirus_note():
    print()
    print("  ┌────────────────────────────────────────────────────────────────┐")
    print("  │  ANTI-VIRUS NOTE                                               │")
    print("  │  Nuitka EXEs are often false-flagged by Windows Defender / AV. │")
    print("  │  Add the dist/ folder to your AV exclusion list BEFORE running  │")
    print("  │  or distributing the EXE to prevent false positives.            │")
    print("  └────────────────────────────────────────────────────────────────┘")


def get_nuitka_major_version() -> int:
    """Return the installed Nuitka major version number (e.g. 4 for 4.0.7), or 0 on failure."""
    try:
        r = subprocess.run([sys.executable, "-m", "nuitka", "--version"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            first_line = r.stdout.strip().splitlines()[0]
            ver_str = first_line.split()[0]
            return int(ver_str.split(".")[0])
    except Exception:
        pass
    return 0


def check_nuitka() -> bool:
    try:
        r = subprocess.run([sys.executable, "-m", "nuitka", "--version"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            _ok(f"Nuitka: {r.stdout.strip().splitlines()[0]}")
            return True
    except Exception:
        pass
    _info("Nuitka not found — installing...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install",
         "nuitka>=4.0", "ordered-set", "zstandard", "--upgrade", "-q"])
    if r.returncode != 0:
        _fail("Cannot install Nuitka.  Run: pip install nuitka ordered-set zstandard")
        return False
    _ok("Nuitka installed")
    return True


def check_nuitka_gcc_cache():
    """
    Validate Nuitka's winlibs-GCC cache.
    Wipes incomplete downloads so Nuitka re-downloads a clean compiler.
    """
    gcc_base = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Nuitka", "Nuitka", "Cache", "downloads", "gcc", "x86_64"
    )
    if not os.path.isdir(gcc_base):
        _info("No Nuitka GCC cache — Nuitka will download compiler on first use")
        return
    for ver in os.listdir(gcc_base):
        vpath = os.path.join(gcc_base, ver)
        if not os.path.isdir(vpath):
            continue
        windows_h = os.path.join(
            vpath, "mingw64", "x86_64-w64-mingw32", "include", "windows.h"
        )
        if not os.path.exists(windows_h):
            _warn(f"Corrupt Nuitka GCC cache (no windows.h): {ver}")
            if force_rmtree(vpath):
                _ok(f"Removed corrupt cache: {ver}")
            else:
                _warn(f"Could not remove {vpath} — delete manually if build fails")
        else:
            _ok(f"Nuitka GCC cache OK: {ver}")


REQUIRED_PACKAGES = [
    ("nuitka",          "nuitka>=4.0"),
    ("ordered_set",     "ordered-set"),
    ("zstandard",       "zstandard"),
    ("flask",           "flask"),
    ("webview",         "pywebview"),
    ("requests",        "requests"),
    ("tls_client",      "tls-client"),
    ("greenlet",        "greenlet"),
    ("rich",            "rich"),
    ("certifi",         "certifi"),
    ("urllib3",         "urllib3"),
    ("cryptography",    "cryptography"),
    ("psutil",          "psutil"),
    ("pystyle",         "pystyle"),
    ("groq",            "groq"),
    ("deep_translator", "deep-translator"),
    ("cybertemp",       "cybertemp"),
    ("emoji",           "emoji"),
    ("grapheme",        "grapheme"),
    ("mss",             "mss"),
    ("browserforge",    "browserforge"),
    ("language_tags",   "language-tags"),
    ("logmagix",        "logmagix"),
    ("websockets",      "websockets"),
    ("websocket",       "websocket-client"),
    ("colorama",        "colorama"),
    ("jsonlines",       "jsonlines"),
    ("PIL",             "pillow"),
    ("Faker",           "faker"),
    ("bs4",             "beautifulsoup4"),
    ("pydantic",        "pydantic"),
    ("httpx",           "httpx"),
    ("aiohttp",         "aiohttp"),
    ("dns",             "dnspython"),
    ("yaml",            "PyYAML"),
    ("Crypto",          "pycryptodome"),
    ("pybase64",        "pybase64"),
    ("win32api",        "pywin32"),
    ("pymongo",         "pymongo"),
    ("curl_cffi",       "curl-cffi"),
    ("primp",           "primp"),
    ("camoufox",        "camoufox"),
    ("truedriver",      "truedriver"),
]


def ensure_packages():
    missing = [pip for imp, pip in REQUIRED_PACKAGES if not module_exists(imp)]
    if not missing:
        _ok("All required packages present")
        return
    _warn(f"Missing: {', '.join(missing)}")
    _info("Installing missing packages ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install"] + missing + ["-q"])
    _ok("Package install complete")


def fix_non_utf8_sources():
    """
    Scan site-packages for .py files containing non-UTF-8 bytes and fix them.
    Known offender: nodriver/truedriver cdp/network.py ships with a Latin-1 ± (0xb1)
    character that crashes Nuitka's source reader.
    """
    sp_dirs = site.getsitepackages() or []
    fixed = 0
    for sp in sp_dirs:
        if not os.path.isdir(sp):
            continue
        for root, _, files in os.walk(sp):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as fh:
                        fh.read()
                except UnicodeDecodeError:
                    try:
                        with open(fpath, "rb") as fh:
                            raw = fh.read()
                        clean = raw.decode("latin-1").encode("utf-8")
                        with open(fpath, "wb") as fh:
                            fh.write(clean)
                        fixed += 1
                        _info(f"Fixed non-UTF-8 encoding: {os.path.relpath(fpath, sp)}")
                    except Exception as exc:
                        _warn(f"Could not fix {fpath}: {exc}")
                except Exception:
                    pass
    if fixed:
        _ok(f"Fixed {fixed} non-UTF-8 source file(s)")
    else:
        _ok("All source files are valid UTF-8")


def find_tls_client_dll() -> str | None:
    """
    Locate tls_client's precompiled native DLL.
    The DLL may be named anything (tls-client-windows-64-xxx.dll, etc.)
    and can live at the package root or in a subdirectory.
    We embed it explicitly with --include-data-files.
    """
    pkg = find_package_dir("tls_client")
    if not pkg:
        return None
    for root, _, files in os.walk(pkg):
        for name in files:
            nl = name.lower()
            if nl.endswith(".dll"):
                return os.path.join(root, name)
    return None


def find_greenlet_pyd() -> str | None:
    """
    Locate greenlet's compiled .pyd extension.
    Without it, greenlet (and therefore truedriver's async loop) silently breaks.
    """
    try:
        import greenlet as _gl
        pyd = getattr(_gl, "__file__", None)
        if pyd and pyd.endswith(".pyd") and os.path.isfile(pyd):
            return pyd
    except Exception:
        pass
    pkg = find_package_dir("greenlet")
    if not pkg:
        return None
    for root, _, files in os.walk(pkg):
        for f in files:
            if f.startswith("_greenlet") and f.endswith(".pyd"):
                return os.path.join(root, f)
    return None


def find_pywin32_dlls() -> list[str]:
    """
    Locate pywin32's system DLLs (pythoncom*.dll, pywintypes*.dll).
    These are placed in the Python root, NOT inside a package directory,
    so Nuitka never finds them automatically.

    Deduplication: pywin32 ships the same DLLs in *both* the Python root
    and site-packages/pywin32_system32.  Including both paths causes Nuitka
    to raise "duplicate destination filename" conflicts.  We deduplicate by
    filename, preferring the Python root copy (which Windows already has on
    PATH) over the site-packages copy.
    """
    seen: dict[str, str] = {}

    python_dir = os.path.dirname(sys.executable)
    for fname in os.listdir(python_dir):
        fl = fname.lower()
        if fl.startswith(("pythoncom", "pywintypes")) and fl.endswith(".dll"):
            seen[fl] = os.path.join(python_dir, fname)

    for sp in (site.getsitepackages() or []):
        sysdir = os.path.join(sp, "pywin32_system32")
        if os.path.isdir(sysdir):
            for fname in os.listdir(sysdir):
                fl = fname.lower()
                if fl.endswith(".dll") and fl not in seen:
                    seen[fl] = os.path.join(sysdir, fname)

    return list(seen.values())


def get_browserforge_data_dir() -> str:
    try:
        from browserforge.download import DATA_DIR
        return str(DATA_DIR)
    except Exception:
        return str(Path.home() / ".browserforge")


def pre_download_browserforge():
    _info("Ensuring browserforge fingerprint data is available...")
    try:
        try:
            from browserforge.download import DownloadManager
            DownloadManager().download()
        except ImportError:
            import browserforge.download as bfd
            if hasattr(bfd, "download_all"):
                bfd.download_all()
            elif hasattr(bfd, "download"):
                bfd.download()
        _ok("Browserforge data ready")
    except Exception as exc:
        _warn(f"Browserforge download skipped: {exc}")


INCLUDE_PACKAGES = [
    "MSK_core",
    "MSK_core.Utils",
    "MSK_core.Helper",
    "MSK_core.WorkFlow",
    "MSK_core.MskColors",

    "flask",
    "jinja2",
    "markupsafe",
    "werkzeug",
    "itsdangerous",
    "click",
    "blinker",
    "webview",

    "requests",
    "tls_client",
    "urllib3",
    "certifi",
    "charset_normalizer",
    "idna",
    "cryptography",
    "curl_cffi",
    "primp",
    "httpx",
    "httpcore",
    "h2",
    "hpack",
    "hyperframe",

    "aiohttp",
    "aiofiles",
    "aiosignal",
    "aiohappyeyeballs",
    "asyncio",
    "anyio",
    "sniffio",
    "async_timeout",

    "truedriver",
    "websockets",
    "websocket",
    "emoji",
    "grapheme",
    "mss",
    "deprecated",
    "wrapt",
    "greenlet",

    "browserforge",
    "language_tags",
    "apify_fingerprint_datapoints",
    "ua_parser",
    "ua_parser_builtins",

    "camoufox",

    "playwright",
    "rebrowser_playwright",
    "patchright",
    "DrissionPage",
    "pyee",

    "lxml",
    "cssselect",

    "rich",
    "pystyle",
    "colorama",
    "Pygments",

    "PIL",
    "numpy",

    "pydantic",
    "pydantic_core",
    "orjson",
    "yaml",
    "jsonlines",
    "bs4",
    "beautifulsoup4",

    "Crypto",
    "cryptography",
    "pybase64",
    "PyNaCl",

    "cybertemp",

    "deep_translator",

    "groq",

    "logmagix",

    "socks",
    "dns",
    "tldextract",
    "geoip2",
    "maxminddb",
    "proxy_tools",

    "faker",
    "Faker",

    "pytz",
    "tzdata",
    "tzlocal",
    "dateutil",

    "psutil",
    "win32api",
    "win32con",
    "win32gui",
    "win32security",
    "pywintypes",
    "uiautomation",

    "pymongo",

    "frozenlist",
    "multidict",
    "yarl",
    "propcache",
    "attrs",

    "concurrent",
    "threading",
    "multiprocessing",

    "flask_cors",

    "requests_file",

    "webencodings",
    "defusedxml",
    "soupsieve",

    "tqdm",
    "filelock",
    "packaging",
    "six",
    "pyperclip",
    "dotenv",
    "python_dotenv",
    "distro",
    "platformdirs",
    "sortedcontainers",
    "cffi",
    "pycparser",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
    "tomli",
    "markdown_it",
    "mdurl",
    "indexed_zstd",
]

INCLUDE_PACKAGE_DATA = [
    "tls_client",
    "truedriver",
    "emoji",
    "grapheme",
    "mss",
    "browserforge",
    "language_tags",
    "apify_fingerprint_datapoints",
    "ua_parser",
    "ua_parser_builtins",
    "camoufox",
    "playwright",
    "rebrowser_playwright",
    "patchright",
    "certifi",
    "webview",
    "flask",
    "jinja2",
    "werkzeug",
    "greenlet",
    "cryptography",
    "Crypto",
    "curl_cffi",
    "primp",
    "geoip2",
    "maxminddb",
    "PIL",
    "rich",
    "faker",
    "Faker",
]

NOFOLLOW = [
    "tkinter",
    "unittest",
    "test",
    "distutils",
    "setuptools",
    "pip",
    "pdb",
    "doctest",
    "lib2to3",
    "webview.platforms.android",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.qt",
    "PIL._avif",
    "PIL._imagingtk",
    "numpy.core.tests",
    "numpy.tests",
    "numpy.f2py.tests",
    "numpy.linalg.tests",
    "numpy.ma.tests",
    "numpy.matrixlib.tests",
    "numpy.polynomial.tests",
    "numpy.random.tests",
    "numpy.testing",
    "websocket.policyserver",
    "websocket.server",
]


def get_missing_pil_nofollow() -> list[str]:
    """
    Return a list of --nofollow-import-to entries for optional Pillow .pyd
    extension modules that are NOT present in the user's Pillow installation.

    Pillow conditionally compiles many codec extensions (AVIF, TIFF, WebP,
    JPEG 2000, …) depending on which C libraries are available at compile time.
    When a .pyd file is missing and Nuitka's DLL copier tries to include it,
    the build fails with a FileNotFoundError.

    This function scans the PIL package directory for every known optional
    extension module and adds it to the nofollow list when its .pyd is absent.
    """
    OPTIONAL_PIL_EXTS = [
        "PIL._avif",
        "PIL._webp",
        "PIL._imagingtk",
        "PIL._imaging",
        "PIL._imagingcms",
        "PIL._imagingft",
        "PIL._imagingmath",
        "PIL._imagingmorph",
        "PIL._imagingtiff",
        "PIL._jpeg2000",
        "PIL._libtiff",
        "PIL._lzma",
        "PIL._zlib",
    ]

    pil_dir = find_package_dir("PIL")
    if not pil_dir:
        return []

    missing = []
    for full_mod in OPTIONAL_PIL_EXTS:
        mod_name = full_mod.split(".")[-1]
        found = False
        for fname in os.listdir(pil_dir):
            if fname.startswith(mod_name) and fname.endswith(".pyd"):
                found = True
                break
        if not found:
            missing.append(full_mod)

    return missing


INCLUDE_MODULES = [
    "json", "hashlib", "uuid", "threading", "ctypes", "socket", "getpass",
    "platform", "subprocess", "pathlib", "typing", "datetime", "warnings",
    "re", "logging", "urllib", "urllib.parse", "urllib.request", "contextlib",
    "ssl", "imaplib", "email", "email.mime", "email.mime.text", "email.mime.multipart",
    "email.parser", "email.header",
    "asyncio", "concurrent.futures", "multiprocessing", "multiprocessing.managers",
    "multiprocessing.pool",

    "rich.console", "rich.text", "rich.progress", "rich.table", "rich.panel",
    "rich.style", "rich.color", "rich.markup", "rich.highlighter",
    "rich.live", "rich.spinner", "rich.traceback", "rich.logging",

    "requests.adapters", "requests.sessions", "requests.auth", "requests.cookies",

    "flask.templating", "flask.json", "flask.globals",
    "jinja2.ext", "jinja2.utils",
    "werkzeug.serving", "werkzeug.routing", "werkzeug.exceptions",
    "werkzeug.middleware",

    "webview.platforms", "webview.platforms.edgechromium",
    "webview.platforms.winforms", "webview.platforms.cef",

    "tls_client.sessions", "tls_client.cookies",

    "truedriver.core", "truedriver.cdp",
    "truedriver.core.config",
    "truedriver.cdp.input_",
    "truedriver.cdp.page",
    "truedriver.cdp.network",
    "truedriver.cdp.emulation",
    "truedriver.cdp.fetch",

    "playwright.sync_api", "playwright._impl._connection",
    "rebrowser_playwright.sync_api",

    "browserforge.fingerprints", "browserforge.headers",
    "browserforge.injectors",

    "language_tags.tags",

    "deep_translator.google", "deep_translator.constants",

    "groq._client", "groq.types",

    "greenlet._greenlet",

    "emoji.unicode_codes", "emoji.unicode_codes.data_dict",

    "pydantic.v1",

    "win32api", "win32con", "win32gui", "win32security", "pywintypes",
    "win32process", "win32event",

    "httpx._client",

    "aiohttp.connector", "aiohttp.client",

    "pystyle", "grapheme", "mss", "websockets", "websocket",
    "deprecated", "certifi", "charset_normalizer", "idna", "urllib3",
    "cryptography", "psutil", "jsonlines", "pybase64", "logmagix",
    "colorama", "Pygments", "PIL", "PIL.Image", "PIL.ImageDraw",
    "bs4", "lxml", "lxml.etree", "yaml",
    "dns", "dns.resolver", "dns.name",
    "socks", "tldextract",
    "pymongo", "pymongo.collection", "pymongo.database",
    "curl_cffi", "curl_cffi.requests",
    "primp",
    "groq",
    "faker", "Faker",
    "uiautomation",

    "MSK_core.Utils.geo_lookup",
    "MSK_core.Utils.proxy_auth_server",
    "MSK_core.Utils.proxy_auth_extension",
    "MSK_core.Utils.proxy_manager",
    "MSK_core.Utils.training_logger",
    "MSK_core.Utils.custom_ai",
    "MSK_core.Utils.custom_fingerprint",
    "MSK_core.Utils.auto_login",
    "MSK_core.Utils.anticrack",
    "MSK_core.Utils.fivesim",
    "MSK_core.Utils.onlinesim",
    "MSK_core.Utils.hero_sms",
    "MSK_core.Utils.mullvad_manager",
    "MSK_core.Utils.window_manager",
    "MSK_core.Utils.logger",
    "MSK_core.Utils.intro",
    "MSK_core.Utils.keyauth",
    "MSK_core.MskColors.color",
    "MSK_core.WorkFlow.email_pool",
    "MSK_core.WorkFlow.text_solver_truedriver",
    "MSK_core.WorkFlow.captcha_solver",
    "MSK_core.WorkFlow.discord_register_chromium",
    "MSK_core.WorkFlow.discord_register_brave",
    "MSK_core.WorkFlow.discord_register",
    "MSK_core.WorkFlow.verifier",
    "MSK_core.WorkFlow.token_checker",
    "MSK_core.Helper.huminazer",
    "MSK_core.Helper.build_info",
    "MSK_core.Helper.discord",
    "MSK_core.Helper.mail",

    "camoufox.sync_api",
]


STATIC_DATA_DIRS = [
    ("MSK_core/Assets",      "MSK_core/Assets"),
    ("MSK_core/JS",          "MSK_core/JS"),
    ("templates",            "templates"),
    ("static",               "static"),
]

OUTPUT_FILES  = [
    "tokens.txt", "invalid.txt", "locked.txt",
    "checked_valid.txt", "checked_invalid.txt",
    "linkverify.txt", "tokenSplited.txt", "humanized.txt",
]
INPUT_FILES   = ["proxies.txt", "cybertemp_domains.txt", "Numbers.txt", "fingerprints.txt"]
PROFILE_FILES = ["bio.txt", "names.txt", "pronouns.txt"]


def clean_build():
    stems = [OUTPUT_NAME, "gui_main", "main", "dist", "build"]
    suffixes = [".build", ".dist", ".onefile-build"]
    dirs = [s + sx for s in stems for sx in suffixes] + ["dist", "build"]
    removed = []
    for d in dirs:
        if os.path.exists(d):
            if force_rmtree(d):
                removed.append(d)
            else:
                _warn(f"Could not remove {d} — close any programs holding it")
    if removed:
        _info(f"Removed: {', '.join(removed)}")
    else:
        _info("No previous build artefacts found")


def _find_icon() -> str | None:
    """Search common icon paths in order of preference."""
    candidates = [
        "msklogo.ico",
        "msk-logo.ico",
        "static/img/icon.ico",
        "static/img/msklogo.png",
        "msk-logo.png",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def build_exe() -> bool:
    _info("Discovering native binary files ...")

    tls_dll      = find_tls_client_dll()
    greenlet_pyd = find_greenlet_pyd()
    pw32_dlls    = find_pywin32_dlls()
    bf_data      = get_browserforge_data_dir()

    if tls_dll:
        _ok(f"tls_client DLL   : {os.path.basename(tls_dll)}")
    else:
        _warn("tls_client DLL not found — token checking may silently fail on clean PCs")

    if greenlet_pyd:
        _ok(f"greenlet .pyd    : {os.path.basename(greenlet_pyd)}")
    else:
        _warn("greenlet .pyd not found — async/CDP pipeline may fail")

    if pw32_dlls:
        _ok(f"pywin32 DLLs     : {[os.path.basename(d) for d in pw32_dlls]}")
    else:
        _warn("pywin32 DLLs not found — Windows API calls may fail")

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--mingw64",
        f"--output-filename={OUTPUT_NAME}.exe",
        "--windows-console-mode=disable",
        "--follow-imports",
        "--assume-yes-for-downloads",
        "--enable-plugin=anti-bloat",
        "--remove-output",
        f"--onefile-tempdir-spec={{TEMP}}\\MSK_{OUTPUT_NAME}",
        "--windows-product-name=FluxMart",
        "--windows-company-name=MSK",
        "--windows-file-description=FluxMart - Discord Account Manager",
        "--windows-product-version=1.0.0.0",
        "--windows-file-version=1.0.0.0",
    ]

    icon = _find_icon()
    if icon:
        cmd.append(f"--windows-icon-from-ico={icon}")
        _ok(f"Icon             : {icon}")
    else:
        _warn("No icon file found — EXE will use the default Windows icon")

    all_nofollow = list(NOFOLLOW)
    missing_pil = get_missing_pil_nofollow()
    if missing_pil:
        _info(f"Excluding {len(missing_pil)} missing optional PIL extension(s): "
              f"{', '.join(m.split('.')[-1] for m in missing_pil)}")
        all_nofollow.extend(missing_pil)
    for nf in all_nofollow:
        cmd.append(f"--nofollow-import-to={nf}")

    for pkg in INCLUDE_PACKAGES:
        root = pkg.split(".")[0]
        if module_exists(root):
            cmd.append(f"--include-package={pkg}")

    for pkg in INCLUDE_PACKAGE_DATA:
        if module_exists(pkg.split(".")[0]):
            cmd.append(f"--include-package-data={pkg}")

    seen_mods = set()
    for mod in INCLUDE_MODULES:
        root = mod.split(".")[0]
        if module_exists(root) and mod not in seen_mods:
            cmd.append(f"--include-module={mod}")
            seen_mods.add(mod)

    _info("Skipping static data dir embedding (templates/static are distributed externally — keeps EXE lean)")


    if os.path.isdir(bf_data):
        cmd.append(f"--include-data-dir={bf_data}=browserforge_data")
        _info(f"Embedding browserforge data: {bf_data}")

    if tls_dll:
        cmd.append(
            f"--include-data-files={tls_dll}=tls_client/{os.path.basename(tls_dll)}"
        )

    nuitka_ver = get_nuitka_major_version()

    if greenlet_pyd and 0 < nuitka_ver < 4:
        cmd.append(
            f"--include-data-files={greenlet_pyd}=greenlet/{os.path.basename(greenlet_pyd)}"
        )

    if 0 < nuitka_ver < 4:
        for dll_path in pw32_dlls:
            cmd.append(f"--include-data-files={dll_path}={os.path.basename(dll_path)}")

    curl_dir = find_package_dir("curl_cffi")
    if curl_dir:
        for root, _, files in os.walk(curl_dir):
            for f in files:
                if f.endswith((".dll", ".so")) and not f.endswith(".pyd"):
                    src_f = os.path.join(root, f)
                    rel   = os.path.relpath(src_f, os.path.dirname(curl_dir))
                    cmd.append(f"--include-data-files={src_f}={rel}")

    cmd.append(ENTRY_POINT)

    for bd in [f"{OUTPUT_NAME}.build", "gui_main.build", "main.build"]:
        if os.path.exists(bd):
            _warn(f"Leftover build dir: {bd} — removing ...")
            if not force_rmtree(bd):
                _fail(f"Cannot remove {bd}.  Close any programs using it and retry.")
                return False

    print(f"\n  [>>]   Nuitka: {sys.executable} -m nuitka ... ({len(cmd)} arguments)")
    print(  "  [>>]   This usually takes 10–25 minutes.  Do not close this window.\n")

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            encoding="utf-8", errors="replace",
        )
        for line in iter(proc.stdout.readline, ""):
            print(line, end="", flush=True)
        proc.wait()
    except Exception as exc:
        _fail(f"Build process error: {exc}")
        return False

    elapsed = time.time() - t0
    if proc.returncode != 0:
        _fail(f"Nuitka exited with code {proc.returncode} after {elapsed:.0f}s")
        _print_failure_guide()
        return False

    _ok(f"Compilation complete in {elapsed:.0f}s")
    return True


def _print_failure_guide():
    print()
    print("  ──────────────── BUILD FAILURE GUIDE ────────────────────────────")
    print("  1. 'windows.h not found' / GCC errors")
    print("     → Delete: %LOCALAPPDATA%\\Nuitka\\Nuitka\\Cache\\downloads\\gcc")
    print("       then re-run exe.py.  Nuitka will download a fresh compiler.")
    print()
    print("  2. AssertionError about existing .c files (leftover build dir)")
    print("     → Delete all *.build folders in this directory, then re-run.")
    print()
    print("  3. ModuleNotFoundError during compilation")
    print("     → Run installer.bat, then re-run exe.py.")
    print()
    print("  4. Disk full / out of memory")
    print("     → Free ≥4 GB disk and ≥2 GB RAM, then retry.")
    print()
    print("  5. Anti-virus killed the compiler")
    print("     → Add this project folder to your AV exclusion list.")
    print()
    print("  6. FileNotFoundError: No such file or directory: '...PIL\\_avif...'")
    print("     or any other PIL/Pillow *.pyd file missing during DLL copy:")
    print("     → This is a Pillow optional codec extension that was not compiled")
    print("       on your machine (e.g. _avif requires libavif).")
    print("     → exe.py auto-detects and excludes missing PIL extensions.")
    print("       If you still hit this, reinstall Pillow:  pip install -U pillow")
    print("       then re-run exe.py.")
    print()
    print("  7. FileNotFoundError for any other *.pyd / *.dll during DLL copy")
    print("     → The package was partially installed or the file was quarantined")
    print("       by AV.  Reinstall the affected package and re-run exe.py.")
    print("  ─────────────────────────────────────────────────────────────────")


def post_build() -> bool:
    """Move EXE into dist/, copy external data, scaffold empty input/output files."""
    os.makedirs(DIST_DIR, exist_ok=True)

    exe_src = f"{OUTPUT_NAME}.exe"
    if os.path.exists(exe_src):
        exe_dst = os.path.join(DIST_DIR, exe_src)
        shutil.move(exe_src, exe_dst)
        size_mb = os.path.getsize(exe_dst) / 1024 ** 2
        _ok(f"EXE: {exe_dst}  ({size_mb:.1f} MB)")
        if size_mb < 10:
            _warn(f"EXE is only {size_mb:.1f} MB — may be incomplete.  Check build log.")
    else:
        found = [f for f in os.listdir(".") if f.endswith(".exe")]
        if found:
            for f in found:
                shutil.move(f, os.path.join(DIST_DIR, f))
                _ok(f"Moved: {f}")
        else:
            _warn("No EXE found in current directory after build!")

    for src, dest in STATIC_DATA_DIRS:
        dst = os.path.join(DIST_DIR, dest)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            _ok(f"Copied: {src}  →  {dst}")

    bf_data = get_browserforge_data_dir()
    if os.path.isdir(bf_data):
        dst_bf = os.path.join(DIST_DIR, "browserforge_data")
        if os.path.exists(dst_bf):
            shutil.rmtree(dst_bf)
        shutil.copytree(bf_data, dst_bf)
        _ok(f"Copied browserforge data → {dst_bf}")

    src_data = "data"
    dst_data = os.path.join(DIST_DIR, "data")
    if os.path.isdir(src_data):
        if os.path.exists(dst_data):
            shutil.rmtree(dst_data)
        shutil.copytree(src_data, dst_data)
        _ok(f"Copied: data → {dst_data}")
    else:
        os.makedirs(dst_data, exist_ok=True)

    input_dir    = os.path.join(dst_data, "input")
    output_dir   = os.path.join(dst_data, "output")
    profiles_dir = os.path.join(input_dir, "profiles")
    avatars_dir  = os.path.join(profiles_dir, "avatars")
    temp_dir     = os.path.join(dst_data, "temp")
    training_dir = os.path.join(dst_data, "training_data")

    for d in (input_dir, output_dir, profiles_dir, avatars_dir, temp_dir, training_dir):
        os.makedirs(d, exist_ok=True)

    for sub in ("success", "failure", "sessions", "models", "analysis", "cache"):
        os.makedirs(os.path.join(training_dir, sub), exist_ok=True)

    for fname in INPUT_FILES:
        p = os.path.join(input_dir, fname)
        if not os.path.exists(p):
            Path(p).touch()

    for fname in OUTPUT_FILES:
        p = os.path.join(output_dir, fname)
        if not os.path.exists(p):
            Path(p).touch()

    for fname in PROFILE_FILES:
        p = os.path.join(profiles_dir, fname)
        if not os.path.exists(p):
            Path(p).touch()

    trans = os.path.join(dst_data, "translations.json")
    if not os.path.exists(trans):
        Path(trans).write_text("{}", encoding="utf-8")

    INSTALLER_DIR = "Installer-check me"
    helper_scripts = [
        ("start.bat", "start.bat"),
        (os.path.join(INSTALLER_DIR, "installer.bat"),    "installer.bat"),
        (os.path.join(INSTALLER_DIR, "check_deps.bat"),   "check_deps.bat"),
        (os.path.join(INSTALLER_DIR, "check_deps.py"),    "check_deps.py"),
        ("locked-problem.bat", "locked-problem.bat"),
    ]
    for src, dst_name in helper_scripts:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(DIST_DIR, dst_name))
            _ok(f"Copied: {dst_name}")

    _ok("Post-build packaging complete")
    return True


def verify_dist() -> bool:
    issues = []

    exe = os.path.join(DIST_DIR, f"{OUTPUT_NAME}.exe")
    if not os.path.exists(exe):
        issues.append(f"EXE missing: {exe}")
    else:
        size_mb = os.path.getsize(exe) / 1024 ** 2
        if size_mb < 10:
            issues.append(f"EXE suspiciously small: {size_mb:.1f} MB (expected ≥10 MB)")

    required_dirs = [
        os.path.join(DIST_DIR, "data", "input"),
        os.path.join(DIST_DIR, "data", "output"),
        os.path.join(DIST_DIR, "templates"),
        os.path.join(DIST_DIR, "static"),
        os.path.join(DIST_DIR, "MSK_core", "Assets"),
        os.path.join(DIST_DIR, "MSK_core", "JS"),
    ]
    for d in required_dirs:
        if not os.path.isdir(d):
            issues.append(f"Missing: {d}")

    if issues:
        _warn("Verification issues found:")
        for iss in issues:
            _warn(f"  • {iss}")
        return False

    _ok("dist/ verified — all required files and folders present")
    return True


SOURCE_ITEMS = [
    "main.py", "gui_main.py", "MSK_core",
    "templates", "static", "requirements.txt", "exe.py",
]


def cleanup_source(delete_source: bool):
    if not delete_source:
        _info("Source preserved  (pass --delete-source to remove after build)")
        return
    _info("Deleting source files ...")
    for item in SOURCE_ITEMS:
        if os.path.exists(item):
            shutil.rmtree(item) if os.path.isdir(item) else os.remove(item)
            _info(f"Deleted: {item}")


TOTAL_STEPS = 9


def main() -> int:
    t_start = time.time()
    _banner("FluxMart  -  Nuitka Build Script")
    print(f"   Python : {sys.version.split()[0]}")
    print(f"   Output : {DIST_DIR}/{OUTPUT_NAME}.exe")
    print(f"   Entry  : {ENTRY_POINT}")

    delete_source = "--delete-source" in sys.argv
    skip_clean    = "--skip-clean"    in sys.argv

    _step(1, TOTAL_STEPS, "System checks")
    check_python_version()
    check_disk_space()
    check_ram()
    check_antivirus_note()

    _step(2, TOTAL_STEPS, "Verifying Nuitka")
    if not check_nuitka():
        return 1

    _step(3, TOTAL_STEPS, "Checking Nuitka GCC cache")
    check_nuitka_gcc_cache()

    _step(4, TOTAL_STEPS, "Checking required packages")
    ensure_packages()

    _info("Checking source file encodings ...")
    fix_non_utf8_sources()

    _step(5, TOTAL_STEPS, "Preparing data assets")
    pre_download_browserforge()

    _step(6, TOTAL_STEPS, "Cleaning previous build")
    if skip_clean:
        _info("Skipping clean (--skip-clean flag)")
    else:
        clean_build()

    _step(7, TOTAL_STEPS, "Scanning native binary files")

    _step(8, TOTAL_STEPS, "Building EXE with Nuitka")
    if not build_exe():
        _fail("Build failed — see above for details")
        return 1

    _step(9, TOTAL_STEPS, "Post-build packaging and verification")
    if not post_build():
        _fail("Post-build failed")
        return 1

    verify_dist()
    cleanup_source(delete_source)

    elapsed = time.time() - t_start
    _banner(f"BUILD SUCCESSFUL  —  finished in {elapsed:.0f}s")
    exe_path = os.path.abspath(os.path.join(DIST_DIR, f"{OUTPUT_NAME}.exe"))
    print(f"\n   EXE : {exe_path}")
    print()
    print("   WHAT TO DISTRIBUTE (all four items must stay next to the EXE):")
    print("     dist/FluxMart.exe")
    print("     dist/data/             ← config, proxies, tokens  (writable)")
    print("     dist/templates/        ← Flask HTML")
    print("     dist/static/           ← CSS / JS / images")
    print("     dist/browserforge_data/ ← fingerprint database")
    print()
    print("   REQUIREMENTS ON TARGET PC:")
    print("     • Windows 10/11 x64")
    print("     • Brave Browser (https://brave.com/download) OR Google Chrome")
    print("     • Microsoft Visual C++ Redistributable x64 2015-2022")
    print("       https://aka.ms/vs/17/release/vc_redist.x64.exe")
    print()
    print("   TROUBLESHOOTING:")
    print("     • Tokens invalid/locked  → run dist/check_deps.bat")
    print("     • EXE blocked by AV      → whitelist dist/ in your AV settings")
    print("     • EXE won't start        → run as Administrator")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
