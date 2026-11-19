"""
FluxMart — prepare_dist.py
Scaffolds a clean, ready-to-distribute dist/ folder.

Run this AFTER exe.py has compiled the EXE.
It creates clean config files (no personal API keys / cached data),
all required empty .txt files, and copies every .bat helper next to the EXE.

Usage:
  python prepare_dist.py
"""

import os
import sys
import json
import shutil
from pathlib import Path

DIST = "dist"


CLEAN_CONFIG = {
    "language": "en",
    "threads": 1,
    "captcha_timeout": 30,
    "headless": False,
    "auto_solver_captcha": True,
    "mullvad": False,
    "vpn_providers": {
        "mullvad": {"enabled": False}
    },
    "email_verification_delay": "0s",
    "email_providers": {
        "cybertemp": {
            "enabled": True,
            "api_key": "",
            "domain": "",
            "cached_domains": [],
            "last_refresh": ""
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
            "account_type": "hotmail"
        }
    },
    "fivesim": {
        "enabled": False,
        "api_key": "",
        "number_limit": 50,
        "country": "canada",
        "operator": "virtual12",
        "verify_without_must": True,
        "cached_countries": []
    },
    "onlinesim": {
        "enabled": False,
        "api_key": "",
        "number_limit": 50,
        "country": "7",
        "verify_without_must": False
    },
    "hero_sms": {
        "enabled": False,
        "api_key": "",
        "number_limit": 50,
        "country": 62,
        "service": "ds",
        "max_price": 0.01,
        "fixed_price": True
    },
    "ai_api": {
        "openrouter": {
            "api_key": "",
            "model": "nvidia/nemotron-3-super-120b-a12b:free"
        },
        "groq": {
            "api_key": "",
            "model": "llama-3.3-70b-versatile"
        }
    },
    "solver_ai": {
        "groq": False,
        "openrouter": False
    },
    "proxies": {"enabled": False},
    "rate_limit_checker": {"enabled": False},
    "token_verify": True,
    "humanizer": {
        "enabled": True,
        "avatar": True,
        "pronouns": True,
        "bio": True,
        "hypesquad": True,
        "display_name": True
    },
    "logs": {
        "censor_token": True,
        "generation_time": True,
        "startup_time": True,
        "hcaptcha_waiting": True,
        "hcaptcha_solving": True,
        "humanize_time": True,
        "verify_time": True,
        "total_time": True
    },
    "token_count": 1,
    "browser_method": "brave",
    "hcaptcha_accessibility_cookie": "",
    "browser_language": "en-US",
    "chrome_path": "",
    "skip_token_extract": False,
    "restock_wait": False,
    "data_saver_enabled": False,
    "update_browser_save": False,
    "fast_mails": {"enabled": False, "buffer_size": 3},
    "multi_buy": {
        "enabled": False,
        "providers": ["zeus", "hotmail007"]
    },
    "webhook": {
        "enabled": False,
        "url": "",
        "notify_all": True
    },
    "cybertemp_api_key": "",
    "ai_image_solver": {
        "enabled": False,
        "model": "gemma4:31b-cloud",
        "api_key": ""
    },
    "nopecha": {
        "enabled": False,
        "api_key": "",
        "use_extension": False
    },
    "save_fingerprint": False,
    "fingerprint_settings": {
        "use_custom_fingerprint": False,
        "load_folder": "data/input/fingerprints.txt",
        "remove_after_use": True
    },
    "email_verification_timeout": 0
}

CLEAN_AUTOLOGIN = {
    "auto_login_enabled": False
}

CLEAN_TRANSLATIONS = {}


DATA_SUBDIRS = [
    "input",
    "input/profiles",
    "input/profiles/avatars",
    "output",
    "temp",
]

INPUT_TXTS = [
    "proxies.txt",
    "cybertemp_domains.txt",
    "Numbers.txt",
    "fingerprints.txt",
]

OUTPUT_TXTS = [
    "tokens.txt",
    "invalid.txt",
    "locked.txt",
    "checked_valid.txt",
    "checked_invalid.txt",
    "linkverify.txt",
    "tokenSplited.txt",
    "humanized.txt",
]

PROFILE_TXTS = [
    "bio.txt",
    "names.txt",
    "pronouns.txt",
]

INSTALLER_DIR = "Installer-check me"
BAT_FILES = [
    (os.path.join(INSTALLER_DIR, "installer.bat"),  "installer.bat"),
    ("start.bat",                                    "start.bat"),
    (os.path.join(INSTALLER_DIR, "check_deps.bat"), "check_deps.bat"),
    (os.path.join(INSTALLER_DIR, "check_deps.py"),  "check_deps.py"),
    ("locked-problem.bat",                           "locked-problem.bat"),
]

STATIC_DIRS = [
    ("templates", "templates"),
    ("static",    "static"),
]


def ok(msg):  print(f"  [OK]   {msg}")
def info(msg): print(f"  [>>]   {msg}")
def warn(msg): print(f"  [!]    {msg}")
def skip(msg): print(f"  [--]   {msg}")


def write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    ok(f"Written: {path}")


def touch(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).touch()


def main():
    print()
    print("=" * 65)
    print("  FluxMart — prepare_dist.py  (clean distribution packager)")
    print("=" * 65)

    print("\n[1/6] Checking dist/ folder ...")
    if not os.path.isdir(DIST):
        warn("dist/ folder not found — creating it.")
        warn("Run exe.py first to compile the EXE, then run this script.")
        os.makedirs(DIST, exist_ok=True)
    else:
        exe_path = os.path.join(DIST, "FluxMart.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 ** 2
            ok(f"EXE found: FluxMart.exe  ({size_mb:.1f} MB)")
        else:
            warn("FluxMart.exe not found in dist/ — run exe.py first!")

    print("\n[2/6] Creating data/ directory structure ...")
    data_root = os.path.join(DIST, "data")
    for sub in DATA_SUBDIRS:
        d = os.path.join(data_root, sub)
        os.makedirs(d, exist_ok=True)
    ok(f"Directories ready under {data_root}/")

    print("\n[3/6] Writing clean config files ...")
    write_json(os.path.join(data_root, "config.json"),      CLEAN_CONFIG)
    write_json(os.path.join(data_root, "autologin.json"),   CLEAN_AUTOLOGIN)
    write_json(os.path.join(data_root, "translations.json"),CLEAN_TRANSLATIONS)

    print("\n[4/6] Creating empty .txt files ...")
    for fname in INPUT_TXTS:
        p = os.path.join(data_root, "input", fname)
        touch(p)
        ok(f"input/{fname}")

    for fname in OUTPUT_TXTS:
        p = os.path.join(data_root, "output", fname)
        touch(p)
        ok(f"output/{fname}")

    for fname in PROFILE_TXTS:
        p = os.path.join(data_root, "input", "profiles", fname)
        touch(p)
        ok(f"input/profiles/{fname}")

    print("\n[5/6] Copying static assets ...")
    for src, dest in STATIC_DIRS:
        dst = os.path.join(DIST, dest)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            ok(f"{src}/ -> dist/{dest}/")
        else:
            skip(f"{src}/ not found — skipping")

    print("\n[6/6] Copying helper scripts ...")
    copied = 0
    for src, dst_name in BAT_FILES:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DIST, dst_name))
            ok(f"{dst_name}")
            copied += 1
        else:
            skip(f"{src} not found — skipping")
    if copied == 0:
        warn("No helper scripts found.")

    print()
    print("=" * 65)
    print("  DONE — dist/ is ready to distribute")
    print("=" * 65)
    print()
    print("  dist/ structure:")
    print("    FluxMart.exe          <- compiled application")
    print("    data/config.json         <- CLEAN defaults (edit API keys here)")
    print("    data/autologin.json      <- auto-login disabled")
    print("    data/translations.json   <- empty (auto-filled on first run)")
    print("    data/input/proxies.txt   <- add your proxies here")
    print("    data/input/Numbers.txt   <- phone numbers (if using)")
    print("    data/output/tokens.txt   <- generated tokens land here")
    print("    data/output/invalid.txt  <- invalid token log")
    print("    data/output/locked.txt   <- locked token log")
    print("    installer.bat            <- run on target PC to install deps")
    print("    check_deps.bat           <- auto-run by installer")
    print("    check_deps.py            <- dependency check script")
    print("    locked-problem.bat       <- run if stuck loading/locked out")
    print("    start.bat                <- shortcut to launch the EXE (alternative to dbl-click)")
    print()
    print("  BEFORE DISTRIBUTING:")
    print("    1. config.json — fill in your cybertemp / fivesim / AI API keys")
    print("    2. data/input/proxies.txt — add proxies (one per line)")
    print("    3. data/input/profiles/ — add bio.txt, names.txt, pronouns.txt")
    print()
    print("  TARGET PC REQUIREMENTS:")
    print("    • Windows 10/11 x64")
    print("    • Brave Browser (https://brave.com/download) OR Google Chrome")
    print("    • Microsoft Visual C++ Redistributable x64 2015-2022")
    print("      https://aka.ms/vs/17/release/vc_redist.x64.exe")
    print()


if __name__ == "__main__":
    main()
