"""Hotmail007 email provider implementation (Updated for NEW OpenAPI 2026-11-15)."""
import re
import time
from typing import Optional, Callable, Dict, List

import requests

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError, EmailStockExhausted


class Hotmail007Provider(IEmailProvider):
    """Hotmail007 (hotmail007.com) email provider - NEW OpenAPI.

    API Documentation: https://hotmail007.com/api-docs
    Base URL: https://gapi.hotmail007.com
    
    NEW API (2026+):
    - Uses /open/stock to fetch available products
    - Uses /open/buy with productId (not mailType)
    - Response format: {"code": 0, "success": true, "data": {...}}
    
    Legacy API (still supported):
    - /api/mail/getMail with mailType
    """

    BASE_URL = "https://gapi.hotmail007.com"

    # Maps config mailType key → legacy API mailType string for backward compatibility
    LEGACY_MAIL_TYPES: Dict[str, str] = {
        "hotmail": "hotmail",
        "outlook": "outlook",
        "hotmail_premium": "hotmail Premium",
        "outlook_premium": "outlook Premium",
        "hotmail_trusted_graph": "hotmail Trusted Graph",
        "outlook_trusted_graph": "outlook Trusted Graph",
        "hotmail_imap": "hotmail IMAP",
        "outlook_imap": "outlook IMAP",
        "hotmail_longterm": "hotmail Long-term",
        "outlook_longterm": "outlook Long-term",
        # Legacy aliases
        "hotmail_trusted": "hotmail Trusted Graph",
        "outlook_trusted": "outlook Trusted Graph",
    }

    def __init__(self, api_key: str = "", mail_type: str = "hotmail", product_id: int = None) -> None:
        self.api_key = api_key
        # Store original mail_type for logging
        self.mail_type_original = mail_type
        # Store productId if provided directly
        self.product_id = product_id
        # Normalize for lookup
        normalized = mail_type.lower().replace(" ", "_").replace("-", "_")
        self.mail_type_legacy = self.LEGACY_MAIL_TYPES.get(normalized, mail_type)
        self.mail_type_config = normalized
        self.session = requests.Session()
        self._cached_products: List[Dict] = []
        self._cache_time = 0

    @property
    def name(self) -> str:
        return "Hotmail007"

    def check_balance(self) -> Optional[float]:
        """Check account balance using NEW OpenAPI endpoint."""
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/open/balance",
                params={"clientKey": self.api_key},
                timeout=15
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    return 0.0
                
                # NEW API format
                if data.get("code") == 0 and data.get("success") is True:
                    balance = data.get("data", {}).get("balance", 0)
                    return float(balance) if balance is not None else 0.0
                return 0.0
            elif resp.status_code in (401, 403):
                return None
            else:
                return 0.0
        except Exception:
            pass
        return None

    def _fetch_products(self, force_refresh: bool = False) -> List[Dict]:
        """Fetch available products from /open/stock endpoint.
        
        Returns list of products:
        [{"productId": 1, "name": "...", "mailType": "hotmail", "stock": 100, "price": 0.002}, ...]
        """
        # Use cached products if fresh (< 5 minutes old)
        if not force_refresh and self._cached_products and (time.time() - self._cache_time) < 300:
            return self._cached_products

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/open/stock",
                params={"clientKey": self.api_key},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 and data.get("success") is True:
                    products = data.get("data", [])
                    if isinstance(products, list):
                        self._cached_products = products
                        self._cache_time = time.time()
                        return products
        except Exception:
            pass
        
        return []

    def _find_product_id(self, mail_type: str) -> Optional[int]:
        """Find productId for the configured mail_type by querying /open/stock.
        
        Matches against mailType field in the product list.
        """
        products = self._fetch_products()
        
        if not products:
            return None
        
        # Normalize the search term - try multiple variations
        search_original = mail_type.strip()
        search_lower = mail_type.lower().strip()
        search_normalized = search_lower.replace("_", " ").replace("-", " ")
        
        # Debug: Log what we're searching for
        print(f"[DEBUG] Searching for mail_type: '{self.mail_type_original}' -> normalized: '{search_normalized}'")
        print(f"[DEBUG] Available products: {len(products)}")
        
        for product in products:
            product_mail_type = product.get("mailType", "").strip()
            product_name = product.get("name", "").strip()
            product_id = product.get("productId")
            
            # Debug: Log each product
            print(f"[DEBUG] Product: ID={product_id}, mailType='{product_mail_type}', name='{product_name}'")
            
            # Try multiple matching strategies
            # 1. Exact match (case-insensitive)
            if product_mail_type.lower() == search_lower:
                print(f"[DEBUG] Match found (exact): {product_id}")
                return product_id
            
            # 2. Normalized match (underscores/spaces)
            if product_mail_type.lower().replace(" ", "_").replace("-", "_") == search_normalized.replace(" ", "_"):
                print(f"[DEBUG] Match found (normalized): {product_id}")
                return product_id
            
            # 3. Contains match
            if search_normalized in product_mail_type.lower() or product_mail_type.lower() in search_normalized:
                print(f"[DEBUG] Match found (contains): {product_id}")
                return product_id
            
            # 4. Name match
            if search_normalized in product_name.lower() or product_name.lower() in search_normalized:
                print(f"[DEBUG] Match found (name): {product_id}")
                return product_id
        
        print(f"[DEBUG] No match found for '{search_normalized}'")
        return None

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Helper.mail import _save_account_data_to_file

        # Log what mail type we received
        Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007: Attempting to purchase '{self.mail_type_original}'"
        Logger.queue_log(worker_id=worker_id)

        # Use productId if provided directly, otherwise try to find it
        product_id = self.product_id
        
        if product_id is None:
            product_id = self._find_product_id(self.mail_type_legacy)
        
        if product_id is not None:
            Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007: Using NEW API with productId={product_id}"
            Logger.queue_log(worker_id=worker_id)
            try:
                return self._create_account_new_api(product_id, worker_id)
            except (EmailCreationError, EmailStockExhausted):
                raise
            except Exception as e:
                # Fall back to legacy API if NEW API fails
                Logger.STATUS = f"{MskColor.WARNING}Hotmail007 NEW API failed: {str(e)[:100]}, trying legacy API..."
                Logger.queue_log(worker_id=worker_id)
        else:
            Logger.STATUS = f"{MskColor.WARNING}Hotmail007: No productId, trying legacy API..."
            Logger.queue_log(worker_id=worker_id)

        # Fallback to LEGACY API
        try:
            return self._create_account_legacy_api(worker_id)
        except (EmailCreationError, EmailStockExhausted):
            raise
        except requests.exceptions.RequestException as e:
            raise EmailCreationError(f"Hotmail007 connection error: {str(e)[:60]}")

    def _create_account_new_api(self, product_id: int, worker_id: int = 0) -> Optional[EmailAccount]:
        """Purchase account using NEW OpenAPI /open/buy endpoint."""
        from ..Helper.mail import _save_account_data_to_file

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/open/buy",
                params={
                    "clientKey": self.api_key,
                    "productId": product_id,
                    "quantity": 1
                },
                timeout=30
            )

            if resp.status_code != 200:
                raise EmailCreationError(f"Hotmail007 NEW API HTTP {resp.status_code}: {resp.text[:80]}")

            data = resp.json()

            # NEW API response format: {"code": 0, "success": true, "data": {"accounts": [...], ...}}
            if data.get("code") == 0 and data.get("success") is True:
                purchase_data = data.get("data", {})
                accounts = purchase_data.get("accounts", [])
                
                if isinstance(accounts, list) and len(accounts) > 0:
                    account_str = accounts[0]
                    parts = account_str.split(":")
                    if len(parts) >= 4:
                        result = {
                            "email": parts[0].strip(),
                            "password": parts[1].strip(),
                            "refresh_token": parts[2].strip(),
                            "client_id": parts[3].strip()
                        }
                    elif len(parts) >= 2:
                        result = {
                            "email": parts[0].strip(),
                            "password": parts[1].strip()
                        }
                    else:
                        raise EmailCreationError(f"Hotmail007: unexpected account format: {account_str[:60]}")
                    
                    _save_account_data_to_file(result, "hotmail007")
                    Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007 account purchased: {result['email']}"
                    Logger.queue_log(worker_id=worker_id)
                    return EmailAccount(
                        email=result["email"],
                        password=result["password"],
                        refresh_token=result.get("refresh_token", ""),
                        client_id=result.get("client_id", ""),
                        provider_name=self.name,
                    )
                raise EmailStockExhausted("Hotmail007: empty accounts list returned (out of stock?)")
            else:
                error_code = data.get("code", "unknown")
                error_msg = data.get("message", "") or f"error code {error_code}"
                
                if "stock" in error_msg.lower() or "out of" in error_msg.lower():
                    raise EmailStockExhausted(f"Hotmail007: {error_msg}")
                raise EmailCreationError(f"Hotmail007: {error_msg}")

        except (EmailCreationError, EmailStockExhausted):
            raise
        except requests.exceptions.RequestException as e:
            raise EmailCreationError(f"Hotmail007 NEW API connection error: {str(e)[:60]}")

    def _create_account_legacy_api(self, worker_id: int = 0) -> Optional[EmailAccount]:
        """Purchase account using LEGACY API /api/mail/getMail endpoint."""
        from ..Helper.mail import _save_account_data_to_file

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/mail/getMail",
                params={
                    "clientKey": self.api_key,
                    "mailType": self.mail_type_legacy,
                    "quantity": 1
                },
                timeout=30
            )

            if resp.status_code != 200:
                raise EmailCreationError(f"Hotmail007 LEGACY API HTTP {resp.status_code}: {resp.text[:80]}")

            data = resp.json()

            # LEGACY API response format: {"success": true, "data": [...]}
            if isinstance(data, dict) and data.get("success") and data.get("data"):
                accounts = data["data"]
                if isinstance(accounts, list) and len(accounts) > 0:
                    account_str = accounts[0]
                    parts = account_str.split(":")
                    if len(parts) >= 4:
                        result = {
                            "email": parts[0].strip(),
                            "password": parts[1].strip(),
                            "refresh_token": parts[2].strip(),
                            "client_id": parts[3].strip()
                        }
                    elif len(parts) >= 2:
                        result = {
                            "email": parts[0].strip(),
                            "password": parts[1].strip()
                        }
                    else:
                        raise EmailCreationError(f"Hotmail007: unexpected account format: {account_str[:60]}")
                    _save_account_data_to_file(result, "hotmail007")
                    Logger.STATUS = f"{MskColor.PRIMARY}Hotmail007 account purchased (legacy): {result['email']}"
                    Logger.queue_log(worker_id=worker_id)
                    return EmailAccount(
                        email=result["email"],
                        password=result["password"],
                        refresh_token=result.get("refresh_token", ""),
                        client_id=result.get("client_id", ""),
                        provider_name=self.name,
                    )
                raise EmailStockExhausted("Hotmail007: empty accounts list returned (out of stock?)")
            else:
                error_msg = ""
                if isinstance(data, dict):
                    error_msg = data.get("message") or data.get("msg") or f"code {data.get('code')}"
                else:
                    error_msg = f"Unexpected response: {str(data)[:60]}"

                if "buy error" in error_msg.lower() or "stock" in error_msg.lower():
                    raise EmailStockExhausted(f"Hotmail007: {error_msg}")
                raise EmailCreationError(f"Hotmail007: {error_msg}")

        except (EmailCreationError, EmailStockExhausted):
            raise
        except requests.exceptions.RequestException as e:
            raise EmailCreationError(f"Hotmail007 LEGACY API connection error: {str(e)[:60]}")

    @staticmethod
    def _get_graph_access_token(refresh_token: str, client_id: str) -> Optional[str]:
        if not refresh_token or not client_id:
            return None
        if refresh_token.endswith("$"):
            refresh_token = refresh_token[:-1]
        default_client_id = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
        cid = client_id if client_id else default_client_id
        try:
            resp = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": cid,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": "https://graph.microsoft.com/.default",
                },
                timeout=30,
                verify=False
            )
            if resp.status_code == 200:
                token = resp.json().get("access_token")
                if token:
                    return token
        except Exception:
            pass
        try:
            resp = requests.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data={
                    "client_id": cid,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": "https://graph.microsoft.com/Mail.Read offline_access",
                },
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json().get("access_token")
        except Exception:
            pass
        return None

    def _get_verification_via_graph(self, refresh_token: str, client_id: str,
                                     timeout: int = 120, poll_interval: int = 3,
                                     stop_signal: Optional[Callable[[], bool]] = None) -> Optional[str]:
        from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic

        access_token = self._get_graph_access_token(refresh_token, client_id)
        if not access_token:
            return None

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            if stop_signal and stop_signal():
                return None
            try:
                response = requests.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "$top": 10,
                        "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,bodyPreview,receivedDateTime"
                    },
                    timeout=15
                )

                if response.status_code in (401, 403):
                    access_token = self._get_graph_access_token(refresh_token, client_id)
                    if not access_token:
                        return None
                    continue

                emails = response.json().get("value", [])

                for email_msg in emails:
                    subject = email_msg.get("subject", "").lower()
                    from_addr = email_msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()

                    is_verify_email = (
                        ("verify" in subject or "confirm" in subject or "email" in subject) and
                        ("discord" in from_addr or "noreply@discord.com" in from_addr)
                    )

                    if not is_verify_email:
                        continue

                    body_html = email_msg.get("body", {}).get("content", "")
                    url = _extract_discord_verification_url(body_html)
                    if url:
                        return url

                    click_patterns = [
                        re.compile(r'https://click\.discord\.com/ls/click\?[^"\'>\\s]+'),
                        re.compile(r'https://links\.discord\.com[^"\'>\\s]+')
                    ]
                    for pat in click_patterns:
                        for m in pat.finditer(body_html):
                            click_url = m.group(0)
                            try:
                                resp = requests.get(click_url, allow_redirects=True, timeout=15, verify=False)
                                if "discord.com/verify" in resp.url:
                                    return resp.url
                                verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'>\\s]+', resp.text)
                                if verify_in_body:
                                    return verify_in_body.group(0)
                            except Exception:
                                pass

                    _log_email_diagnostic("Hotmail007-Graph", email_msg.get("subject", ""), body_html, True)

            except Exception:
                pass

            time.sleep(poll_interval)

        return None

    def get_verification_url(
        self,
        email: str,
        password: str = "",
        timeout: int = 120,
        poll_interval: int = 3,
        refresh_token: str = "",
        client_id: str = "",
        stop_signal: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        if stop_signal and stop_signal():
            return None

        if refresh_token and client_id:
            graph_result = self._get_verification_via_graph(
                refresh_token, client_id, timeout=timeout, poll_interval=poll_interval, stop_signal=stop_signal
            )
            if graph_result:
                return graph_result

        # Fallback to NEW OpenAPI /open/mail/latest endpoint
        account_str = ":".join(filter(None, [email, password, refresh_token, client_id]))
        start_time = time.time()

        while True:
            if stop_signal and stop_signal():
                return None
            try:
                from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic
                for folder in ["inbox", "junkemail"]:
                    resp = self.session.get(
                        f"{self.BASE_URL}/open/mail/latest",
                        params={
                            "clientKey": self.api_key,
                            "account": account_str,
                            "folder": folder
                        },
                        timeout=30
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("code") == 0 and data.get("success") and data.get("data"):
                            mail_data = data["data"]
                            if isinstance(mail_data, dict):
                                html_body = (mail_data.get("html") or mail_data.get("Html") or "")
                                text_body = (mail_data.get("text") or mail_data.get("Text") or "")
                                subject = (mail_data.get("subject") or mail_data.get("Subject") or "")
                                has_discord = ("discord" in (html_body or "").lower() or
                                               "discord" in (text_body or "").lower() or
                                               "discord" in subject.lower())
                                for body in [html_body, text_body]:
                                    if not body:
                                        continue
                                    if has_discord or 'verify' in subject.lower():
                                        url = _extract_discord_verification_url(body)
                                        if url:
                                            return url
            except Exception:
                pass

            if timeout > 0 and time.time() - start_time > timeout:
                return None
            time.sleep(poll_interval)
