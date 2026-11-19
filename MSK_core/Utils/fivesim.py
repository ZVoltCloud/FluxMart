import os
import sys
import time
import requests
from typing import Optional, Dict, Tuple

from .utils import get_resource_path


class FiveSimAPI:
    BASE_URL = "https://5sim.net/v1"
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        })
    
    def validate_api_key(self) -> Tuple[bool, str, float]:
        if not self.api_key:
            return False, "No API key provided", 0.0
        
        try:
            response = self.session.get(f"{self.BASE_URL}/user/profile")
            if response.status_code == 200:
                data = response.json()
                balance = data.get("balance", 0)
                return True, "Valid", balance
            elif response.status_code == 401:
                return False, "Invalid API key", 0.0
            else:
                return False, f"API error: {response.status_code}", 0.0
        except Exception as e:
            return False, f"Connection error: {str(e)}", 0.0
    
    def get_balance(self) -> float:
        try:
            response = self.session.get(f"{self.BASE_URL}/user/profile")
            if response.status_code == 200:
                data = response.json()
                return float(data.get("balance", 0))
            return 0.0
        except Exception:
            return 0.0
    
    def get_available_numbers(self, country: str = "any", operator: str = "any") -> int:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/guest/prices",
                params={"country": country, "product": "discord"}
            )
            if response.status_code == 200:
                data = response.json()
                if country in data and "discord" in data[country]:
                    return data[country]["discord"].get("count", 0)
            return 0
        except Exception:
            return 0
    
    def buy_number(self, country: str = "any", operator: str = "any") -> Optional[Dict]:
        try:
            response = self.session.get(
                f"{self.BASE_URL}/user/buy/activation/{country}/{operator}/discord"
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "id": data.get("id"),
                    "phone": data.get("phone"),
                    "operator": data.get("operator"),
                    "country": data.get("country"),
                    "status": data.get("status"),
                    "price": data.get("price", 0)
                }
            return None
        except Exception:
            return None
    
    def get_sms(self, order_id: int, timeout: int = 120) -> Optional[str]:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = self.session.get(f"{self.BASE_URL}/user/check/{order_id}")
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "")
                    
                    if status == "RECEIVED":
                        sms_list = data.get("sms", [])
                        if sms_list:
                            return sms_list[-1].get("code", sms_list[-1].get("text", ""))
                    elif status == "CANCELED":
                        return None
                    elif status == "TIMEOUT":
                        return None
                    elif status == "BANNED":
                        return None
                
                time.sleep(3)
            except Exception:
                time.sleep(3)
        
        return None
    
    def finish_order(self, order_id: int) -> bool:
        try:
            response = self.session.get(f"{self.BASE_URL}/user/finish/{order_id}")
            return response.status_code == 200
        except Exception:
            return False
    
    def cancel_order(self, order_id: int) -> bool:
        try:
            response = self.session.get(f"{self.BASE_URL}/user/cancel/{order_id}")
            return response.status_code == 200
        except Exception:
            return False
    
    def ban_order(self, order_id: int) -> bool:
        try:
            response = self.session.get(f"{self.BASE_URL}/user/ban/{order_id}")
            return response.status_code == 200
        except Exception:
            return False

    def get_prices_for_discord(self) -> Dict:
        """Fetch prices for Discord across all countries.
        Returns {country_name: {operator: {cost, count, rate}}}
        API returns: {country: {product: {operator: {cost, count, rate}}}}
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/guest/prices")
            if response.status_code == 200:
                all_data = response.json()
                result = {}
                for country_name, products in all_data.items():
                    if not isinstance(products, dict):
                        continue
                    discord_ops = products.get("discord", {})
                    if discord_ops and isinstance(discord_ops, dict):
                        result[country_name] = discord_ops
                return result
            return {}
        except Exception:
            return {}

    def get_operators_for_country(self, country: str = "any") -> Dict:
        """Fetch operator details for Discord in a specific country.
        Uses the prices endpoint which has per-operator data.
        Returns {operator_name: {cost, count, rate}}
        """
        try:
            response = self.session.get(f"{self.BASE_URL}/guest/prices",
                                        params={"product": "discord", "country": country})
            if response.status_code == 200:
                data = response.json()
                country_data = data.get(country, {})
                if not country_data:
                    for k, v in data.items():
                        if isinstance(v, dict):
                            country_data = v
                            break
                if not isinstance(country_data, dict):
                    return {}
                discord_data = country_data.get("discord", None)
                if discord_data and isinstance(discord_data, dict):
                    return discord_data
                return country_data
            return {}
        except Exception:
            return {}


class PhoneVerifier:
    def __init__(self, api_key: str = "", number_limit: int = 10, country: str = "any", operator: str = "any"):
        self.api = FiveSimAPI(api_key)
        self.number_limit = number_limit
        self.country = country if country else "any"
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
                f.write(f"{timestamp} | {phone} | {email} | {token[:20]}...\n")
            self.used_numbers += 1
        except Exception:
            pass
    
    def can_use_number(self) -> bool:
        if self.number_limit <= 0:
            return True
        return self.used_numbers < self.number_limit
    
    def get_remaining_numbers(self) -> int:
        if self.number_limit <= 0:
            return -1
        return max(0, self.number_limit - self.used_numbers)
    
    def is_enabled(self) -> bool:
        return bool(self.api.api_key)
    
    def _extract_code(self, raw_code: str) -> Optional[str]:
        import re
        if raw_code and len(raw_code) == 6 and raw_code.isdigit():
            return raw_code
        match = re.search(r'\b(\d{6})\b', raw_code or "")
        if match:
            return match.group(1)
        match = re.search(r'(\d{4,8})', raw_code or "")
        if match:
            return match.group(1)
        return None

    def verify_phone(self, token: str, email: str = "", proxy: Optional[Dict] = None) -> Tuple[bool, str]:
        if not self.can_use_number():
            return False, "Number limit reached"

        if not self.api.api_key:
            return False, "5sim API key not configured"

        number_data = self.api.buy_number(country=self.country, operator=self.operator)
        if not number_data:
            return False, "Failed to get phone number"

        order_id = number_data["id"]
        phone = number_data["phone"]

        try:
            import tls_client
            session = tls_client.Session(client_identifier="chrome_120")

            if proxy:
                server_url = proxy.get('server', '').split('://')[-1]
                if 'username' in proxy and 'password' in proxy:
                    proxy_url = f"http://{proxy['username']}:{proxy['password']}@{server_url}"
                else:
                    proxy_url = f"http://{server_url}"
                session.proxies = {'http': proxy_url, 'https': proxy_url}

            headers = {
                "Authorization": token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "X-Discord-Locale": "en-US",
                "X-Discord-Timezone": "America/New_York",
                "X-Super-Properties": "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IChLSFRNTCwgbGlrZSBHZWNrbykgQ2hyb21lLzEyMC4wLjAuMCBTYWZhcmkvNTM3LjM2IiwiYnJvd3Nlcl92ZXJzaW9uIjoiMTIwLjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIn0="
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
                except:
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
                self._save_number(phone, email, token)
                return True, phone_formatted
            else:
                error_msg = "Unknown error"
                try:
                    err_data = verify_response.json()
                    error_msg = err_data.get("message", str(verify_response.status_code))
                except:
                    error_msg = str(verify_response.status_code)
                self.api.ban_order(order_id)
                return False, f"Verify failed: {error_msg}"

        except Exception as e:
            try:
                self.api.cancel_order(order_id)
            except:
                pass
            return False, f"Error: {str(e)}"
