"""Centralized environment detection and path resolution.

This module is the SINGLE SOURCE OF TRUTH for:
  - Detecting whether we're running as a compiled executable (Nuitka / PyInstaller)
  - Resolving the application base path
  - Building resource paths

Every other module must import from here instead of duplicating this logic.
"""
import os
import sys
from typing import Optional


def is_frozen() -> bool:
    """Check if running as compiled executable (Nuitka or PyInstaller).

    Uses multiple detection strategies for maximum reliability:
      1. sys.frozen (PyInstaller / some Nuitka builds)
      2. __compiled__ (Nuitka-specific global)
      3. sys.executable heuristic -- if sys.executable does NOT end with
         'python.exe' or 'pythonw.exe', we're almost certainly inside a
         compiled EXE.
    """
    if getattr(sys, 'frozen', False):
        return True
    try:
        # noinspection PyUnresolvedReferences
        return bool(__compiled__)  # type: ignore[name-defined]
    except NameError:
        pass
    exe_name = os.path.basename(sys.executable).lower()
    if exe_name not in ('python.exe', 'pythonw.exe', 'python', 'pythonw',
                         'python3.exe', 'python3'):
        return True
    return False


def _find_base_path_frozen() -> str:
    """Search for the project root when running as a compiled EXE.

    Searches multiple candidate directories in priority order and picks the
    first one that contains a 'data/' subfolder.  This makes the EXE work
    correctly regardless of whether it lives in dist/, in the project root,
    or in any other location -- as long as 'data/' is nearby.
    """
    candidates = []

    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass

    try:
        candidates.append(os.getcwd())
    except Exception:
        pass

    try:
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass

    extended = []
    for c in candidates:
        cur = c
        for _ in range(4):
            if cur not in extended:
                extended.append(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent

    for d in extended:
        if os.path.isdir(os.path.join(d, 'data')):
            return d

    if extended:
        return extended[0]
    return os.path.dirname(os.path.abspath(sys.executable))


def get_base_path() -> str:
    """Get the base path for the application, works for both frozen and non-frozen."""
    if is_frozen():
        return _find_base_path_frozen()
    # In dev mode: MSK_core/Utils/env.py → go up 2 levels to project root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for Nuitka EXE."""
    return os.path.join(get_base_path(), relative_path)


def get_config_path() -> str:
    """Get the path to the main config file."""
    return get_resource_path("data/config.json")


def init_exe_environment() -> None:
    """Initialize environment for frozen executable.
    
    Sets up browserforge data path, working directory, and sys.path.
    Safe to call multiple times -- subsequent calls are no-ops.
    """
    if not is_frozen():
        return

    base_path = get_base_path()

    browserforge_data = os.path.join(base_path, 'browserforge_data')
    if os.path.exists(browserforge_data):
        os.environ['BROWSERFORGE_DATA_DIR'] = browserforge_data

    try:
        os.chdir(base_path)
    except OSError:
        pass

    if base_path not in sys.path:
        sys.path.insert(0, base_path)


def init_browserforge_path() -> Optional[str]:
    """Initialize browserforge data path and SSL certs for frozen executable."""
    if not is_frozen():
        return None
    
    base_path = get_base_path()
    browserforge_data = os.path.join(base_path, 'browserforge_data')
    if os.path.exists(browserforge_data):
        os.environ['BROWSERFORGE_DATA_DIR'] = browserforge_data

    try:
        import certifi
        ca_bundle = certifi.where()
        if ca_bundle and os.path.exists(ca_bundle):
            os.environ['SSL_CERT_FILE'] = ca_bundle
            os.environ['REQUESTS_CA_BUNDLE'] = ca_bundle
    except ImportError:
        pass

    return browserforge_data


def rehabilitate_environment_paths() -> None:
    """Detect and fix truncated environment paths caused by Nuitka onefile builds.

    Nuitka can mangle env vars like APPDATA and LOCALAPPDATA, truncating
    'AppData' to 'AppDat', 'AppDa', 'AppD', etc. This function detects ANY
    truncation and rebuilds the correct paths from USERPROFILE.
    """
    if sys.platform != "win32":
        return

    user_profile = os.environ.get("USERPROFILE", "")
    if not user_profile or not os.path.isdir(user_profile):
        exe_dir = os.path.dirname(sys.executable)
        parts = exe_dir.replace("/", "\\").split("\\")
        for i, part in enumerate(parts):
            if part.lower() == "users" and i + 1 < len(parts):
                user_profile = "\\".join(parts[:i+2])
                break
        if not user_profile or not os.path.isdir(user_profile):
            return

    real_appdata_root = os.path.join(user_profile, "AppData")

    if not os.path.isdir(real_appdata_root):
        return

    appdata = os.environ.get("APPDATA", "")
    real_roaming = os.path.join(real_appdata_root, "Roaming")
    if os.path.isdir(real_roaming):
        if not appdata or not os.path.isdir(appdata) or "appdata" not in appdata.lower():
            os.environ["APPDATA"] = real_roaming

    localappdata = os.environ.get("LOCALAPPDATA", "")
    real_local = os.path.join(real_appdata_root, "Local")
    if os.path.isdir(real_local):
        if not localappdata or not os.path.isdir(localappdata) or "appdata" not in localappdata.lower():
            os.environ["LOCALAPPDATA"] = real_local

    for var, default in [("PROGRAMFILES", "C:\\Program Files"), ("PROGRAMFILES(X86)", "C:\\Program Files (x86)")]:
        val = os.environ.get(var, "")
        if not val or not os.path.isdir(val):
            if os.path.isdir(default):
                os.environ[var] = default
