"""
FluxMart — Setup & Dependency Installer
Run this script (as Administrator) before launching main.py.
It installs every dependency, verifies native DLLs, installs browser
binaries, and tells you exactly what is wrong and why tokens would be
flagged on this PC.
"""

import os
import sys
import ctypes
import subprocess
import urllib.request
import winreg

# ── Make sure rich is available before we use it ─────────────────────────────
def _bootstrap_rich():
    try:
        import rich  # noqa: F401
    except ImportError:
        print("[setup] Installing 'rich' for display...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "rich", "--quiet",
             "--disable-pip-version-check"],
            check=False,
        )

_bootstrap_rich()

from rich.console import Console
from rich.text import Text
from rich.rule import Rule
from rich.panel import Panel
from rich.padding import Padding

console = Console()

# ─────────────────────────────────────────────────────────────────────────────

VCREDIST_URL  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
VCREDIST_TEMP = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "vc_redist.x64.exe")

GRADIENT = [
    "#3A1E77", "#432388", "#4B2999", "#5330A9",
    "#5B36B8", "#623DC6", "#6943D3", "#714AE0",
    "#7950ED", "#8257FA",
]

BANNER_LINES = [
    " ███▄ ▄███▓  ██████  ██ ▄█▀   ▄▄▄█████▓ ▒█████   ██ ▄█▀▓█████  ███▄    █       ▄████ ",
    "▓██▒▀█▀ ██▒▒██    ▒  ██▄█▒    ▓  ██▒ ▓▒▒██▒  ██▒ ██▄█▒ ▓█   ▀  ██ ▀█   █      ██▒ ▀█▒",
    "▓██    ▓██░░ ▓██▄   ▓███▄░    ▒ ▓██░ ▒░▒██░  ██▒▓███▄░ ▒███   ▓██  ▀█ ██▒    ▒██░▄▄▄░",
    "▒██    ▒██   ▒   ██▒▓██ █▄    ░ ▓██▓ ░ ▒██   ██░▓██ █▄ ▒▓█  ▄ ▓██▒  ▐▌██▒    ░▓█  ██▓",
    "▒██▒   ░██▒▒██████▒▒▒██▒ █▄     ▒██▒ ░ ░ ████▓▒░▒██▒ █▄░▒████▒▒██░   ▓██░    ░▒▓███▀▒",
    "░ ▒░   ░  ░▒ ▒▓▒ ▒ ░▒ ▒▒ ▓▒     ▒ ░░   ░ ▒░▒░▒░ ▒ ▒▒ ▓▒░░ ▒░ ░░ ▒░   ▒ ▒      ░▒   ▒ ",
    "░  ░      ░░ ░▒  ░ ░░ ░▒ ▒░       ░      ░ ▒ ▒░ ░ ░▒ ▒░ ░ ░  ░░ ░░   ░ ▒░      ░   ░ ",
    "░      ░   ░  ░  ░  ░ ░░ ░      ░      ░ ░ ░ ▒  ░ ░░ ░    ░      ░   ░ ░     ░ ░   ░ ",
    "       ░         ░  ░  ░                   ░ ░  ░  ░      ░  ░         ░           ░ ",
    "                                                                                     ",
]

SPACING = "                    "


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tag(label: str, color: str, msg: str, detail: str = ""):
    t = Text()
    t.append("[", style="#c0c0c0")
    t.append(label, style=color)
    t.append("] ", style="#c0c0c0")
    t.append(msg, style="white")
    if detail:
        t.append(f"  {detail}", style="dim")
    console.print(t)


def ok(msg, detail=""):    _tag("  OK  ", "#13A10E", msg, detail)
def fail(msg, detail=""):  _tag(" FAIL ", "#FF4444", msg, detail)
def warn(msg, detail=""):  _tag(" WARN ", "#FFD700", msg, detail)
def info(msg, detail=""):  _tag(" INFO ", "#7950ED", msg, detail)
def step(n, total, msg):
    t = Text()
    t.append(f"[{n}/{total}] ", style="#8257FA bold")
    t.append(msg, style="white bold")
    console.print()
    console.print(t)


def display_banner():
    console.print()
    console.print()
    for i, line in enumerate(BANNER_LINES):
        console.print(SPACING + line, style=GRADIENT[i % len(GRADIENT)])
    console.print()
    console.print(Rule(title="[dim]Setup & Dependency Installer[/dim]", style="#5330A9"))
    console.print()


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd: list, timeout=180) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


# ── Step 0: VC++ Redistributable ─────────────────────────────────────────────

def _check_vcredist() -> bool:
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64"),
    ]
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as k:
                val, _ = winreg.QueryValueEx(k, "Installed")
                if val == 1:
                    return True
        except Exception:
            pass
    sys32 = os.environ.get("SystemRoot", "C:\\Windows") + "\\System32"
    for dll in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll"):
        if os.path.isfile(os.path.join(sys32, dll)):
            return True
    return False


def _install_vcredist() -> bool:
    info("Downloading Visual C++ Redistributable x64...")
    try:
        urllib.request.urlretrieve(VCREDIST_URL, VCREDIST_TEMP)
    except Exception as e:
        fail("Download failed.", str(e))
        return False
    info("Installing silently (this may take ~30 seconds)...")
    try:
        r = subprocess.run(
            [VCREDIST_TEMP, "/install", "/quiet", "/norestart"],
            timeout=180, capture_output=True,
        )
        return r.returncode in (0, 3010)
    except Exception as e:
        fail("Installer error.", str(e))
        return False


def check_vcredist() -> bool:
    """Returns True if VC++ is present (possibly after auto-install)."""
    if _check_vcredist():
        ok("Microsoft Visual C++ Redistributable x64 is installed.")
        return True

    fail(
        "Visual C++ Redistributable x64 NOT found.",
        "— THIS is why tokens appear Invalid/Locked on this PC!",
    )
    console.print()
    console.print(
        Padding(
            "[bold #FFD700]WHY TOKENS GET FLAGGED[/bold #FFD700]\n"
            "[dim]tls_client and greenlet are native C extensions.\n"
            "Without vcruntime140.dll / msvcp140.dll they fail to load.\n"
            "When the DLL load crashes silently, every token check returns\n"
            "'Invalid' or 'Locked' even if the token is perfectly valid.[/dim]",
            (0, 4),
        )
    )
    console.print()

    if is_admin():
        info("Auto-installing VC++ Redistributable...")
        if _install_vcredist():
            ok("Visual C++ Redistributable installed!  A reboot may be required.")
            return True
        else:
            fail(
                "Auto-install failed.",
                f"Download manually: {VCREDIST_URL}",
            )
            return False
    else:
        warn(
            "Run setup as Administrator to auto-install,",
            f"or download manually: {VCREDIST_URL}",
        )
        return False


# ── Step 1: pip upgrade ───────────────────────────────────────────────────────

def upgrade_pip():
    info("Upgrading pip / setuptools / wheel...")
    _run([sys.executable, "-m", "pip", "install", "--upgrade",
          "pip", "setuptools", "wheel", "--quiet",
          "--disable-pip-version-check"])
    ok("pip upgraded.")


# ── Step 2: requirements.txt ──────────────────────────────────────────────────

def install_requirements():
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if not os.path.isfile(req):
        warn("requirements.txt not found — skipping package install.")
        return

    info("Installing packages from requirements.txt...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req,
         "--quiet", "--disable-pip-version-check"],
        capture_output=True, timeout=600,
    )
    if r.returncode == 0:
        ok("All packages installed from requirements.txt.")
    else:
        warn(
            "Some packages may have failed.",
            "Check output above for details.",
        )
        if r.stderr:
            for line in r.stderr.decode(errors="replace").splitlines()[-10:]:
                console.print(f"    [dim]{line}[/dim]")


# ── Step 3: Verify critical native modules ────────────────────────────────────

CRITICAL_CHECKS = [
    (
        "greenlet",
        "import greenlet; greenlet.greenlet(lambda: None).switch()",
        "greenlet",
        "Browser concurrency will not work — tokens may fail silently.",
    ),
    (
        "tls_client",
        "import tls_client; tls_client.Session(client_identifier='chrome_120')",
        "tls_client",
        "Token validation (valid/locked/invalid) will be BROKEN — all tokens return Invalid.",
    ),
    (
        "curl_cffi",
        "import curl_cffi",
        "curl_cffi",
        "HTTP-level token checks may degrade.",
    ),
    (
        "playwright",
        "import playwright",
        "playwright",
        "Chromium-based registration method will not work.",
    ),
    (
        "camoufox",
        "import camoufox",
        "camoufox",
        "Camoufox registration method will not work.",
    ),
]


def verify_native_modules() -> bool:
    all_ok = True
    for name, code, pkg, impact in CRITICAL_CHECKS:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, timeout=20,
        )
        if r.returncode == 0:
            ok(f"{name} native module loaded.")
        else:
            fail(f"{name} failed to load!")
            console.print(f"    [#FF4444 dim]Impact : {impact}[/#FF4444 dim]")
            console.print(f"    [dim]Fix    : Install VC++ Redistributable x64 first, then run[/dim]")
            console.print(f"    [dim]         pip install {pkg}  (or re-run setup)[/dim]")
            all_ok = False
    return all_ok


# ── Step 4: Browser binaries ──────────────────────────────────────────────────

def install_browsers():
    info("Installing Playwright Chromium binary...")
    r1 = subprocess.run(
        ["playwright", "install", "chromium"],
        capture_output=True, timeout=600,
    )
    if r1.returncode == 0:
        ok("Playwright Chromium installed.")
    else:
        # Try python -m playwright
        r1b = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, timeout=600,
        )
        if r1b.returncode == 0:
            ok("Playwright Chromium installed.")
        else:
            warn("Playwright Chromium install may have failed — check manually.")

    info("Installing Camoufox browser binary...")
    r2 = subprocess.run(
        [sys.executable, "-m", "camoufox", "fetch"],
        capture_output=True, timeout=600,
    )
    if r2.returncode == 0:
        ok("Camoufox binary installed.")
    else:
        warn("Camoufox fetch may have failed — run:  python -m camoufox fetch")


# ── Step 5: Final diagnosis ───────────────────────────────────────────────────

def final_summary(vc_ok: bool, mods_ok: bool):
    console.print()
    console.print(Rule(style="#5330A9"))
    console.print()

    if vc_ok and mods_ok:
        t = Text()
        t.append("[", style="#c0c0c0")
        t.append("Msk", style="dim")
        t.append("] ", style="#c0c0c0")
        t.append("Setup complete!", style="#13A10E bold")
        t.append("  All dependencies verified.", style="dim")
        console.print(t)
        console.print()
        console.print("[dim]You can now run  [bold]start.bat[/bold]  or  [bold]python main.py[/bold][/dim]")
    else:
        t = Text()
        t.append("[", style="#c0c0c0")
        t.append("Msk", style="dim")
        t.append("] ", style="#c0c0c0")
        t.append("Setup finished with issues!", style="#FF4444 bold")
        console.print(t)
        console.print()
        if not vc_ok:
            console.print(
                Padding(
                    "[bold #FF4444]ACTION REQUIRED:[/bold #FF4444]\n"
                    "[white]Install [bold]Microsoft Visual C++ Redistributable x64[/bold]\n"
                    f"Download: [link]{VCREDIST_URL}[/link][/white]\n"
                    "[dim]After installing VC++, re-run setup to verify.[/dim]",
                    (0, 4),
                )
            )
        if not mods_ok:
            console.print(
                Padding(
                    "[bold #FFD700]Native module check failed.[/bold #FFD700]\n"
                    "[dim]Fix VC++ first, then run setup again.[/dim]",
                    (0, 4),
                )
            )

    console.print()


# ── Entry point ───────────────────────────────────────────────────────────────

TOTAL_STEPS = 5

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()

    os.system("cls")
    display_banner()

    if not is_admin():
        warn(
            "Not running as Administrator.",
            "VC++ auto-install may fail — right-click start-s.bat → Run as administrator.",
        )
        console.print()

    # Step 0 — VC++ Redistributable
    step(0, TOTAL_STEPS, "Visual C++ Redistributable x64")
    vc_ok = check_vcredist()

    # Step 1 — pip
    step(1, TOTAL_STEPS, "Upgrading pip")
    upgrade_pip()

    # Step 2 — requirements.txt
    step(2, TOTAL_STEPS, "Python packages")
    install_requirements()

    # Step 3 — native module verification
    step(3, TOTAL_STEPS, "Verifying critical native modules")
    mods_ok = verify_native_modules()

    # Step 4 — browser binaries
    step(4, TOTAL_STEPS, "Browser binaries")
    install_browsers()

    # Step 5 — summary
    step(5, TOTAL_STEPS, "Summary")
    final_summary(vc_ok, mods_ok)

    console.print("[dim]Press Enter to exit...[/dim]", end="")
    input()
