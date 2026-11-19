"""
GeoIP lookup for proxy fingerprinting.
Used by Brave + ZenDriver methods to set browser timezone/locale
to match the proxy's geographic location.
"""
from __future__ import annotations
import re
from typing import Optional, Dict, Tuple

_FALLBACK_TZ     = "America/New_York"
_FALLBACK_LOCALE = "en-US"

_COUNTRY_MAP: Dict[str, Tuple[str, str]] = {
    "US": ("America/New_York",     "en-US"),
    "GB": ("Europe/London",         "en-GB"),
    "CA": ("America/Toronto",       "en-CA"),
    "AU": ("Australia/Sydney",      "en-AU"),
    "DE": ("Europe/Berlin",         "de-DE"),
    "FR": ("Europe/Paris",          "fr-FR"),
    "NL": ("Europe/Amsterdam",      "nl-NL"),
    "SE": ("Europe/Stockholm",      "sv-SE"),
    "NO": ("Europe/Oslo",           "nb-NO"),
    "FI": ("Europe/Helsinki",       "fi-FI"),
    "DK": ("Europe/Copenhagen",     "da-DK"),
    "CH": ("Europe/Zurich",         "de-CH"),
    "AT": ("Europe/Vienna",         "de-AT"),
    "BE": ("Europe/Brussels",       "nl-BE"),
    "IT": ("Europe/Rome",           "it-IT"),
    "ES": ("Europe/Madrid",         "es-ES"),
    "PT": ("Europe/Lisbon",         "pt-PT"),
    "PL": ("Europe/Warsaw",         "pl-PL"),
    "CZ": ("Europe/Prague",         "cs-CZ"),
    "HU": ("Europe/Budapest",       "hu-HU"),
    "RO": ("Europe/Bucharest",      "ro-RO"),
    "BG": ("Europe/Sofia",          "bg-BG"),
    "GR": ("Europe/Athens",         "el-GR"),
    "RU": ("Europe/Moscow",         "ru-RU"),
    "UA": ("Europe/Kiev",           "uk-UA"),
    "TR": ("Europe/Istanbul",       "tr-TR"),
    "IN": ("Asia/Kolkata",          "en-IN"),
    "CN": ("Asia/Shanghai",         "zh-CN"),
    "JP": ("Asia/Tokyo",            "ja-JP"),
    "KR": ("Asia/Seoul",            "ko-KR"),
    "SG": ("Asia/Singapore",        "en-SG"),
    "HK": ("Asia/Hong_Kong",        "zh-HK"),
    "TW": ("Asia/Taipei",           "zh-TW"),
    "ID": ("Asia/Jakarta",          "id-ID"),
    "MY": ("Asia/Kuala_Lumpur",     "ms-MY"),
    "TH": ("Asia/Bangkok",          "th-TH"),
    "VN": ("Asia/Ho_Chi_Minh",      "vi-VN"),
    "PH": ("Asia/Manila",           "fil-PH"),
    "PK": ("Asia/Karachi",          "ur-PK"),
    "BD": ("Asia/Dhaka",            "bn-BD"),
    "BR": ("America/Sao_Paulo",     "pt-BR"),
    "AR": ("America/Argentina/Buenos_Aires", "es-AR"),
    "CL": ("America/Santiago",      "es-CL"),
    "CO": ("America/Bogota",        "es-CO"),
    "MX": ("America/Mexico_City",   "es-MX"),
    "PE": ("America/Lima",          "es-PE"),
    "VE": ("America/Caracas",       "es-VE"),
    "ZA": ("Africa/Johannesburg",   "en-ZA"),
    "NG": ("Africa/Lagos",          "en-NG"),
    "EG": ("Africa/Cairo",          "ar-EG"),
    "IL": ("Asia/Jerusalem",        "he-IL"),
    "SA": ("Asia/Riyadh",           "ar-SA"),
    "AE": ("Asia/Dubai",            "ar-AE"),
    "NZ": ("Pacific/Auckland",      "en-NZ"),
}


def _extract_host(proxy: Optional[Dict]) -> str:
    """Extract just the IP/hostname from a proxy dict."""
    if not proxy:
        return ""
    server = proxy.get("server", "")
    if "://" in server:
        server = server.split("://", 1)[1]
    host = server.split(":")[0].strip()
    return host


def _is_ip(host: str) -> bool:
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host))


def lookup_proxy_geo(proxy: Optional[Dict]) -> Tuple[str, str]:
    """
    Returns (timezone_id, locale) for a proxy dict.
    Falls back to ("America/New_York", "en-US") on any error.
    """
    host = _extract_host(proxy)
    if not host or not _is_ip(host):
        return _FALLBACK_TZ, _FALLBACK_LOCALE

    try:
        import requests as _req
        resp = _req.get(
            f"http://ip-api.com/json/{host}?fields=status,timezone,countryCode",
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                tz = data.get("timezone") or ""
                cc = data.get("countryCode") or ""
                if tz:
                    locale = _COUNTRY_MAP.get(cc, ("", _FALLBACK_LOCALE))[1]
                    return tz, locale
                if cc and cc in _COUNTRY_MAP:
                    return _COUNTRY_MAP[cc]
    except Exception:
        pass

    return _FALLBACK_TZ, _FALLBACK_LOCALE
