"""
MSK Phone Fingerprint Manager
Loads the generated phone_devices.json database and provides
a thread-safe pool to pop unique fingerprints per registration session.

Usage:
    from MSK_core.Utils.phone_fingerprint import PhoneFingerprint
    fp = PhoneFingerprint.get()   # returns a full profile dict, or None
"""

import os
import json
import random
import threading
import hashlib
from typing import Optional, Dict, Any, List

from .env import get_base_path

_DB_LOCK = threading.Lock()
_DB_PROFILES: List[dict] = []
_DB_LOADED: bool = False
_DB_INDEX: int = 0  # rotating cursor so we never repeat until full cycle


def _db_path() -> str:
    return os.path.join(get_base_path(), "MSK_core", "Assets", "phone_devices.json")


def _load_db() -> None:
    global _DB_PROFILES, _DB_LOADED
    if _DB_LOADED:
        return
    path = _db_path()
    if not os.path.exists(path):
        _DB_LOADED = True
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            _DB_PROFILES = json.load(f)
        random.shuffle(_DB_PROFILES)   # shuffle once at load so order is random
        _DB_LOADED = True
    except Exception:
        _DB_LOADED = True


def _ensure_loaded() -> None:
    with _DB_LOCK:
        _load_db()


class PhoneFingerprint:
    """
    Thread-safe phone fingerprint pool.
    Each call to .get() returns a different profile in round-robin order.
    When the pool is exhausted it wraps around.
    """

    @staticmethod
    def available() -> bool:
        """Return True if the phone_devices.json database exists and has entries."""
        _ensure_loaded()
        return len(_DB_PROFILES) > 0

    @staticmethod
    def count() -> int:
        _ensure_loaded()
        return len(_DB_PROFILES)

    @staticmethod
    def get(seed: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Return one phone fingerprint profile.
        - If seed is provided → deterministic pick (same seed = same profile).
        - If seed is None → round-robin from pool.
        Returns None if database is empty / not generated yet.
        """
        _ensure_loaded()
        if not _DB_PROFILES:
            return None

        global _DB_INDEX
        if seed:
            # Deterministic: hash seed → index
            idx = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(_DB_PROFILES)
            return _DB_PROFILES[idx]
        else:
            with _DB_LOCK:
                profile = _DB_PROFILES[_DB_INDEX % len(_DB_PROFILES)]
                _DB_INDEX += 1
            return profile

    @staticmethod
    def get_for_worker(worker_id: int) -> Optional[Dict[str, Any]]:
        """Return a consistent fingerprint for a given worker ID."""
        return PhoneFingerprint.get(seed=f"worker_{worker_id}")

    @staticmethod
    def reload() -> None:
        """Force-reload the database from disk."""
        global _DB_PROFILES, _DB_LOADED, _DB_INDEX
        with _DB_LOCK:
            _DB_PROFILES = []
            _DB_LOADED = False
            _DB_INDEX = 0
        _ensure_loaded()


def build_mobile_stealth_js(profile: dict) -> str:
    """
    Generate the JS injection string for a mobile fingerprint profile.
    This overrides all detectable browser properties to match
    the target Android device consistently.
    """
    if not profile:
        return ""

    b = profile.get("browser", {})
    d = profile.get("display", {})
    dev = profile.get("device", {})
    net = profile.get("network", {})
    bat = profile.get("battery", {})

    ua = b.get("user_agent", "")
    platform = b.get("platform", "Linux armv8l")
    lang = b.get("language", "en-US")
    languages = json.dumps(b.get("languages", [lang]))
    hw_concurrency = b.get("hardware_concurrency", 8)
    device_memory = b.get("device_memory", 4)
    max_touch = b.get("max_touch_points", 10)
    sw = d.get("width_px", 1080)
    sh = d.get("height_px", 2400)
    avail_h = d.get("avail_height", sh - 60)
    color_depth = d.get("color_depth", 24)
    dpi = d.get("dpi", 420)
    connection = net.get("connection_type", "4g")
    downlink = net.get("downlink", 10.0)
    rtt = net.get("rtt", 50)
    bat_level = bat.get("level", 0.75)
    bat_charging = "true" if bat.get("charging", False) else "false"
    mobile = "true" if b.get("mobile", True) else "false"

    ch_ua = b.get("sec_ch_ua", f'"Chromium";v="120", "Google Chrome";v="120"')
    ch_ua_mobile = b.get("sec_ch_ua_mobile", "?1")
    ch_ua_platform = b.get("sec_ch_ua_platform", '"Android"')

    # Escape for JS string embedding
    ua_js = ua.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")
    platform_js = platform.replace("\\", "\\\\").replace('"', '\\"')
    ch_ua_js = ch_ua.replace("\\", "\\\\").replace('"', '\\"')

    js = f"""
(function() {{
'use strict';

// ── 1. Remove webdriver flag ──
try {{
    Object.defineProperty(Navigator.prototype, 'webdriver', {{ get: () => undefined, configurable: true }});
}} catch(e) {{}}

// ── 2. Clean CDP automation leaks ──
try {{
    ['cdc_adoQpoasnfa76pfcZLmcfl_Array','cdc_adoQpoasnfa76pfcZLmcfl_Promise',
     'cdc_adoQpoasnfa76pfcZLmcfl_Symbol','__playwright_target__','__pwInitScripts',
     '__puppeteer_evaluation_script__','domAutomation','domAutomationController'].forEach(function(k) {{
        try {{ delete window[k]; }} catch(_) {{}}
    }});
}} catch(e) {{}}

// ── 3. User Agent ──
try {{
    Object.defineProperty(navigator, 'userAgent', {{ get: () => '{ua_js}', configurable: true }});
    Object.defineProperty(navigator, 'appVersion', {{ get: () => '{ua_js}'.replace('Mozilla/', ''), configurable: true }});
}} catch(e) {{}}

// ── 4. Platform ──
try {{
    Object.defineProperty(navigator, 'platform', {{ get: () => '{platform_js}', configurable: true }});
}} catch(e) {{}}

// ── 5. Language ──
try {{
    Object.defineProperty(navigator, 'language', {{ get: () => '{lang}', configurable: true }});
    Object.defineProperty(navigator, 'languages', {{ get: () => {languages}, configurable: true }});
}} catch(e) {{}}

// ── 6. Hardware ──
try {{
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_concurrency}, configurable: true }});
}} catch(e) {{}}
try {{
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {device_memory}, configurable: true }});
}} catch(e) {{}}

// ── 7. Touch (mobile critical) ──
try {{
    Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {max_touch}, configurable: true }});
}} catch(e) {{}}

// ── 8. Mobile flag via userAgentData ──
try {{
    if (navigator.userAgentData) {{
        Object.defineProperty(navigator.userAgentData, 'mobile', {{ get: () => {mobile}, configurable: true }});
        Object.defineProperty(navigator.userAgentData, 'platform', {{ get: () => 'Android', configurable: true }});
    }}
}} catch(e) {{}}

// ── 9. Screen -- match device resolution ──
try {{
    Object.defineProperty(screen, 'width', {{ get: () => {sw}, configurable: true }});
    Object.defineProperty(screen, 'height', {{ get: () => {sh}, configurable: true }});
    Object.defineProperty(screen, 'availWidth', {{ get: () => {sw}, configurable: true }});
    Object.defineProperty(screen, 'availHeight', {{ get: () => {avail_h}, configurable: true }});
    Object.defineProperty(screen, 'colorDepth', {{ get: () => {color_depth}, configurable: true }});
    Object.defineProperty(screen, 'pixelDepth', {{ get: () => {color_depth}, configurable: true }});
    Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {round(dpi/160.0, 1)}, configurable: true }});
    Object.defineProperty(window, 'outerWidth', {{ get: () => {sw}, configurable: true }});
    Object.defineProperty(window, 'outerHeight', {{ get: () => {sh}, configurable: true }});
    Object.defineProperty(window, 'innerWidth', {{ get: () => {sw}, configurable: true }});
    Object.defineProperty(window, 'innerHeight', {{ get: () => {avail_h - 56}, configurable: true }});
}} catch(e) {{}}

// ── 10. window.chrome (absent on mobile but Discord checks it) ──
try {{
    if (!window.chrome) {{
        window.chrome = {{
            app: {{ isInstalled: false }},
            runtime: {{ id: undefined, connect: function(){{return {{}};}}, sendMessage: function(){{}} }},
            csi: function(){{}},
            loadTimes: function(){{ return {{}}; }},
        }};
    }}
}} catch(e) {{}}

// ── 11. Permissions ──
try {{
    var _origPQ = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(p) {{
        if (p && p.name === 'notifications') {{
            return Promise.resolve({{ state: (Notification && Notification.permission) || 'default', onchange: null }});
        }}
        return _origPQ(p);
    }};
}} catch(e) {{}}

// ── 12. Network Information API (mobile-realistic) ──
try {{
    var _conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (_conn) {{
        try {{ Object.defineProperty(_conn, 'effectiveType', {{ get: () => '{connection}', configurable: true }}); }} catch(_) {{}}
        try {{ Object.defineProperty(_conn, 'type', {{ get: () => '{connection}', configurable: true }}); }} catch(_) {{}}
        try {{ Object.defineProperty(_conn, 'downlink', {{ get: () => {downlink}, configurable: true }}); }} catch(_) {{}}
        try {{ Object.defineProperty(_conn, 'rtt', {{ get: () => {rtt}, configurable: true }}); }} catch(_) {{}}
        try {{ Object.defineProperty(_conn, 'saveData', {{ get: () => false, configurable: true }}); }} catch(_) {{}}
    }}
}} catch(e) {{}}

// ── 13. Battery API ──
try {{
    if (navigator.getBattery) {{
        navigator.getBattery = function() {{
            return Promise.resolve({{
                level: {bat_level},
                charging: {bat_charging},
                chargingTime: {bat_charging == 'true' and 1200 or 'Infinity'},
                dischargingTime: {int((1 - bat_level) * 14400) if bat_charging == 'false' else 'Infinity'},
                addEventListener: function(){{}},
                removeEventListener: function(){{}}
            }});
        }};
    }}
}} catch(e) {{}}

// ── 14. Orientation (portrait mobile) ──
try {{
    if (window.screen && screen.orientation) {{
        try {{ Object.defineProperty(screen.orientation, 'type', {{ get: () => 'portrait-primary', configurable: true }}); }} catch(_) {{}}
        try {{ Object.defineProperty(screen.orientation, 'angle', {{ get: () => 0, configurable: true }}); }} catch(_) {{}}
    }}
}} catch(e) {{}}

// ── 15. Hide MSK globals ──
try {{
    setTimeout(function() {{
        ['__msk_seed','__hcap_bridge','__hcapListenerActive','__msk_phone_fp'].forEach(function(k) {{
            try {{
                if (k in window) Object.defineProperty(window, k, {{ enumerable: false, configurable: true }});
            }} catch(_) {{}}
        }});
    }}, 500);
}} catch(e) {{}}

}})();
"""
    return js


def validate_profile(profile: dict) -> bool:
    """
    Quick sanity-check that a profile is internally consistent.
    Returns True if all required fields are present and coherent.
    """
    if not profile:
        return False
    try:
        b = profile["browser"]
        d = profile["display"]
        dev = profile["device"]
        assert len(b.get("user_agent", "")) > 50
        assert len(b.get("chrome_version", "")) >= 5
        assert d.get("width_px", 0) >= 320
        assert d.get("height_px", 0) >= 480
        assert d.get("dpi", 0) >= 100
        assert dev.get("cpu_cores", 0) >= 2
        android_ver = int(profile["system"]["android_version"])
        assert 9 <= android_ver <= 15
        return True
    except Exception:
        return False
