"""
Hero SMS API Client & Phone Verifier
Uses the SMS-Activate compatible API protocol (hero-sms.com)
Service code for Discord: 'ds'
"""
import time
import re
import os
import threading

try:
    import tls_client
except ImportError:
    tls_client = None

try:
    import requests as _requests_fallback
except ImportError:
    _requests_fallback = None


BASE_URL = "https://hero-sms.com/stubs/handler_api.php"


class HeroSmsAPI:
    """Low-level wrapper around hero-sms.com SMS-Activate compatible API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._session = None
        self._init_session()

    def _init_session(self):
        if tls_client is not None:
            try:
                self._session = tls_client.Session(
                    client_identifier="chrome_120",
                    random_tls_extension_order=True,
                )
                return
            except Exception:
                pass
        if _requests_fallback is not None:
            self._session = _requests_fallback.Session()

    def _request(self, params: dict, timeout: int = 15) -> str:
        """Make an API request and return the raw text response."""
        params["api_key"] = self.api_key
        try:
            if tls_client and isinstance(self._session, tls_client.Session):
                resp = self._session.get(BASE_URL, params=params, timeout_seconds=timeout)
            elif self._session is not None:
                resp = self._session.get(BASE_URL, params=params, timeout=timeout)
            else:
                return ""
            return resp.text.strip()
        except Exception:
            return ""

    def get_balance(self) -> float:
        """Get account balance. Returns -1.0 on error."""
        try:
            result = self._request({"action": "getBalance"})
            # Response: ACCESS_BALANCE:123.45
            if result.startswith("ACCESS_BALANCE:"):
                return float(result.split(":")[1])
            return -1.0
        except Exception:
            return -1.0

    def buy_number(self, service: str = "ds", country: int = 62,
                   max_price: float = 0.0, fixed_price: bool = True) -> dict:
        """
        Buy a phone number for the given service and country.
        Returns {"id": activation_id, "phone": phone_number} or None.
        """
        try:
            params = {
                "action": "getNumber",
                "service": service,
                "country": str(country),
            }
            if max_price > 0:
                params["maxPrice"] = str(max_price)
            if fixed_price:
                params["fixedPrice"] = "true"

            result = self._request(params)
            # Response: ACCESS_NUMBER:ID:PHONE
            if result.startswith("ACCESS_NUMBER:"):
                parts = result.split(":")
                if len(parts) >= 3:
                    return {
                        "id": parts[1],
                        "phone": parts[2],
                    }
            return None
        except Exception:
            return None

    def get_sms(self, activation_id: str, timeout: int = 120) -> str:
        """
        Poll for the SMS code. Returns the code string or None on timeout.
        Status responses:
          STATUS_WAIT_CODE  - not yet received
          STATUS_OK:code    - received
          STATUS_CANCEL     - cancelled
        """
        try:
            # First, set status to "ready" (status=1)
            self.set_status(activation_id, status=1)

            start = time.time()
            while time.time() - start < timeout:
                result = self._request({
                    "action": "getStatus",
                    "id": str(activation_id),
                })
                if result.startswith("STATUS_OK:"):
                    code = result.split(":", 1)[1]
                    return code
                if result in ("STATUS_CANCEL",):
                    return None
                time.sleep(3)
            return None
        except Exception:
            return None

    def set_status(self, activation_id: str, status: int = 1) -> str:
        """
        Set activation status.
        1 = ready to receive SMS
        3 = request another SMS
        6 = complete activation
        8 = cancel activation
        """
        try:
            return self._request({
                "action": "setStatus",
                "id": str(activation_id),
                "status": str(status),
            })
        except Exception:
            return ""

    def finish_order(self, activation_id: str) -> str:
        """Mark activation as complete (status=6)."""
        return self.set_status(activation_id, status=6)

    def cancel_order(self, activation_id: str) -> str:
        """Cancel activation (status=8)."""
        return self.set_status(activation_id, status=8)


class HeroSmsVerifier:
    """High-level phone verifier using Hero SMS, matching the PhoneVerifier pattern."""

    def __init__(self, api_key: str, number_limit: int = 50,
                 country: int = 62, service: str = "ds",
                 max_price: float = 0.0, fixed_price: bool = True,
                 operator: str = "any"):
        self.api = HeroSmsAPI(api_key)
        self.number_limit = number_limit
        self.country = country
        self.service = service
        self.max_price = max_price
        self.fixed_price = fixed_price
        self._numbers_used = 0
        self._lock = threading.Lock()
        self._used_numbers_file = self._get_used_numbers_path()

    @staticmethod
    def _get_used_numbers_path() -> str:
        try:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return os.path.join(base, "data", "output", "hero_sms_used.txt")
        except Exception:
            return "hero_sms_used.txt"

    def is_enabled(self) -> bool:
        return bool(self.api.api_key)

    def can_use_number(self) -> bool:
        if self.number_limit <= 0:
            return True
        return self._numbers_used < self.number_limit

    def _save_number(self, phone: str, email: str = "", token: str = ""):
        """Persist used number to file."""
        try:
            os.makedirs(os.path.dirname(self._used_numbers_file), exist_ok=True)
            with open(self._used_numbers_file, "a", encoding="utf-8") as f:
                f.write(f"{phone}|{email}|{token[:20] if token else ''}\n")
        except Exception:
            pass

    def verify_phone(self, token: str, email: str = "") -> tuple:
        """
        Perform API-based phone verification for a Discord token.
        Returns (success: bool, message: str).
        """
        with self._lock:
            if not self.can_use_number():
                return False, "Number limit reached"

        # 1. Buy a number
        number_data = self.api.buy_number(
            service=self.service,
            country=self.country,
            max_price=self.max_price,
            fixed_price=self.fixed_price,
        )
        if not number_data:
            return False, "Failed to get phone number from Hero SMS"

        activation_id = number_data["id"]
        phone = number_data["phone"]
        phone_formatted = phone if phone.startswith("+") else f"+{phone}"

        try:
            # 2. Send the phone number to Discord via API
            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIn0=",
            }

            session = None
            if tls_client:
                try:
                    session = tls_client.Session(
                        client_identifier="chrome_120",
                        random_tls_extension_order=True,
                    )
                except Exception:
                    pass
            if session is None and _requests_fallback:
                session = _requests_fallback.Session()

            if session is None:
                self.api.cancel_order(activation_id)
                return False, "No HTTP client available"

            # Send phone to Discord
            import json as _json
            payload = _json.dumps({"phone": phone_formatted})

            if tls_client and isinstance(session, tls_client.Session):
                resp = session.post(
                    "https://discord.com/api/v9/users/@me/phone",
                    headers=headers,
                    data=payload,
                    timeout_seconds=15,
                )
                status_code = resp.status_code
            else:
                resp = session.post(
                    "https://discord.com/api/v9/users/@me/phone",
                    headers=headers,
                    data=payload,
                    timeout=15,
                )
                status_code = resp.status_code

            if status_code not in (200, 201, 204):
                self.api.cancel_order(activation_id)
                try:
                    err = resp.json() if hasattr(resp, 'json') else {}
                    err_msg = err.get("message", f"HTTP {status_code}")
                except Exception:
                    err_msg = f"HTTP {status_code}"
                return False, f"Discord rejected phone: {err_msg}"

            # 3. Wait for SMS code
            code = self.api.get_sms(activation_id, timeout=120)
            if not code:
                self.api.cancel_order(activation_id)
                return False, "SMS timeout - no code received"

            # Extract 6-digit code
            verification_code = code
            if not (code.isdigit() and len(code) == 6):
                match = re.search(r'\b(\d{6})\b', code)
                if match:
                    verification_code = match.group(1)
                else:
                    self.api.cancel_order(activation_id)
                    return False, f"Could not extract code from: {code[:30]}"

            # 4. Submit verification code to Discord
            verify_payload = _json.dumps({
                "phone": phone_formatted,
                "code": verification_code,
            })

            if tls_client and isinstance(session, tls_client.Session):
                resp2 = session.post(
                    "https://discord.com/api/v9/phone-verifications/verify",
                    headers=headers,
                    data=verify_payload,
                    timeout_seconds=15,
                )
                status2 = resp2.status_code
            else:
                resp2 = session.post(
                    "https://discord.com/api/v9/phone-verifications/verify",
                    headers=headers,
                    data=verify_payload,
                    timeout=15,
                )
                status2 = resp2.status_code

            if status2 in (200, 201, 204):
                self.api.finish_order(activation_id)
                with self._lock:
                    self._numbers_used += 1
                self._save_number(phone_formatted, email, token)
                return True, phone_formatted
            else:
                self.api.cancel_order(activation_id)
                try:
                    err = resp2.json() if hasattr(resp2, 'json') else {}
                    err_msg = err.get("message", f"HTTP {status2}")
                except Exception:
                    err_msg = f"HTTP {status2}"
                return False, f"Discord verify failed: {err_msg}"

        except Exception as e:
            try:
                self.api.cancel_order(activation_id)
            except Exception:
                pass
            return False, f"Error: {str(e)[:80]}"
