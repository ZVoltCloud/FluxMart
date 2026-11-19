"""
Dynamic Discord build number fetcher.
Scrapes the real build number from Discord's live page to avoid
using stale/hardcoded values that trigger detection.
"""

import re
import time
import threading
from typing import Optional

_lock = threading.Lock()
_cached_build: Optional[int] = None
_cached_at: float = 0.0
_CACHE_TTL = 3600


_FALLBACK_BUILD = 523061


def fetch_build_number(timeout: int = 8) -> int:
    """Fetch the latest Discord client build number from the live page.

    Returns the build number as int.  On any failure returns the
    most-recently cached value or the baked-in fallback.
    """
    global _cached_build, _cached_at

    with _lock:
        if _cached_build and (time.time() - _cached_at < _CACHE_TTL):
            return _cached_build

    try:
        from curl_cffi import requests as cffi_req

        with cffi_req.Session(impersonate="chrome131") as s:
            r = s.get(
                "https://discord.com/app",
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                    "user-agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
                timeout=timeout,
            )

            m = re.search(r'"BUILD_NUMBER"\s*:\s*"(\d+)"', r.text)
            if m:
                bn = int(m.group(1))
                with _lock:
                    _cached_build = bn
                    _cached_at = time.time()
                return bn

    except Exception:
        pass

    with _lock:
        if _cached_build:
            return _cached_build

    return _FALLBACK_BUILD


def get_build_number() -> int:
    """Non-blocking getter – returns cached value instantly or fallback."""
    with _lock:
        if _cached_build:
            return _cached_build
    return _FALLBACK_BUILD


def _bg_warm():
    try:
        fetch_build_number()
    except Exception:
        pass

threading.Thread(target=_bg_warm, daemon=True).start()
