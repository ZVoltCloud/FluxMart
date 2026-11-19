import os
import re
import base64
import random
import threading
import datetime

from .utils import get_base_path

_CUSTOM_FPS: list = []
_FPS_LOADED: bool = False
_FPS_LOCK = threading.Lock()


def _reset_pool():
    global _CUSTOM_FPS, _FPS_LOADED
    _CUSTOM_FPS = []
    _FPS_LOADED = False


def load_custom_fingerprints(config: dict):
    global _CUSTOM_FPS, _FPS_LOADED
    with _FPS_LOCK:
        if _FPS_LOADED:
            return
        _FPS_LOADED = True
        settings = config.get("fingerprint_settings", {})
        if not settings.get("use_custom_fingerprint", False):
            return
        raw_path = settings.get("load_folder", "data/input/fingerprints.txt")
        path = raw_path if os.path.isabs(raw_path) else os.path.join(get_base_path(), raw_path)
        if not os.path.exists(path):
            return
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            _CUSTOM_FPS.extend(lines)
        elif os.path.isdir(path):
            for fname in os.listdir(path):
                if fname.endswith(".txt"):
                    fpath = os.path.join(path, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        lines = [ln.strip() for ln in f if ln.strip()]
                    _CUSTOM_FPS.extend(lines)


def pop_custom_fingerprint(config: dict):
    load_custom_fingerprints(config)
    settings = config.get("fingerprint_settings", {})
    if not settings.get("use_custom_fingerprint", False):
        return None
    with _FPS_LOCK:
        if not _CUSTOM_FPS:
            return None
        fp = random.choice(_CUSTOM_FPS)
        if settings.get("remove_after_use", True):
            _CUSTOM_FPS.remove(fp)
            raw_path = settings.get("load_folder", "data/input/fingerprints.txt")
            path = raw_path if os.path.isabs(raw_path) else os.path.join(get_base_path(), raw_path)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    with open(path, "w", encoding="utf-8") as f:
                        for line in lines:
                            if line.strip() != fp.strip():
                                f.write(line)
                except Exception:
                    pass
        return fp


def extract_snowflake_from_fingerprint(fingerprint: str):
    if not fingerprint:
        return None
    try:
        match = re.search(r'(\d{17,20})', fingerprint)
        if match:
            return match.group(1)
        padding = "=" * (4 - len(fingerprint) % 4)
        decoded = base64.b64decode(fingerprint + padding).decode("utf-8", errors="ignore")
        match = re.search(r'(\d{17,20})', decoded)
        if match:
            return match.group(1)
        if fingerprint.isdigit():
            return fingerprint
    except Exception:
        pass
    return None


def snowflake_to_age(snowflake: str) -> str:
    if not snowflake:
        return "Unknown"
    try:
        sf = int(snowflake)
        timestamp_ms = (sf >> 22) + 1420070400000
        creation_date = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0)
        now = datetime.datetime.now()
        diff = now - creation_date
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        secs = diff.seconds % 60
        return f"{days}d {hours}h {minutes}m {secs}s"
    except Exception:
        return "Unknown"
