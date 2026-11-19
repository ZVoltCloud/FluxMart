"""
OnlineSim.io API client for FluxMart EXE.
Endpoints: GET /api/getNum.php, GET /api/getState.php, GET /api/getBalance.php, etc.
Service code for Discord: "discord"
"""

import os
import re
import time
import requests
from typing import Optional, Dict, Tuple, List

from .utils import get_resource_path


class OnlineSimAPI:
    """Wrapper for the OnlineSim.io REST API (v1.1)."""

    BASE_URL = "https://onlinesim.io/api"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key.strip() if api_key else ""
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # ─── helpers ──────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: dict = None, timeout: int = 15) -> dict:
        """Issue a GET request and return parsed JSON (or error dict)."""
        params = params or {}
        params["apikey"] = self.api_key
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params,
                timeout=timeout,
            )
            if resp.status_code != 200:
                return {"response": "error", "error": f"HTTP {resp.status_code}"}
            data = resp.json()
            if isinstance(data, dict) and data.get("response") in (
                "ERROR_WRONG_KEY",
                "ERROR_NO_KEY",
                "ACCOUNT_BLOCKED",
                "ERROR_NO_SERVICE",
                "API_ACCESS_DISABLED",
                "API_ACCESS_IP",
            ):
                return {"response": "error", "error": data.get("response", "Unknown")}
            return data
        except Exception as exc:
            return {"response": "error", "error": str(exc)[:120]}

    # ─── balance ──────────────────────────────────────────────────────────

    def get_balance(self) -> float:
        """Return current user balance as float."""
        if not self.api_key:
            return 0.0
        data = self._get("getBalance.php")
        if isinstance(data, dict):
            if data.get("response") == "error":
                return -1.0
            bal = data.get("balance")
            if bal is not None:
                try:
                    return float(bal)
                except (ValueError, TypeError):
                    pass
            zbalance = data.get("zbalance")
            if zbalance is not None:
                try:
                    return float(zbalance)
                except (ValueError, TypeError):
                    pass
        return 0.0

    def validate_api_key(self) -> Tuple[bool, str, float]:
        """Check if the API key is valid. Returns (ok, message, balance)."""
        if not self.api_key:
            return False, "No API key provided", 0.0
        balance = self.get_balance()
        if balance < 0:
            return False, "Invalid API key", 0.0
        return True, "Valid", balance

    # ─── buy number ───────────────────────────────────────────────────────

    def buy_number(self, country: str = "7", operator: str = "any", **kwargs) -> Optional[Dict]:
        """
        Buy a virtual number for Discord.
        country: E.164 country code without '+' (e.g. "7" for Russia, "44" for UK).
        Returns dict with keys: id (tzid), phone, country  --  or None on failure.
        """
        params: Dict = {
            "service": "discord",
            "number": "true",
        }
        if country and country not in ("any", "0", ""):
            params["country"] = country

        data = self._get("getNum.php", params, timeout=20)
        if not isinstance(data, dict):
            return None

        if data.get("response") == 1 or data.get("response") == "1":
            tzid = data.get("tzid")
            phone = data.get("number", "")
            if tzid:
                return {
                    "id": str(tzid),
                    "phone": phone,
                    "country": country,
                }
        return None

    # ─── get SMS ──────────────────────────────────────────────────────────

    def get_sms(self, tzid: str, timeout: int = 120) -> Optional[str]:
        """
        Poll getState until an SMS code arrives or timeout.
        Returns the code string, or None.
        """
        start = time.time()
        while time.time() - start < timeout:
            data = self._get("getState.php", {
                "tzid": tzid,
                "message_to_code": "1",
                "msg_list": "0",
                "clean": "1",
            })

            # getState returns a list of operations
            ops = data if isinstance(data, list) else [data]
            for op in ops:
                if not isinstance(op, dict):
                    continue
                if str(op.get("tzid")) != str(tzid):
                    continue

                response = op.get("response", "")

                # "TZ_NUM_ANSWER" means SMS received
                if response == "TZ_NUM_ANSWER":
                    msg = op.get("msg", "")
                    if msg:
                        return str(msg)

                # Still waiting
                if response in ("TZ_NUM_WAIT", "TZ_NUM_PREPARE", 1, "1"):
                    break

                # Errors / closed
                if response in ("TZ_OVER_EMPTY", "TZ_OVER_NR", "ERROR"):
                    return None

            time.sleep(4)

        return None

    # ─── finish / cancel ──────────────────────────────────────────────────

    def finish_order(self, tzid: str) -> bool:
        """Mark operation as completed (setOperationOk)."""
        data = self._get("setOperationOk.php", {"tzid": tzid}, timeout=10)
        if isinstance(data, dict):
            return data.get("response") == "1" or data.get("response") == 1
        return False

    def cancel_order(self, tzid: str) -> bool:
        """Cancel an operation and attempt to get a refund."""
        # OnlineSim does not have a dedicated cancel endpoint -- 
        # calling setOperationOk with flag or just letting it expire works.
        # We use setOperationRevise to request next SMS or let it timeout.
        # Actually, the "close" is handled by not calling setOperationOk -- 
        # the number expires after 15 min automatically.
        # For safety we call setOperationOk anyway to release it fast.
        return self.finish_order(tzid)

    # ─── tariffs (for country listing) ────────────────────────────────────

    def get_tariffs(self, country: str = "") -> Dict:
        """Get tariffs for Discord. Returns raw data dict."""
        params = {"service": "discord"}
        if country and country not in ("any", ""):
            params["country"] = country
        return self._get("getTariffs.php", params)


class OnlineSimVerifier:
    """High-level phone verification flow using OnlineSim."""

    def __init__(self, api_key: str = "", number_limit: int = 10, country: str = "7", operator: str = "any"):
        self.api = OnlineSimAPI(api_key)
        self.number_limit = number_limit
        self.country = country if country and country != "any" else "7"
        self.operator = operator if operator else "any"
        self.used_numbers = 0
        self._load_used_count()

    def _load_used_count(self):
        try:
            numbers_file = get_resource_path("data/input/Numbers.txt")
            if os.path.exists(numbers_file):
                with open(numbers_file, "r", encoding="utf-8") as f:
                    self.used_numbers = len([line for line in f if line.strip()])
        except Exception:
            self.used_numbers = 0

    def _save_number(self, phone: str, email: str = "", token: str = ""):
        try:
            numbers_file = get_resource_path("data/input/Numbers.txt")
            os.makedirs(os.path.dirname(numbers_file), exist_ok=True)
            with open(numbers_file, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp} | [OnlineSim] {phone} | {email} | {token[:20]}...\n")
            self.used_numbers += 1
        except Exception:
            pass

    def can_use_number(self) -> bool:
        if self.number_limit <= 0:
            return True
        return self.used_numbers < self.number_limit

    def is_enabled(self) -> bool:
        return bool(self.api.api_key)

    def _extract_code(self, raw_code: str) -> Optional[str]:
        if not raw_code:
            return None
        raw_code = str(raw_code)
        if raw_code.isdigit() and len(raw_code) == 6:
            return raw_code
        match = re.search(r'\b(\d{6})\b', raw_code)
        if match:
            return match.group(1)
        match = re.search(r'(\d{4,8})', raw_code)
        if match:
            return match.group(1)
        return None

    def verify_phone(self, token: str, email: str = "", proxy: Optional[Dict] = None) -> Tuple[bool, str]:
        """Verify a Discord token's phone via API-only (no browser)."""
        if not self.can_use_number():
            return False, "Number limit reached"

        if not self.api.api_key:
            return False, "OnlineSim API key not configured"

        number_data = self.api.buy_number(country=self.country)
        if not number_data:
            return False, "Failed to get phone number from OnlineSim"

        order_id = str(number_data["id"])
        phone = str(number_data["phone"])

        try:
            import tls_client
            session = tls_client.Session(client_identifier="chrome_131")

            if proxy:
                server_url = proxy.get('server', '').replace('http://', '').replace('https://', '')
                if 'username' in proxy and 'password' in proxy:
                    proxy_url = f"http://{proxy['username']}:{proxy['password']}@{server_url}"
                else:
                    proxy_url = f"http://{server_url}"
                session.proxies = {'http': proxy_url, 'https': proxy_url}

            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "X-Discord-Locale": "en-US",
                "X-Discord-Timezone": "America/New_York",
            }

            phone_formatted = phone if phone.startswith("+") else f"+{phone}"

            response = session.post(
                "https://discord.com/api/v9/users/@me/phone",
                headers=headers,
                json={"phone": phone_formatted}
            )

            if response.status_code not in [200, 204]:
                error_msg = "Unknown error"
                try:
                    err_data = response.json()
                    error_msg = err_data.get("message", str(response.status_code))
                except Exception:
                    error_msg = str(response.status_code)
                self.api.cancel_order(order_id)
                return False, f"Discord rejected phone: {error_msg}"

            code = self.api.get_sms(order_id, timeout=120)
            if not code:
                self.api.cancel_order(order_id)
                return False, "SMS timeout - no code received"

            verification_code = self._extract_code(code)
            if not verification_code:
                self.api.cancel_order(order_id)
                return False, f"Could not extract code from: {code[:20]}"

            verify_response = session.post(
                "https://discord.com/api/v9/users/@me/phone/verify",
                headers=headers,
                json={"phone": phone_formatted, "code": verification_code}
            )

            if verify_response.status_code in [200, 204]:
                self.api.finish_order(order_id)
                self._save_number(phone_formatted, email, token)
                return True, phone_formatted
            else:
                error_msg = "Unknown error"
                try:
                    err_data = verify_response.json()
                    error_msg = err_data.get("message", str(verify_response.status_code))
                except Exception:
                    error_msg = str(verify_response.status_code)
                self.api.cancel_order(order_id)
                return False, f"Verify failed: {error_msg}"

        except Exception as e:
            try:
                self.api.cancel_order(order_id)
            except Exception:
                pass
            return False, f"OnlineSim Error: {str(e)}"
