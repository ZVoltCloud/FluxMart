"""
FluxMart — Bootstrapper Build Script
Compiles Bootstrapper.py into a standalone EXE using Nuitka.

Usage:
  python exe-2.py
  python exe-2.py --skip-clean
"""

import os, sys, shutil, subprocess, site, stat, time, importlib.util
from pathlib import Path

OUTPUT_NAME = "Bootstrapper"
ENTRY_POINT = "Bootstrapper.py"
DIST_DIR    = "dist"

def _banner(t, c="═", w=60):
    print(f"\n{c*w}\n   {t}\n{c*w}")

def _step(n, total, label): print(f"\n[{n}/{total}] {label} ...")
def _ok(m):   print(f"  [OK]   {m}")
def _info(m): print(f"  [>>]   {m}")
def _warn(m): print(f"  [!]    {m}")
def _fail(m): print(f"\n  [FAIL] {m}")

def module_exists(name):
    try: return importlib.util.find_spec(name.split(".")[0]) is not None
    except: return False

def find_package_dir(pkg):
    try:
        spec = importlib.util.find_spec(pkg)
        if spec:
            if spec.origin: return os.path.dirname(spec.origin)
            locs = list(spec.submodule_search_locations or [])
            if locs: return locs[0]
    except: pass
    return None

def check_nuitka():
    try:
        r = subprocess.run([sys.executable, "-m", "nuitka", "--version"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            _ok(f"Nuitka: {r.stdout.strip().splitlines()[0]}")
            return True
    except: pass
    _info("Installing Nuitka...")
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "nuitka>=4.0", "ordered-set", "zstandard", "-q"])
    return True

def _find_icon():
    for c in ["msklogo.ico", "msk-logo.ico", "static/img/icon.ico", "msk-logo.png"]:
        if os.path.exists(c): return c
    return None

def clean_build():
    for d in [f"{OUTPUT_NAME}.build", f"{OUTPUT_NAME}.dist",
              f"{OUTPUT_NAME}.onefile-build", "Bootstrapper.build",
              "Bootstrapper.dist", "Bootstrapper.onefile-build"]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            _info(f"Removed: {d}")

REQUIRED = [
    ("requests",      "requests"),
    ("webview",       "pywebview"),
    ("cryptography",  "cryptography"),
]

def ensure_packages():
    missing = [pip for imp, pip in REQUIRED if not module_exists(imp)]
    if not missing:
        _ok("All required packages present")
        return
    _info(f"Installing: {', '.join(missing)}")
    subprocess.run([sys.executable, "-m", "pip", "install"] + missing + ["-q"])

INCLUDE_PACKAGES = [
    "requests", "urllib3", "certifi", "charset_normalizer", "idna",
    "webview", "webview.platforms", "webview.platforms.edgechromium",
    "webview.platforms.winforms", "webview.platforms.cef",
    "cryptography", "cffi", "pycparser",
    "json", "hashlib", "zipfile", "shutil", "threading",
]

NOFOLLOW = [
    "tkinter", "unittest", "test", "distutils", "setuptools", "pip",
    "webview.platforms.android", "webview.platforms.cocoa",
    "webview.platforms.gtk", "webview.platforms.qt",
]

def build_exe():
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone", "--onefile", "--mingw64",
        f"--output-filename={OUTPUT_NAME}.exe",
        "--windows-console-mode=disable",
        "--follow-imports",
        "--assume-yes-for-downloads",
        "--enable-plugin=anti-bloat",
        "--remove-output",
        f"--onefile-tempdir-spec={{TEMP}}\\MSK_{OUTPUT_NAME}",
        "--windows-product-name=FluxMart Updater",
        "--windows-company-name=MSK",
        "--windows-file-description=FluxMart Auto-Updater",
        "--windows-product-version=1.0.0.0",
        "--windows-file-version=1.0.0.0",
    ]

    icon = _find_icon()
    if icon:
        cmd.append(f"--windows-icon-from-ico={icon}")
        _ok(f"Icon: {icon}")

    for nf in NOFOLLOW:
        cmd.append(f"--nofollow-import-to={nf}")

    for pkg in INCLUDE_PACKAGES:
        root = pkg.split(".")[0]
        if module_exists(root):
            cmd.append(f"--include-package={pkg}")

    for pkg in ["webview", "certifi", "cryptography"]:
        if module_exists(pkg):
            cmd.append(f"--include-package-data={pkg}")

    # Include the HTML template
    template = "bootstrapper_template.html"
    if os.path.isfile(template):
        cmd.append(f"--include-data-files={template}={template}")
        _ok(f"Template: {template}")

    cmd.append(ENTRY_POINT)

    print(f"\n  [>>]   Nuitka: {len(cmd)} arguments")
    print(  "  [>>]   This usually takes 3-8 minutes.\n")

    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, encoding="utf-8", errors="replace")
    for line in iter(proc.stdout.readline, ""):
        print(line, end="", flush=True)
    proc.wait()

    elapsed = time.time() - t0
    if proc.returncode != 0:
        _fail(f"Build failed (code {proc.returncode}) after {elapsed:.0f}s")
        return False
    _ok(f"Build complete in {elapsed:.0f}s")
    return True

def post_build():
    os.makedirs(DIST_DIR, exist_ok=True)
    exe = f"{OUTPUT_NAME}.exe"
    if os.path.isfile(exe):
        dst = os.path.join(DIST_DIR, exe)
        shutil.move(exe, dst)
        size = os.path.getsize(dst) / 1024**2
        _ok(f"EXE: {dst} ({size:.1f} MB)")
    else:
        _warn("No EXE found after build!")

TOTAL_STEPS = 5

def main():
    t0 = time.time()
    _banner("FluxMart — Bootstrapper Build Script")
    print(f"   Python : {sys.version.split()[0]}")
    print(f"   Output : {DIST_DIR}/{OUTPUT_NAME}.exe")

    skip_clean = "--skip-clean" in sys.argv

    _step(1, TOTAL_STEPS, "Checking Nuitka")
    if not check_nuitka(): return 1

    _step(2, TOTAL_STEPS, "Checking packages")
    ensure_packages()

    _step(3, TOTAL_STEPS, "Cleaning previous build")
    if not skip_clean: clean_build()

    _step(4, TOTAL_STEPS, "Building Bootstrapper EXE")
    if not build_exe(): return 1

    _step(5, TOTAL_STEPS, "Post-build")
    post_build()

    elapsed = time.time() - t0
    _banner(f"BUILD SUCCESSFUL — {elapsed:.0f}s")
    print(f"\n   EXE: {os.path.abspath(os.path.join(DIST_DIR, f'{OUTPUT_NAME}.exe'))}")
    print(f"\n   Place Bootstrapper.exe next to FluxMart.exe in dist/")
    print(f"   Also copy bootstrapper_template.html to the same folder.\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
