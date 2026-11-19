import time
import re
import logging
import sys
import os
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, List
from contextlib import contextmanager

import requests
import tls_client
from playwright.sync_api import Page, Frame

from .discord import HeaderGenerator
from ..Utils.utils import Utils, Config
from ..MskColors.color import MskColor
from ..Utils.logger import Logger

import warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

for logger_name in ['logmagix', 'urllib3', 'requests', 'httpx', 'MailcowApi']:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)
    logging.getLogger(logger_name).disabled = True

# logging.disable(logging.DEBUG)

try:
    import logmagix
    logmagix.Logger.debug = lambda *args, **kwargs: None
    logmagix.Logger.info = lambda *args, **kwargs: None
    logmagix.Logger.success = lambda *args, **kwargs: None
    logmagix.Logger.failure = lambda *args, **kwargs: None
except ImportError:
    pass


_devnull = open(os.devnull, 'w')

@contextmanager
def suppress_output():
    yield


_DISCORD_VERIFY_PATTERNS = [
    re.compile(r'https://click\.discord\.com/ls/click\?upn=[^\s\r\n<>"\']+'),
    re.compile(r'https://links\.discord\.com/ls/click\?upn=[^\s\r\n<>"\']+'),
    re.compile(r'https://discord\.com/verify#token=[^\s\r\n<>"\']+'),
    re.compile(r'https://discord\.com/verify\?token=[^\s\r\n<>"\']+'),
    re.compile(r'https://[a-z0-9.-]*discord\.com/[^\s\r\n<>"\']*verify[^\s\r\n<>"\']*'),
]


def _extract_discord_verification_url(body: str) -> Optional[str]:
    """Extract a Discord verification URL from an email body (HTML or plain text).

    Tries multiple known Discord verification URL patterns in priority order.
    Works with both href-embedded links and plain-text URLs.
    """
    if not body:
        return None

    href_match = re.search(
        r'<a\s[^>]*href=["\']?(https://click\.discord\.com/ls/click\?upn=[^"\'\s<>]+)["\']?[^>]*>\s*Verify\s+Email\s*</a>',
        body,
        re.IGNORECASE | re.DOTALL
    )
    if href_match:
        return href_match.group(1).rstrip('"\'>')

    for pattern in _DISCORD_VERIFY_PATTERNS:
        all_matches = pattern.findall(body)
        if all_matches:
            for match in all_matches:
                pos = body.find(match)
                if pos >= 0:
                    ctx_start = max(0, pos - 300)
                    ctx_end = min(len(body), pos + len(match) + 300)
                    context = body[ctx_start:ctx_end].lower()
                    if 'verify' in context:
                        return match.rstrip('"\'>')
            return all_matches[0].rstrip('"\'>')

    href_pattern = re.compile(
        r'href=["\']?(https://[^\s"\'<>]*discord\.com[^\s"\'<>]*)["\']?',
        re.IGNORECASE
    )
    for m in href_pattern.finditer(body):
        url = m.group(1).lower()
        if 'verify' in url or 'token' in url:
            return m.group(1).rstrip('"\'>')

    return None


def _log_email_diagnostic(provider_name: str, subject: str, body: str, has_discord: bool,
                          sender: str = ""):
    """Log diagnostic info when an email is found but no verification link extracted."""
    body_len = len(body) if body else 0
    body_preview = (body[:200] if body else "(empty)").replace('\n', ' ').replace('\r', '')
    sender_info = f", from='{sender[:30]}'" if sender else ""
    Logger.STATUS = (
        f"{MskColor.YELLOW}[{provider_name}] Email found (subject='{subject[:40]}'{sender_info}, "
        f"discord_mentioned={has_discord}, body_len={body_len}) but no verify link matched. "
        f"Preview: {body_preview[:80]}..."
    )
    Logger.queue_log(worker_id=0)


def _save_account_data_to_file(account_data: dict, provider_name: str) -> None:
    """Save parsed account details to a text file in data/hotmail or data/outlook."""
    try:
        import json
        from pathlib import Path
        
        email = account_data.get("email", "")
        if not email:
            return
            
        domain = email.split('@')[-1].lower() if '@' in email else 'unknown'
        
        if "hotmail" in domain:
            folder_name = "hotmail"
        elif "outlook" in domain:
            folder_name = "outlook"
        else:
            folder_name = domain.replace('.com', '')
            
        base_dir = Path("data") / folder_name
        base_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{email}-{provider_name}.txt"
        filepath = base_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(account_data, f, indent=4)
            
    except Exception as e:
        Logger.STATUS = f"{MskColor.RED}Failed to save account to file: {str(e)[:60]}"
        Logger.queue_log(worker_id=0)


class MskMailApi:
    _domain_cache = {}
    _domain_cache_time = {}

    def __init__(self, api_key: Optional[str] = None) -> None:
        for logger_name in ['logmagix', 'urllib3', 'requests', 'httpx']:
            logging.getLogger(logger_name).setLevel(logging.CRITICAL)
            logging.getLogger(logger_name).disabled = True
        
        from cybertemp import CyberTemp
        free_key = "free"
        if api_key and str(api_key).strip().lower() != "free" and len(str(api_key).strip()) > 10:
            free_key = api_key
            
        self.client = CyberTemp(api_key=free_key)

    def get_domains(self, domain_type: Optional[str] = None) -> List[str]:
        import time
        cache_key = str(domain_type)
        if time.time() - self._domain_cache_time.get(cache_key, 0) < 300 and self._domain_cache.get(cache_key):
            return self._domain_cache[cache_key]

        try:
            all_domains = []
            offset = 0
            limit = 100
            while True:
                kwargs = {"limit": limit, "offset": offset}
                if domain_type:
                    kwargs["type"] = domain_type
                with suppress_output():
                    result = self.client.get_domains(**kwargs)
                if not result:
                    break
                if isinstance(result, dict):
                    domains = result.get("domains", [])
                    total = result.get("total", 0)
                    all_domains.extend([d.get("name") if isinstance(d, dict) else d for d in domains])
                    if len(all_domains) >= total:
                        break
                    offset += limit
                elif isinstance(result, list):
                    all_domains.extend([d.get("name") if isinstance(d, dict) else d for d in result])
                    break
                else:
                    break
            
            if all_domains:
                # filter out broken domain structs if any leaked through
                cleaned = [str(d).strip() for d in all_domains if isinstance(d, str) and "." in d]
                if cleaned:
                    MskMailApi._domain_cache[cache_key] = cleaned
                    MskMailApi._domain_cache_time[cache_key] = time.time()
                    return cleaned
            return MskMailApi._domain_cache.get(cache_key, [])
        except Exception:
            pass
        return MskMailApi._domain_cache.get(cache_key, [])

    def create_account(self, email: str, password: str) -> Optional[str]:
        try:
            with suppress_output():
                self.client.get_email_content(email, max_retries=1, delay_between_retries=1.0)
            return email
        except Exception:
            pass
        return email

    def get_inbox(self, email: str, password: str, poll_interval: int = 3, timeout: int = 0) -> Optional[str]:
        start_time = time.time()
        while True:
            try:
                with suppress_output():
                    emails = self.client.get_email_content(
                        email,
                        max_retries=1,
                        delay_between_retries=1.0
                    )
                
                if emails and len(emails) > 0:
                    for msg in emails:
                        body = msg.get('html', '') or msg.get('text', '') or msg.get('body', '')
                        if body:
                            match = re.search(r'upn=([^\s&"\'<>]+)', body)
                            if match:
                                return match.group(1)

                if timeout > 0 and time.time() - start_time > timeout:
                    return None

            except Exception:
                if timeout > 0 and time.time() - start_time > timeout:
                    return None

            time.sleep(poll_interval)

    def get_verification_url(self, email: str, timeout: int = 0, poll_interval: int = 3, stop_signal=None) -> Optional[str]:
        start_time = time.time()
        consecutive_api_failures = 0
        max_api_failures = 3  # fail fast if key is invalid
        
        while True:
            # Respect stop signal — exit immediately when user presses Stop
            if stop_signal is not None and callable(stop_signal) and stop_signal():
                return None
            
            try:
                with suppress_output():
                    emails = self.client.get_email_content(
                        email,
                        max_retries=1,
                        delay_between_retries=1.0
                    )
                
                if emails is None:
                    # None means API call failed (invalid key, network error, etc.)
                    consecutive_api_failures += 1
                    if consecutive_api_failures >= max_api_failures:
                        # Key is likely invalid — abort instead of polling forever
                        return None
                elif isinstance(emails, list) and len(emails) > 0:
                    consecutive_api_failures = 0
                    for msg in emails:
                        subject = msg.get('subject', '')
                        html_body = msg.get('html', '') or ''
                        text_body = msg.get('text', '') or msg.get('body', '') or ''
                        
                        for body in [html_body, text_body]:
                            if not body:
                                continue
                            url = _extract_discord_verification_url(body)
                            if url:
                                return url
                        
                        combined = html_body or text_body
                        if combined and ('discord' in combined.lower() or 'verify' in subject.lower()):
                            _log_email_diagnostic("CyberTemp", subject, combined, "discord" in (combined or "").lower())
                else:
                    # Empty list = no emails yet, that's normal
                    consecutive_api_failures = 0

            except Exception:
                consecutive_api_failures += 1
                if consecutive_api_failures >= max_api_failures:
                    return None

            if timeout > 0 and time.time() - start_time > timeout:
                return None
            
            # Sleep in small increments so stop_signal is checked frequently
            sleep_end = time.time() + poll_interval
            while time.time() < sleep_end:
                if stop_signal is not None and callable(stop_signal) and stop_signal():
                    return None
                time.sleep(0.3)

class DuckMailApi:
    """DuckMail email provider API client"""
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_url = "https://api.duckmail.sbs"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.token = None
        if self.api_key:
            self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})

    def get_domains(self, domain_type: Optional[str] = None) -> List[str]:
        try:
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            with suppress_output():
                resp = self.session.get(f"{self.api_url}/domains", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                domains = []
                for item in data.get('hydra:member', []):
                    domains.append(item.get('domain'))
                return domains
        except Exception:
            pass
        return []

    def authenticate(self, email: str, password: str) -> bool:
        if self.token:
            return True
        try:
            with suppress_output():
                resp = self.session.post(f"{self.api_url}/token", json={"address": email, "password": password})
            if resp.status_code == 200:
                self.token = resp.json().get('token')
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                return True
        except Exception:
            pass
        return False

    def create_account(self, email: str, password: str) -> Optional[str]:
        try:
            payload = {
                "address": email,
                "password": password,
                "expiresIn": 0
            }
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            with suppress_output():
                resp = self.session.post(f"{self.api_url}/accounts", json=payload, headers=headers)
            if resp.status_code == 201 or resp.status_code == 409:
                self.authenticate(email, password)
                return email
        except Exception:
            pass
        return email

    def get_verification_url(self, email: str, password: str, timeout: int = 0, poll_interval: int = 3, **kwargs) -> Optional[str]:
        start_time = time.time()
        self.authenticate(email, password)
        stop_signal = kwargs.get('stop_signal')
        while True:
            if stop_signal and stop_signal():
                return None
            try:
                with suppress_output():
                    resp = self.session.get(f"{self.api_url}/messages")
                if resp.status_code == 200:
                    data = resp.json()
                    members = data.get('hydra:member', [])
                    for msg in members:
                        msg_id = msg.get('id')
                        with suppress_output():
                            detail_resp = self.session.get(f"{self.api_url}/messages/{msg_id}")
                        if detail_resp.status_code == 200:
                            detail = detail_resp.json()
                            html_body = ''
                            html_list = detail.get('html', [])
                            if isinstance(html_list, list):
                                html_body = ''.join(html_list)
                            elif isinstance(html_list, str):
                                html_body = html_list
                            text_body = detail.get('text', '')
                            for body in [html_body, text_body]:
                                if not body: continue
                                url = _extract_discord_verification_url(body)
                                if url:
                                    return url
            except Exception:
                pass
            
            if timeout > 0 and time.time() - start_time > timeout:
                return None
            time.sleep(poll_interval)


class MailcowApi:
    """Mailcow email provider API client"""
    def __init__(self, host_url: str, api_key: str) -> None:
        self.host_url = host_url.rstrip('/')
        if self.host_url and not self.host_url.startswith("http"):
            self.host_url = f"https://{self.host_url}"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        })

    def get_domains(self) -> List[str]:
        """Get available domains from Mailcow server"""
        try:
            response = self.session.get(f"{self.host_url}/api/v1/get/domain/all")
            if response.status_code == 200:
                domains = response.json()
                return [d.get('domain_name', '') for d in domains if d.get('active', 0) == 1]
        except Exception:
            pass
        return []

    def create_account(self, email: str, password: str) -> Optional[str]:
        """Create a mailbox on Mailcow server"""
        try:
            username, domain = email.split('@')
            payload = {
                "local_part": username,
                "domain": domain,
                "name": username,
                "password": password,
                "password2": password,
                "quota": 1,
                "active": 1
            }
            response = self.session.post(f"{self.host_url}/api/v1/add/mailbox", json=payload)
            if response.status_code == 200:
                result = response.json()
                if result and result[0].get('type') == 'success':
                    return email
        except Exception:
            pass
        return None

    def get_verification_url(self, email: str, password: str, timeout: int = 60, poll_interval: int = 3, **kwargs) -> Optional[str]:
        """Retrieve Discord verification email via IMAP using the Mailcow server"""
        import imaplib
        import email as email_module
        from urllib.parse import urlparse
        import logging
        
        logger = logging.getLogger("MailcowApi")
        
        if not timeout or timeout <= 0:
            timeout = 120
        
        start_time = time.time()
        
        imap_host = self.host_url
        if imap_host:
            parsed = urlparse(imap_host)
            imap_host = parsed.hostname or parsed.path
        
        if not imap_host:
            logger.error("Mailcow IMAP host is empty, cannot verify email")
            return None
        
        logger.info(f"Connecting to IMAP server: {imap_host} for {email}")
        attempt = 0
        
        while time.time() - start_time < timeout:
            attempt += 1
            imap = None
            try:
                imap = imaplib.IMAP4_SSL(imap_host, timeout=15)
                imap.login(email, password)
                imap.select('INBOX')
                
                _, message_numbers = imap.search(None, 'FROM', '"noreply@discord.com"')
                
                if message_numbers[0]:
                    for num in reversed(message_numbers[0].split()):
                        _, msg_data = imap.fetch(num, '(RFC822)')
                        email_body = msg_data[0][1]
                        message = email_module.message_from_bytes(email_body)
                        
                        body = ""
                        if message.is_multipart():
                            for part in message.walk():
                                if part.get_content_type() == "text/html":
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                                    break
                                elif part.get_content_type() == "text/plain" and not body:
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                        else:
                            body = message.get_payload(decode=True).decode(errors='ignore')
                        
                        url = _extract_discord_verification_url(body)
                        if url:
                            try:
                                imap.close()
                                imap.logout()
                            except Exception:
                                pass
                            logger.info(f"Found Discord verification URL on attempt {attempt}")
                            return url
                        
                        subject = message.get("Subject", "")
                        sender = message.get("From", "")
                        _log_email_diagnostic("Mailcow", subject, body, "discord" in body.lower(), sender=sender)
                    
                    logger.debug(f"Attempt {attempt}: Found Discord emails but no verification URL yet")
                else:
                    logger.debug(f"Attempt {attempt}: No Discord emails in inbox yet, waiting...")
                
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass
                
            except imaplib.IMAP4.error as e:
                logger.warning(f"Attempt {attempt}: IMAP error for {email} on {imap_host}: {e}")
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except ConnectionRefusedError:
                logger.error(f"IMAP connection refused on {imap_host}:993 — is IMAP enabled?")
                return None
            except OSError as e:
                logger.warning(f"Attempt {attempt}: Connection error to {imap_host}: {e}")
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Attempt {attempt}: Unexpected error: {type(e).__name__}: {e}")
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            
            time.sleep(poll_interval)
        
        logger.warning(f"Email verification timed out after {timeout}s ({attempt} attempts) for {email}")
        return None


class ZeusApi:
    """Zeus email account purchasing API client (api.zeus-x.ru)"""
    
    ACCOUNT_CODES = {
        "Hotmail New": "HOTMAIL",
        "Outlook New": "OUTLOOK",
        "Hotmail Trusted [Graph API]": "HOTMAIL_TRUSTED_GRAPH_API",
        "Outlook Trusted [Graph API]": "OUTLOOK_TRUSTED_GRAPH_API",
        "Hotmail Trusted [IMAP/POP3]": "HOTMAIL_TRUSTED",
        "Outlook Trusted [IMAP/POP3]": "OUTLOOK_TRUSTED",
    }
    
    def __init__(self, api_key: str, account_type: str = "HOTMAIL") -> None:
        self.api_key = api_key
        self.account_code = self.ACCOUNT_CODES.get(account_type, account_type)
        self.base_url = "https://api.zeus-x.ru"
        self.session = requests.Session()
    
    def check_balance(self) -> Optional[float]:
        """Check Zeus account balance"""
        try:
            resp = self.session.get(
                f"{self.base_url}/balance",
                params={"apikey": self.api_key},
                timeout=15
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    # 200 but non-JSON body — treat as valid (server accepted key)
                    return 0.0
                # Accept both "Code" and "code" (API may use either casing)
                code = data.get("Code", data.get("code", None))
                if code == 0 or code == "0":
                    bal = data.get("Data", data.get("data", {}))
                    if isinstance(bal, dict):
                        bal = bal.get("Balance", bal.get("balance", 0))
                    return float(bal) if bal is not None else 0.0
                # 200 with any non-error body → key was accepted, balance unknown
                if code is None:
                    return 0.0
            elif resp.status_code in (401, 403):
                return None
            else:
                # Any other status — treat as connection issue not invalid key
                return 0.0
        except Exception:
            pass
        return None
    
    def check_instock(self) -> int:
        """Check how many accounts are in stock for the selected type"""
        try:
            resp = self.session.get(f"{self.base_url}/instock", timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("Code") == 0:
                    for item in data.get("Data", []):
                        if item.get("AccountCode") == self.account_code:
                            return item.get("Instock", 0)
        except Exception:
            pass
        return 0
    
    def create_account(self) -> Optional[Dict[str, str]]:
        """Purchase one email account from Zeus"""
        try:
            resp = self.session.get(
                f"{self.base_url}/purchase",
                params={
                    "apikey": self.api_key,
                    "accountcode": self.account_code,
                    "quantity": 1
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                raise Exception(f"Zeus HTTP {resp.status_code}: {resp.text[:80]}")
            
            data = resp.json()
            
            if not isinstance(data, dict):
                raise Exception(f"Zeus unexpected response: {str(data)[:80]}")
            
            code = data.get("Code")
            
            if code == 0 or code == "0":
                purchase_data = data.get("Data")
                if not purchase_data:
                    raise Exception("Zeus: purchase succeeded but no data returned (out of stock?)")
                
                accounts = None
                if isinstance(purchase_data, dict):
                    for key in ["Accounts", "accounts", "Items", "items", "Data", "data"]:
                        if key in purchase_data and isinstance(purchase_data[key], list):
                            accounts = purchase_data[key]
                            break
                    
                    if accounts is None:
                        result = self._extract_account_fields(purchase_data)
                        if result:
                            return result
                        
                        for val in purchase_data.values():
                            if isinstance(val, str) and ":" in val and "@" in val:
                                parts = val.split(":", 1)
                                return {"email": parts[0].strip(), "password": parts[1].strip()}
                        
                        raise Exception(f"Zeus: can't find accounts in response: {str(purchase_data)[:100]}")
                
                elif isinstance(purchase_data, list):
                    accounts = purchase_data
                elif isinstance(purchase_data, str) and ":" in purchase_data:
                    parts = purchase_data.split(":", 1)
                    return {"email": parts[0].strip(), "password": parts[1].strip()}
                else:
                    raise Exception(f"Zeus: unexpected Data type: {str(purchase_data)[:80]}")
                
                if accounts and len(accounts) > 0:
                    acc = accounts[0]
                    if isinstance(acc, dict):
                        result = self._extract_account_fields(acc)
                        if result:
                            _save_account_data_to_file(result, "zeus")
                            return result
                    
                    acc_str = str(acc)
                    if ":" in acc_str:
                        parts = acc_str.split(":", 1)
                        result = {"email": parts[0].strip(), "password": parts[1].strip()}
                        _save_account_data_to_file(result, "zeus")
                        return result
                    
                    raise Exception(f"Zeus: can't parse account: {acc_str[:60]}")
                else:
                    raise Exception("Zeus: empty accounts list returned")
            else:
                error_msg = data.get("Message") or data.get("message") or f"error code {code}"
                raise Exception(f"Zeus: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Zeus connection error: {str(e)[:60]}")
        except Exception:
            raise
    
    @staticmethod
    def _extract_account_fields(d: dict) -> Optional[Dict[str, str]]:
        """Extract email, password, refresh_token, client_id from a Zeus account dict."""
        email = (d.get("email") or d.get("Email") or 
                d.get("login") or d.get("Login") or
                d.get("Account") or d.get("account") or "")
        password = (d.get("password") or d.get("Password") or 
                   d.get("pass") or d.get("Pass") or "")
        if not email or not password:
            return None
        result = {"email": str(email).strip(), "password": str(password).strip()}
        refresh_token = (d.get("RefreshToken") or d.get("refresh_token") or "")
        client_id = (d.get("ClientId") or d.get("client_id") or "")
        if refresh_token:
            result["refresh_token"] = str(refresh_token).strip()
        if client_id:
            result["client_id"] = str(client_id).strip()
        return result
    
    def _get_access_token(self, refresh_token: str, client_id: str) -> Optional[str]:
        """Exchange a refresh token for an access token via Microsoft OAuth2.
        
        Tries 'common' tenant with '.default' scope first (most compatible),
        then falls back to 'consumers' tenant with specific scopes.
        """
        if refresh_token and refresh_token.endswith("$"):
            refresh_token = refresh_token[:-1]
        
        try:
            resp = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": "https://graph.microsoft.com/.default",
                },
                timeout=15,
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
                    "client_id": client_id,
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

    def _get_verification_via_imap(self, email: str, password: str, timeout: int = 60,
                                    poll_interval: int = 3) -> Optional[str]:
        """IMAP fallback for Zeus accounts without Graph API tokens.

        Connects to outlook.office365.com via IMAP to read inbox directly.
        """
        import imaplib
        import email as email_module

        imap_host = "outlook.office365.com"
        start_time = time.time()
        attempt = 0

        Logger.STATUS = f"{MskColor.YELLOW}[Zeus] No Graph API tokens, trying IMAP fallback ({imap_host})..."
        Logger.queue_log(worker_id=0)

        while time.time() - start_time < timeout:
            attempt += 1
            imap = None
            try:
                imap = imaplib.IMAP4_SSL(imap_host, timeout=15)
                imap.login(email, password)
                imap.select('INBOX')

                _, message_numbers = imap.search(None, 'FROM', '"noreply@discord.com"')

                if message_numbers[0]:
                    for num in reversed(message_numbers[0].split()):
                        _, msg_data = imap.fetch(num, '(RFC822)')
                        email_body = msg_data[0][1]
                        message = email_module.message_from_bytes(email_body)

                        body = ""
                        if message.is_multipart():
                            for part in message.walk():
                                if part.get_content_type() == "text/html":
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                                    break
                                elif part.get_content_type() == "text/plain" and not body:
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                        else:
                            body = message.get_payload(decode=True).decode(errors='ignore')

                        url = _extract_discord_verification_url(body)
                        if url:
                            try:
                                imap.close()
                                imap.logout()
                            except Exception:
                                pass
                            return url

                        subject = message.get("Subject", "")
                        sender = message.get("From", "")
                        _log_email_diagnostic("Zeus-IMAP", subject, body, "discord" in body.lower(), sender=sender)

                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

            except imaplib.IMAP4.error as e:
                err_str = str(e).lower()
                if "login" in err_str or "authentication" in err_str or "invalid" in err_str:
                    Logger.STATUS = f"{MskColor.RED}[Zeus] IMAP login failed for {email}: {str(e)[:60]}"
                    Logger.queue_log(worker_id=0)
                    return None
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except (ConnectionRefusedError, OSError) as e:
                Logger.STATUS = f"{MskColor.RED}[Zeus] IMAP connection error ({imap_host}): {str(e)[:60]}"
                Logger.queue_log(worker_id=0)
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except Exception:
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass

            time.sleep(poll_interval)

        Logger.STATUS = f"{MskColor.RED}[Zeus] IMAP verification timed out after {timeout}s ({attempt} attempts)"
        Logger.queue_log(worker_id=0)
        return None

    def get_verification_url(self, email: str, password: str, timeout: int = 60, poll_interval: int = 3,
                             refresh_token: str = "", client_id: str = "", **kwargs) -> Optional[str]:
        """Retrieve Discord verification email from Hotmail/Outlook.

        Primary method: Microsoft Graph API (requires refresh_token + client_id).
        Fallback: IMAP login to outlook.office365.com using email + password.
        """
        if not refresh_token or not client_id:
            return self._get_verification_via_imap(email, password, timeout, poll_interval)
        
        start_time = time.time()
        graph_auth_failures = 0
        
        while True:
            try:
                access_token = self._get_access_token(refresh_token, client_id)
                if not access_token:
                    graph_auth_failures += 1
                    if graph_auth_failures >= 3:
                        Logger.STATUS = f"{MskColor.YELLOW}[Zeus] Graph API auth failed {graph_auth_failures}x, trying IMAP fallback..."
                        Logger.queue_log(worker_id=0)
                        remaining = max(30, timeout - int(time.time() - start_time))
                        return self._get_verification_via_imap(email, password, remaining, poll_interval)
                    if timeout > 0 and time.time() - start_time > timeout:
                        Logger.STATUS = f"{MskColor.RED}[Zeus] Graph API auth failed, trying IMAP fallback..."
                        Logger.queue_log(worker_id=0)
                        remaining = max(30, timeout - int(time.time() - start_time))
                        return self._get_verification_via_imap(email, password, remaining, poll_interval)
                    time.sleep(poll_interval)
                    continue
                
                headers = {"Authorization": f"Bearer {access_token}"}
                resp = requests.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers=headers,
                    params={
                        "$top": 5,
                        "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,bodyPreview,receivedDateTime"
                    },
                    timeout=15
                )
                
                if resp.status_code == 200:
                    messages = resp.json().get("value", [])
                    for msg in messages:
                        subject = msg.get("subject", "").lower()
                        from_addr = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                        
                        is_discord_verify = (
                            ("discord" in from_addr or "noreply@discord.com" in from_addr) and
                            ("verify" in subject or "confirm" in subject or "email" in subject)
                        )
                        
                        if not is_discord_verify:
                            continue
                        
                        body_content = msg.get("body", {}).get("content", "")
                        if body_content:
                            url = _extract_discord_verification_url(body_content)
                            if url:
                                return url
                            
                            click_patterns = [
                                re.compile(r'https://click\.discord\.com/ls/click\?[^"\'>\s]+'),
                                re.compile(r'https://links\.discord\.com[^"\'>\s]+')
                            ]
                            for pat in click_patterns:
                                for m in pat.finditer(body_content):
                                    click_url = m.group(0)
                                    try:
                                        click_resp = requests.get(click_url, allow_redirects=True, timeout=15, verify=False)
                                        final_url = click_resp.url
                                        if "discord.com/verify" in final_url:
                                            return final_url
                                        verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'>\s]+', click_resp.text)
                                        if verify_in_body:
                                            return verify_in_body.group(0)
                                    except Exception:
                                        pass
                            
                            _log_email_diagnostic("Zeus-Graph", msg.get("subject", ""), body_content, True)
                elif resp.status_code in (401, 403):
                    Logger.STATUS = f"{MskColor.YELLOW}[Zeus] Graph API returned {resp.status_code}, trying IMAP..."
                    Logger.queue_log(worker_id=0)
                    remaining = max(30, timeout - int(time.time() - start_time))
                    return self._get_verification_via_imap(email, password, remaining, poll_interval)
            except Exception:
                pass
            
            if timeout > 0 and time.time() - start_time > timeout:
                return None
            
            time.sleep(poll_interval)


class Hotmail007Api:
    """Hotmail007 email account purchasing and verification API client (hotmail007.com)"""
    
    BASE_URL = "https://gapi.hotmail007.com"
    
    MAIL_TYPES = {
        "hotmail": "hotmail",
        "outlook": "outlook",
        "hotmail_trusted": "hotmail Trusted",
        "outlook_trusted": "outlook Trusted",
    }
    
    def __init__(self, api_key: str, mail_type: str = "hotmail") -> None:
        self.api_key = api_key
        normalized = mail_type.lower().replace(" ", "_")
        self.mail_type = self.MAIL_TYPES.get(normalized, mail_type)
        self.session = requests.Session()
    
    def check_balance(self) -> Optional[float]:
        """Check Hotmail007 account balance"""
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/user/balance",
                params={"clientKey": self.api_key},
                timeout=15
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    return 0.0
                # Accept truthy success field or status == "ok" / "success"
                success = data.get("success", data.get("status", None))
                if success is True or str(success).lower() in ("ok", "success", "1", "true"):
                    bal = data.get("data", data.get("balance", {}))
                    if isinstance(bal, dict):
                        bal = bal.get("balance", bal.get("Balance", 0))
                    return float(bal) if bal is not None else 0.0
                # 200 but unexpected body shape — key accepted by server
                if success is None:
                    return 0.0
            elif resp.status_code in (401, 403):
                return None
            else:
                return 0.0
        except Exception:
            pass
        return None
    
    def get_stock(self) -> Dict[str, int]:
        """Check Hotmail007 account stock for all types.
        
        Returns dict of mailType: count.
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/mail/getStock",
                params={"clientKey": self.api_key},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("success"):
                    stock_data = data.get("data", {})
                    return stock_data if isinstance(stock_data, dict) else {}
        except Exception:
            pass
        return {}
    
    def create_account(self) -> Optional[Dict[str, str]]:
        """Purchase one email account from Hotmail007.
        
        Returns dict with email, password, refresh_token, client_id.
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/api/mail/getMail",
                params={
                    "clientKey": self.api_key,
                    "mailType": self.mail_type,
                    "quantity": 1
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                raise Exception(f"Hotmail007 HTTP {resp.status_code}: {resp.text[:80]}")
            
            data = resp.json()
            
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
                        _save_account_data_to_file(result, "hotmail007")
                        return result
                    elif len(parts) >= 2:
                        result = {
                            "email": parts[0].strip(),
                            "password": parts[1].strip()
                        }
                        _save_account_data_to_file(result, "hotmail007")
                        return result
                    raise Exception(f"Hotmail007: unexpected account format: {account_str[:60]}")
                raise Exception("Hotmail007: empty accounts list returned (out of stock?)")
            else:
                stock = self.get_stock()
                current_stock = stock.get(self.mail_type, 0) if isinstance(stock, dict) else 0
                
                if isinstance(data, dict):
                    error_msg = data.get("message") or data.get("msg") or f"code {data.get('code')}"
                else:
                    error_msg = f"Unexpected response: {str(data)[:60]}"
                    
                if "buy error" in error_msg.lower() and current_stock <= 0:
                    error_msg = f"Out of Stock for type '{self.mail_type}' (Stock: {current_stock})"
                
                raise Exception(f"Hotmail007: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Hotmail007 connection error: {str(e)[:60]}")
        except Exception:
            raise
    
    def _build_account_string(self, email: str, password: str,
                               refresh_token: str = "", client_id: str = "") -> str:
        """Build the full account string for Hotmail007 API calls."""
        parts = [email, password]
        if refresh_token:
            parts.append(refresh_token)
            if client_id:
                parts.append(client_id)
        return ":".join(parts)
    
    @staticmethod
    def _get_graph_access_token(refresh_token: str, client_id: str) -> Optional[str]:
        """Exchange a refresh token for an MS Graph access token.
        
        Uses 'common' tenant with '.default' scope (most compatible with hotmail007 accounts).
        Falls back to 'consumers' tenant if needed.
        """
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
                                     timeout: int = 120, poll_interval: int = 3) -> Optional[str]:
        """Read Discord verification email directly via MS Graph API.
        
        This is the primary verification method for Hotmail007 accounts
        that come with refresh tokens. Mirrors the approach from the working
        single-file generator.
        """
        access_token = self._get_graph_access_token(refresh_token, client_id)
        if not access_token:
            Logger.STATUS = f"{MskColor.RED}[Hotmail007] Failed to get Graph API access token"
            Logger.queue_log(worker_id=0)
            return None
        
        start_time = time.time()
        attempt = 0
        
        while (time.time() - start_time) < timeout:
            attempt += 1
            try:
                response = requests.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "$top": 5,
                        "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,bodyPreview,receivedDateTime"
                    },
                    timeout=15
                )
                
                if response.status_code in (401, 403):
                    access_token = self._get_graph_access_token(refresh_token, client_id)
                    if not access_token:
                        Logger.STATUS = f"{MskColor.RED}[Hotmail007] Graph token refresh failed"
                        Logger.queue_log(worker_id=0)
                        return None
                    continue
                
                emails = response.json().get("value", [])
                
                if attempt % 3 == 0:
                    elapsed = int(time.time() - start_time)
                    Logger.STATUS = f"{MskColor.YELLOW}[Hotmail007] Checking inbox via Graph API... ({elapsed}s elapsed)"
                    Logger.queue_log(worker_id=0)
                
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
                        re.compile(r'https://click\.discord\.com/ls/click\?[^"\'>\s]+'),
                        re.compile(r'https://links\.discord\.com[^"\'>\s]+')
                    ]
                    
                    for pat in click_patterns:
                        for m in pat.finditer(body_html):
                            click_url = m.group(0)
                            try:
                                resp = requests.get(click_url, allow_redirects=True, timeout=15, verify=False)
                                final_url = resp.url
                                
                                if "discord.com/verify" in final_url:
                                    return final_url
                                
                                verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'>\s]+', resp.text)
                                if verify_in_body:
                                    return verify_in_body.group(0)
                            except Exception:
                                pass
                    
                    _log_email_diagnostic("Hotmail007-Graph", email_msg.get("subject", ""), body_html, True)
                    
            except Exception:
                pass
            
            time.sleep(poll_interval)
        
        Logger.STATUS = f"{MskColor.RED}[Hotmail007] Graph API verification timed out after {timeout}s"
        Logger.queue_log(worker_id=0)
        return None

    def get_verification_url(self, email: str, password: str, timeout: int = 60,
                              poll_interval: int = 5, refresh_token: str = "",
                              client_id: str = "", **kwargs) -> Optional[str]:
        """Retrieve Discord verification email from Hotmail007.
        
        Primary method: MS Graph API (requires refresh_token + client_id from purchase).
        Fallback: Hotmail007's getFirstMail API endpoint.
        """
        if refresh_token and client_id:
            Logger.STATUS = f"{MskColor.PRIMARY}[Hotmail007] Using MS Graph API for email verification"
            Logger.queue_log(worker_id=0)
            graph_result = self._get_verification_via_graph(
                refresh_token, client_id, timeout=timeout, poll_interval=poll_interval
            )
            if graph_result:
                return graph_result
            Logger.STATUS = f"{MskColor.YELLOW}[Hotmail007] Graph API failed, trying getFirstMail API fallback..."
            Logger.queue_log(worker_id=0)
        
        account_str = self._build_account_string(email, password, refresh_token, client_id)
        start_time = time.time()
        
        while True:
            try:
                for folder in ["inbox", "junkemail"]:
                    resp = self.session.get(
                        f"{self.BASE_URL}/v1/mail/getFirstMail",
                        params={
                            "clientKey": self.api_key,
                            "account": account_str,
                            "folder": folder
                        },
                        timeout=30
                    )
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("success") and data.get("data"):
                            mail_data = data["data"]
                            if isinstance(mail_data, dict):
                                html_body = (mail_data.get("Html") or mail_data.get("html") or
                                           mail_data.get("body") or "")
                                text_body = (mail_data.get("Text") or mail_data.get("text") or "")
                                subject = (mail_data.get("Subject") or mail_data.get("subject") or "")
                                
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
                                
                                if has_discord:
                                    combined = html_body or text_body
                                    _log_email_diagnostic("Hotmail007", subject, combined, has_discord)
            except Exception:
                pass
            
            if timeout > 0 and time.time() - start_time > timeout:
                return None
            
            time.sleep(poll_interval)


class LutionApi:
    """Lution email account purchasing and verification API client (lution.ee)
    
    Uses the V2 API at https://api.lution.ee/v2
    Auth: Bearer token header + apikey query param fallback.
    Buy response: { "success": true, "data": { "list": "email:pass:token:clientid\\n..." } }

    Category codes updated 2026: Lution now uses dot-separated codes (e.g. "hotmail.trusted.graph")
    and added new account tiers (hotmail5, hotmail4, hotmail3, hotmail2, etc.).
    """
    
    BASE_URL = "https://api.lution.ee/v2"
    
    # Updated category codes: Lution migrated from underscore to dot-separated codes.
    # Old code -> new code mapping handled in __init__ for backward compatibility.
    CATEGORY_CODES = {
        # New dot-separated codes (current API)
        "Hotmail": "hotmail",
        "Outlook": "outlook",
        "Hotmail Trusted (IMAP,GRAPH)": "hotmail.trusted",
        "Outlook Trusted (IMAP,GRAPH)": "outlook.trusted",
        "Hotmail Trusted (GRAPH)": "hotmail.trusted.graph",
        "Outlook Trusted (GRAPH)": "outlook.trusted.graph",
        "Hotmail SMTP": "hotmail.smtp",
        "Outlook SMTP": "outlook.smtp",
        "Hotmail (without tokens)": "hotmail",
        "Outlook (without tokens)": "outlook",
        # New account tiers (aged accounts with trust scores)
        "Hotmail5": "hotmail5",
        "Hotmail4": "hotmail4",
        "Hotmail3": "hotmail3",
        "Hotmail2": "hotmail2",
        "Outlook5": "outlook5",
        "Outlook4": "outlook4",
        "Outlook3": "outlook3",
        "Outlook2": "outlook2",
    }

    # Map old underscore codes (from config) to new dot-separated codes
    _LEGACY_CODE_MAP = {
        "hotmail_trusted": "hotmail.trusted",
        "outlook_trusted": "outlook.trusted",
        "hotmail_trusted_graph": "hotmail.trusted.graph",
        "outlook_trusted_graph": "outlook.trusted.graph",
        "hotmail_no_tokens": "hotmail",
        "outlook_no_tokens": "outlook",
    }
    
    def __init__(self, api_key: str, category: str = "hotmail.trusted.graph") -> None:
        self.api_key = api_key
        # Resolve display name -> code
        resolved = self.CATEGORY_CODES.get(category, category)
        # Migrate legacy underscore codes to current dot-separated codes
        resolved = self._LEGACY_CODE_MAP.get(resolved, resolved)
        self.category = resolved
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
    
    def _params(self, extra: Optional[Dict] = None) -> Dict:
        """Build query params with apikey fallback for robustness."""
        p = {"apikey": self.api_key}
        if extra:
            p.update(extra)
        return p
    
    def check_balance(self) -> Optional[float]:
        """Check Lution account balance via GET /user/me"""
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/user/me",
                params=self._params(),
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("data", {}).get("balance")
        except Exception:
            pass
        return None
    
    def get_stock(self) -> Dict[str, int]:
        """Check Lution account stock for all categories.
        
        V2 response: { "success": true, "data": [ { "category": "...", "price": ..., "stock": N }, ... ] }
        Returns dict of category: stock_count.
        """
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/email/stock",
                params=self._params(),
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("success"):
                    stock_list = data.get("data", [])
                    if isinstance(stock_list, list):
                        return {item.get("category", ""): item.get("stock", 0) for item in stock_list}
        except Exception:
            pass
        return {}
    
    def create_account(self) -> Optional[Dict[str, str]]:
        """Purchase one email account from Lution V2 API.

        Current API endpoint: POST /v2/email/buy
        Request body: { "category": "hotmail.trusted.graph", "quantity": 1 }
        Response: {
          "success": true,
          "data": [
            { "email": "...", "password": "...", "refresh_token": "...", "client_id": "..." }
          ]
        }
        Also handles legacy formats:
          - data.list (newline-separated "email:pass:token:clientid" string)
          - data.emails (list of dicts)
          - data.purchase.accounts (list of strings)
        """
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/email/buy",
                params=self._params(),
                json={
                    "category": self.category,
                    "quantity": 1
                },
                timeout=30
            )

            if resp.status_code != 200:
                raise Exception(f"Lution HTTP {resp.status_code}: {resp.text[:120]}")

            data = resp.json()

            if not isinstance(data, dict) or not data.get("success"):
                error_msg = (
                    data.get("message") or data.get("msg") or
                    data.get("error") or f"code {data.get('code', 'unknown')}"
                )
                stock = self.get_stock()
                current_stock = stock.get(self.category, 0)
                if current_stock <= 0:
                    error_msg = f"Out of Stock for category '{self.category}' (Stock: {current_stock})"
                raise Exception(f"Lution: {error_msg}")

            response_data = data.get("data", {})

            # Format 1: data is a list of account dicts (current API as of 2026)
            if isinstance(response_data, list) and len(response_data) > 0:
                acc = response_data[0]
                if isinstance(acc, dict):
                    result = self._extract_dict_account(acc)
                    if result:
                        _save_account_data_to_file(result, "lution")
                        return result
                # Possibly a list of strings
                if isinstance(acc, str):
                    result = self._parse_account_string(acc)
                    if result:
                        _save_account_data_to_file(result, "lution")
                        return result

            # Format 2: data is a dict with an "emails" list
            if isinstance(response_data, dict):
                emails_list = response_data.get("emails", [])
                if emails_list and isinstance(emails_list, list) and len(emails_list) > 0:
                    acc = emails_list[0]
                    if isinstance(acc, dict):
                        result = self._extract_dict_account(acc)
                        if result:
                            _save_account_data_to_file(result, "lution")
                            return result

                # Format 3: data.list is a newline-separated colon-delimited string
                account_list_str = response_data.get("list", "")
                if account_list_str and isinstance(account_list_str, str):
                    lines = [ln.strip() for ln in account_list_str.strip().split("\n") if ln.strip()]
                    if lines:
                        result = self._parse_account_string(lines[0])
                        if result:
                            _save_account_data_to_file(result, "lution")
                            return result

                # Format 4: data.purchase.accounts
                purchase_data = response_data.get("purchase", {})
                if isinstance(purchase_data, dict):
                    accounts_raw = purchase_data.get("accounts", [])
                    if accounts_raw and len(accounts_raw) > 0:
                        result = self._parse_account_string(accounts_raw[0])
                        if result:
                            _save_account_data_to_file(result, "lution")
                            return result

            raise Exception(
                f"Lution: purchase succeeded but could not parse accounts from response: "
                f"{str(response_data)[:120]}"
            )

        except requests.exceptions.RequestException as e:
            raise Exception(f"Lution connection error: {str(e)[:60]}")
        except Exception:
            raise

    @staticmethod
    def _extract_dict_account(acc: dict) -> Optional[Dict[str, str]]:
        """Extract account details from a Lution account dict response."""
        email = acc.get("email", "").strip()
        password = acc.get("password", "").strip()
        if not email or not password:
            return None
        result = {"email": email, "password": password}
        # Graph refresh token — try several field names used by different Lution versions
        rt = (
            acc.get("graph_refresh_token") or
            acc.get("refresh_token") or
            acc.get("token") or
            ""
        )
        if rt:
            result["refresh_token"] = str(rt).strip()
        # Client ID — Lution uses "thunderbird_client_id" or "client_id"
        cid = acc.get("thunderbird_client_id") or acc.get("client_id") or ""
        if cid:
            result["client_id"] = str(cid).strip()
        return result
    
    @staticmethod
    def _parse_account_string(account_str: str) -> Optional[Dict[str, str]]:
        """Parse account string like 'email:password:refresh_token:client_id'.

        Handles refresh tokens that contain colons (MS OAuth tokens sometimes do).
        Format: email : password : refresh_token : client_id
        The email always contains exactly one '@', password never does, so we split
        on-at-sign boundary to be safe.
        """
        if not isinstance(account_str, str):
            return None
        parts = account_str.split(":")
        if len(parts) < 2:
            return None
        result = {
            "email": parts[0].strip(),
            "password": parts[1].strip(),
        }
        if len(parts) >= 3 and parts[2].strip():
            # Refresh tokens can contain colons — rejoin everything from index 2 onward
            # and split off the client_id (last part, typically a UUID with no colons)
            remainder = ":".join(parts[2:])
            # Client IDs are UUIDs: 8-4-4-4-12 hex chars with hyphens (no colons)
            # Refresh tokens are long base64/JWT strings that may contain colons.
            # Split from the right: last 36-char UUID-like segment = client_id
            import re as _re
            uuid_pattern = _re.compile(r'^[0-9a-fA-F\-]{32,36}$')
            # Try splitting off the last colon-separated chunk as client_id
            sub_parts = remainder.split(":")
            if len(sub_parts) >= 2 and uuid_pattern.match(sub_parts[-1]):
                result["client_id"] = sub_parts[-1].strip()
                result["refresh_token"] = ":".join(sub_parts[:-1]).strip()
            else:
                result["refresh_token"] = remainder.strip()
                if len(parts) >= 4 and parts[3].strip():
                    result["client_id"] = parts[3].strip()
        return result
    
    @staticmethod
    def _get_graph_access_token(refresh_token: str, client_id: str) -> Optional[str]:
        """Exchange a refresh token for an MS Graph access token.
        
        Same approach as Zeus/Hotmail007 since Lution accounts are Hotmail/Outlook.
        """
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
                                     timeout: int = 120, poll_interval: int = 3) -> Optional[str]:
        """Read Discord verification email directly via MS Graph API."""
        access_token = self._get_graph_access_token(refresh_token, client_id)
        if not access_token:
            Logger.STATUS = f"{MskColor.RED}[Lution] Failed to get Graph API access token"
            Logger.queue_log(worker_id=0)
            return None
        
        start_time = time.time()
        attempt = 0
        
        while (time.time() - start_time) < timeout:
            attempt += 1
            try:
                response = requests.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "$top": 5,
                        "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,bodyPreview,receivedDateTime"
                    },
                    timeout=15
                )
                
                if response.status_code in (401, 403):
                    access_token = self._get_graph_access_token(refresh_token, client_id)
                    if not access_token:
                        Logger.STATUS = f"{MskColor.RED}[Lution] Graph token refresh failed"
                        Logger.queue_log(worker_id=0)
                        return None
                    continue
                
                emails = response.json().get("value", [])
                
                if attempt % 3 == 0:
                    elapsed = int(time.time() - start_time)
                    Logger.STATUS = f"{MskColor.YELLOW}[Lution] Checking inbox via Graph API... ({elapsed}s elapsed)"
                    Logger.queue_log(worker_id=0)
                
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
                                final_url = resp.url
                                if "discord.com/verify" in final_url:
                                    return final_url
                                verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'>\\s]+', resp.text)
                                if verify_in_body:
                                    return verify_in_body.group(0)
                            except Exception:
                                pass
                    
                    _log_email_diagnostic("Lution-Graph", email_msg.get("subject", ""), body_html, True)
                    
            except Exception:
                pass
            
            time.sleep(poll_interval)
        
        Logger.STATUS = f"{MskColor.RED}[Lution] Graph API verification timed out after {timeout}s"
        Logger.queue_log(worker_id=0)
        return None

    def _get_verification_via_imap(self, email: str, password: str, timeout: int = 60,
                                    poll_interval: int = 3) -> Optional[str]:
        """IMAP fallback for Lution accounts without Graph API tokens."""
        import imaplib
        import email as email_module

        imap_host = "outlook.office365.com"
        start_time = time.time()
        attempt = 0

        Logger.STATUS = f"{MskColor.YELLOW}[Lution] No Graph API tokens, trying IMAP fallback ({imap_host})..."
        Logger.queue_log(worker_id=0)

        while time.time() - start_time < timeout:
            attempt += 1
            imap = None
            try:
                imap = imaplib.IMAP4_SSL(imap_host, timeout=15)
                imap.login(email, password)
                imap.select('INBOX')

                _, message_numbers = imap.search(None, 'FROM', '"noreply@discord.com"')

                if message_numbers[0]:
                    for num in reversed(message_numbers[0].split()):
                        _, msg_data = imap.fetch(num, '(RFC822)')
                        email_body = msg_data[0][1]
                        message = email_module.message_from_bytes(email_body)

                        body = ""
                        if message.is_multipart():
                            for part in message.walk():
                                if part.get_content_type() == "text/html":
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                                    break
                                elif part.get_content_type() == "text/plain" and not body:
                                    body = part.get_payload(decode=True).decode(errors='ignore')
                        else:
                            body = message.get_payload(decode=True).decode(errors='ignore')

                        url = _extract_discord_verification_url(body)
                        if url:
                            try:
                                imap.close()
                                imap.logout()
                            except Exception:
                                pass
                            return url

                        subject = message.get("Subject", "")
                        sender = message.get("From", "")
                        _log_email_diagnostic("Lution-IMAP", subject, body, "discord" in body.lower(), sender=sender)

                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

            except imaplib.IMAP4.error as e:
                err_str = str(e).lower()
                if "login" in err_str or "authentication" in err_str or "invalid" in err_str:
                    Logger.STATUS = f"{MskColor.RED}[Lution] IMAP login failed for {email}: {str(e)[:60]}"
                    Logger.queue_log(worker_id=0)
                    return None
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except (ConnectionRefusedError, OSError) as e:
                Logger.STATUS = f"{MskColor.RED}[Lution] IMAP connection error ({imap_host}): {str(e)[:60]}"
                Logger.queue_log(worker_id=0)
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except Exception:
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass

            time.sleep(poll_interval)

        Logger.STATUS = f"{MskColor.RED}[Lution] IMAP verification timed out after {timeout}s ({attempt} attempts)"
        Logger.queue_log(worker_id=0)
        return None

    def get_verification_url(self, email: str, password: str, timeout: int = 60,
                              poll_interval: int = 5, refresh_token: str = "",
                              client_id: str = "", **kwargs) -> Optional[str]:
        """Retrieve Discord verification email from Lution account.
        
        Primary method: MS Graph API (requires refresh_token + client_id from purchase).
        Fallback: IMAP login to outlook.office365.com using email + password.
        """
        if refresh_token and client_id:
            graph_result = self._get_verification_via_graph(
                refresh_token, client_id, timeout=timeout, poll_interval=poll_interval
            )
            if graph_result:
                return graph_result
            Logger.STATUS = f"{MskColor.YELLOW}[Lution] Graph API failed, trying IMAP fallback..."
            Logger.queue_log(worker_id=0)
        
        return self._get_verification_via_imap(email, password, timeout, poll_interval)


class BrowserMailVerify:
    def __init__(self, page: Page, worker_id: int) -> None:
        self.page = page
        self.worker_id = worker_id
        self.captcha_solver = None
    
    @property
    def config(self):
        """Always read fresh config from file to ensure latest values."""
        return Config.config

    def _navigate_to_discord_home(self):
        """Navigate back to Discord home page after email verification."""
        try:
            self.page.goto("https://discord.com/channels/@me", timeout=30_000, wait_until="domcontentloaded")
            time.sleep(3)
        except Exception:
            pass

    def verify_email_with_browser(self, verification_url: str, timeout: int = 60) -> bool:
        from ..WorkFlow.captcha_solver import CaptchaSolver
        
        try:
            Logger.STATUS = f"{MskColor.PRIMARY}Opening verification link..."
            Logger.queue_log(worker_id=self.worker_id)

            resolved_url = verification_url
            tracking_domains = ['click.discord.com', 'links.discord.com']
            if any(domain in verification_url for domain in tracking_domains):
                try:
                    import requests as req
                    # Follow the FULL redirect chain to get the actual final URL
                    resp = req.get(verification_url, allow_redirects=True, timeout=15, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    final_url = resp.url
                    # Check if the final URL has a verify token (in path or fragment)
                    if 'verify' in final_url or 'token=' in final_url:
                        resolved_url = final_url
                    else:
                        # Also check the response body for a verify link
                        import re as _re
                        verify_match = _re.search(r'https://discord\.com/verify[^"\'>\s]+', resp.text)
                        if verify_match:
                            resolved_url = verify_match.group(0)
                        else:
                            # Try single-hop redirect as fallback to get Location header
                            resp2 = req.get(verification_url, allow_redirects=False, timeout=15, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            location = resp2.headers.get('Location', '')
                            if location and 'discord.com' in location and '/verify' in location:
                                resolved_url = location
                            elif location and location not in ['https://discord.com', 'https://discord.com/']:
                                resolved_url = location
                except Exception:
                    pass

            self.page.goto(resolved_url, timeout=30_000, wait_until="domcontentloaded")
            time.sleep(2)
            
            current_url = self.page.url.lower()
            # Only consider it a failed redirect if we landed on the bare homepage
            # AND the URL has no verify token fragment
            is_homepage = current_url.rstrip('/') in ['https://discord.com', 'http://discord.com']
            is_login = '/login' in current_url or '/register' in current_url
            has_token = 'token=' in current_url or '/verify' in current_url
            
            if (is_homepage or is_login) and not has_token:
                Logger.STATUS = f"{MskColor.RED}Verification link redirected to Discord homepage instead of verify page"
                Logger.queue_log(worker_id=self.worker_id)
                return False
            
            button_selectors = [
                # English
                'a:has-text("Verify Email")',
                'button:has-text("Verify Email")',
                'a[href*="/verify"]',
                # German
                'button:has-text("E-Mail verifizieren")',
                'button:has-text("E-Mail bestätigen")',
                'a:has-text("E-Mail verifizieren")',
                'a:has-text("E-Mail bestätigen")',
                # French
                'button:has-text("Vérifier l\'e-mail")',
                'button:has-text("Vérifier l\'adresse e-mail")',
                'a:has-text("Vérifier l\'e-mail")',
                'a:has-text("Vérifier l\'adresse e-mail")',
                # Spanish
                'button:has-text("Verificar correo")',
                'button:has-text("Verificar email")',
                'a:has-text("Verificar correo")',
                'a:has-text("Verificar email")',
                # Portuguese
                'button:has-text("Verificar e-mail")',
                'button:has-text("Verificar email")',
                'a:has-text("Verificar e-mail")',
                # Italian
                'button:has-text("Verifica email")',
                'a:has-text("Verifica email")',
                'button:has-text("Verifica l\'email")',
                # Dutch
                'button:has-text("E-mailadres bevestigen")',
                'button:has-text("E-mail verifiëren")',
                'a:has-text("E-mailadres bevestigen")',
                # Polish
                'button:has-text("Zweryfikuj e-mail")',
                'a:has-text("Zweryfikuj e-mail")',
                # Turkish
                'button:has-text("E-postayı doğrula")',
                'a:has-text("E-postayı doğrula")',
                # Russian
                'button:has-text("Подтвердить email")',
                'a:has-text("Подтвердить email")',
                'button:has-text("Подтвердить электронную почту")',
                # Arabic
                'button:has-text("التحقق من البريد")',
                'a:has-text("التحقق من البريد")',
                # Chinese Simplified
                'button:has-text("验证邮箱")',
                'a:has-text("验证邮箱")',
                'button:has-text("验证电子邮件")',
                # Japanese
                'button:has-text("メールを確認")',
                'a:has-text("メールを確認")',
                # Korean
                'button:has-text("이메일 인증")',
                'a:has-text("이메일 인증")',
                # Swedish
                'button:has-text("Verifiera e-post")',
                'a:has-text("Verifiera e-post")',
                # Norwegian
                'button:has-text("Bekreft e-post")',
                'a:has-text("Bekreft e-post")',
                # Danish
                'button:has-text("Bekræft e-mail")',
                'a:has-text("Bekræft e-mail")',
                # Finnish
                'button:has-text("Vahvista sähköposti")',
                'a:has-text("Vahvista sähköposti")',
                # Romanian
                'button:has-text("Verificați e-mailul")',
                'a:has-text("Verificați e-mailul")',
                # Hungarian
                'button:has-text("E-mail megerősítése")',
                'a:has-text("E-mail megerősítése")',
                # Czech
                'button:has-text("Ověřit e-mail")',
                'a:has-text("Ověřit e-mail")',
                # Generic fallback – match any button/link containing "verify" (case-insensitive via :has-text)
                'button:has-text("verify")',
                'a:has-text("verify")',
            ]

            _clicked = False
            for selector in button_selectors:
                try:
                    btn = self.page.query_selector(selector)
                    if btn and btn.is_visible():
                        try:
                            btn.click(timeout=5000)
                        except Exception:
                            try:
                                btn.evaluate("el => el.click()")
                            except Exception:
                                pass
                        time.sleep(2)
                        _clicked = True
                        break
                except Exception:
                    continue

            if not _clicked:
                try:
                    _clicked = self.page.evaluate('''() => {
                        const keywords = [
                            "verify email", "e-mail verifizieren", "e-mail bestätigen",
                            "vérifier l'e-mail", "vérifier l'adresse", "verificar correo",
                            "verificar email", "verificar e-mail", "verifica email",
                            "e-mailadres bevestigen", "e-mail verifiëren", "zweryfikuj",
                            "doğrula", "подтвердить", "验证邮箱", "验证电子邮件",
                            "메일 인증", "メールを確認", "verifiera", "bekreft", "bekræft",
                            "vahvista", "verificați", "megerősítése", "ověřit"
                        ];
                        const elements = document.querySelectorAll('a, button, div[role="button"]');
                        for (const el of elements) {
                            const text = (el.innerText || el.textContent || "").trim().toLowerCase();
                            if (!text) continue;
                            const rect = el.getBoundingClientRect();
                            if (rect.width <= 0 || rect.height <= 0) continue;
                            for (const kw of keywords) {
                                if (text.includes(kw)) {
                                    el.scrollIntoView({ block: "center" });
                                    el.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }''')
                    if _clicked:
                        time.sleep(2)
                except Exception:
                    pass
            
            self.captcha_solver = CaptchaSolver(self.page, self.worker_id)
            auto_solve = self.config.get("auto_solver_captcha", True)

            VERIFIED_PHRASES = [
                "done", "verified", "email verified", "you're all set",
                "success", "verification successful", "email confirmed",
                "bestätigt", "verifiziert", "e-mail bestätigt",
                "email bestätigt", "e-mail verifiziert", "email verifiziert",
                "erfolgreich bestätigt", "e-mail-verifizierung erfolgreich",
                "e-mail-adresse bestätigt",
                "vérifié", "email vérifié", "e-mail vérifié",
                "vérification réussie", "adresse e-mail confirmée",
                "verificado", "email verificado", "correo verificado",
                "verificación exitosa", "dirección de correo verificada",
                "verificado", "e-mail verificado", "email verificado",
                "verificação concluída",
                "verificato", "email verificato", "verifica completata",
                "geverifieerd", "e-mail geverifieerd", "bevestigd",
                "zweryfikowano", "email zweryfikowany", "adres e-mail potwierdzony",
                "doğrulandı", "e-posta doğrulandı", "e-posta adresi doğrulandı",
                "подтверждено", "email подтверждён", "адрес электронной почты подтверждён",
                "確認済み", "メール確認完了",
                "확인됨", "이메일 확인 완료",
                "已验证", "邮箱已验证",
            ]

            def _is_verified(text: str) -> bool:
                t = text.lower()
                return any(phrase in t for phrase in VERIFIED_PHRASES)

            def _safe_inner_text(pg, timeout_ms: int = 4000) -> str:
                """Read body innerText with a hard timeout to prevent freezing."""
                import threading as _th
                result = [""]
                exc = [None]
                def _read():
                    try:
                        result[0] = pg.inner_text("body") if pg.query_selector("body") else ""
                    except Exception as _e:
                        exc[0] = _e
                t = _th.Thread(target=_read, daemon=True)
                t.start()
                t.join(timeout=timeout_ms / 1000.0)
                if t.is_alive():
                    return ""  # timed out — page likely frozen
                return result[0]

            def _check_url_verified(pg) -> bool:
                """Fast URL-based check — Discord redirects to /channels/@me on success."""
                try:
                    url = pg.url.lower()
                    return "/channels/@me" in url or "/app" in url or "channels/@me" in url
                except Exception:
                    return False

            start_time = time.time()

            while time.time() - start_time < timeout:
                # 1) Fast path: URL change (instant, no DOM read needed)
                if _check_url_verified(self.page):
                    Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                    Logger.queue_log(worker_id=self.worker_id)
                    return True

                # 2) Body text check with freeze-safe timeout
                page_text = _safe_inner_text(self.page)
                if _is_verified(page_text):
                    Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                    Logger.queue_log(worker_id=self.worker_id)
                    self._navigate_to_discord_home()
                    return True

                hcaptcha_frame = self.captcha_solver.find_hcaptcha_frame(self.page, timeout=3)
                if hcaptcha_frame:
                    if auto_solve:
                        Logger.STATUS = f"{MskColor.YELLOW}hCaptcha on verify page, solving..."
                        Logger.queue_log(worker_id=self.worker_id)

                        try:
                            solve_result = self.captcha_solver.solve_accessibility_hcaptcha(hcaptcha_frame)

                            if solve_result < 0:
                                if solve_result == -3.0:
                                    raise ConnectionError("VPN_BLOCKED_GROQ")
                                for _retry in range(2):
                                    if solve_result == -2.0:
                                        self.captcha_solver.refresh_captcha(hcaptcha_frame)
                                    time.sleep(1.5)
                                    hcaptcha_frame = self.captcha_solver.find_hcaptcha_frame(self.page, timeout=3)
                                    if not hcaptcha_frame:
                                        break
                                    solve_result = self.captcha_solver.solve_accessibility_hcaptcha(hcaptcha_frame)
                                    if solve_result == -3.0:
                                        raise ConnectionError("VPN_BLOCKED_GROQ")
                                    if solve_result > 0:
                                        break

                            time.sleep(1.5)

                            if _check_url_verified(self.page):
                                Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                                Logger.queue_log(worker_id=self.worker_id)
                                return True

                            page_text_after = _safe_inner_text(self.page)
                            if _is_verified(page_text_after):
                                Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                                Logger.queue_log(worker_id=self.worker_id)
                                self._navigate_to_discord_home()
                                return True

                            try:
                                if hcaptcha_frame.is_detached():
                                    Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                                    Logger.queue_log(worker_id=self.worker_id)
                                    self._navigate_to_discord_home()
                                    return True
                            except Exception:
                                pass

                        except Exception as e:
                            Logger.STATUS = f"{MskColor.RED}Error solving captcha: {e}"
                            Logger.queue_log(worker_id=self.worker_id)
                            return False
                    else:
                        Logger.STATUS = f"{MskColor.YELLOW}hCaptcha on verify page, waiting for manual solve..."
                        Logger.queue_log(worker_id=self.worker_id)

                        self.captcha_solver.wait_for_captcha_solved(hcaptcha_frame, timeout=120)
                        time.sleep(1.5)

                        if _check_url_verified(self.page):
                            Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                            Logger.queue_log(worker_id=self.worker_id)
                            return True

                        page_text_after = _safe_inner_text(self.page)
                        if _is_verified(page_text_after):
                            Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                            Logger.queue_log(worker_id=self.worker_id)
                            self._navigate_to_discord_home()
                            return True

                        try:
                            if hcaptcha_frame.is_detached():
                                Logger.STATUS = f"{MskColor.GREEN}Email Verified!"
                                Logger.queue_log(worker_id=self.worker_id)
                                self._navigate_to_discord_home()
                                return True
                        except Exception:
                            pass

                time.sleep(0.25)

            Logger.STATUS = f"{MskColor.RED}Verification timeout"
            Logger.queue_log(worker_id=self.worker_id)
            return False

        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Error during browser verification: {e}"
            Logger.queue_log(worker_id=self.worker_id)
            return False

    def _find_hcaptcha_frame(self) -> Optional[Frame]:
        try:
            for iframe in self.page.query_selector_all("iframe"):
                src = iframe.get_attribute("src")
                if src and "hcaptcha.com" in src:
                    frame = iframe.content_frame()
                    if frame:
                        try:
                            checkbox = frame.query_selector("div#checkbox")
                            if checkbox and checkbox.get_attribute("aria-checked") == "false":
                                checkbox.click()
                                time.sleep(1)
                        except Exception:
                            pass
                        
                        try:
                            if frame.query_selector("#menu-info"):
                                return frame
                        except Exception:
                            pass
        except Exception:
            pass
        return None


class MailVerify:
    def __init__(self, proxy_dict: Optional[Dict[str, str]] = None) -> None:
        self.session: tls_client.Session = tls_client.Session(
            client_identifier="chrome_120",
            random_tls_extension_order=True
        )
        if proxy_dict:
            self.proxy_url: str = Utils.proxy_dict_to_url(proxy_dict=proxy_dict)
            self.session.proxies = {'http': self.proxy_url, 'https': self.proxy_url}

    def get_verify_token(self, upn: str) -> Optional[str]:
        headers: Dict[str, str] = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'en-US,en;q=0.9,de-DE;q=0.8,de;q=0.7,en-DE;q=0.6',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        }

        try:
            response = self.session.get(
                'https://click.discord.com/ls/click',
                params={'upn': upn},
                headers=headers,
                allow_redirects=False
            )
            location = response.headers.get("Location")
            if location:
                fragment = urlparse(location).fragment
                if fragment and "token=" in fragment:
                    return fragment.split("token=")[-1]
        except Exception as e:
            pass
        return None

    def verify_token(self, token: str, upn: str) -> Tuple[Optional[str], bool]:
        headers = HeaderGenerator().generate_headers(token)
        verify_token = self.get_verify_token(upn)
        if not verify_token:
            return None, False

        try:
            response = self.session.post(
                'https://discord.com/api/v9/auth/verify',
                headers=headers,
                json={'token': verify_token}
            )
            if 200 <= response.status_code < 300:
                return response.json().get("token"), True
        except Exception as e:
            print(f"Error verifying token: {e}")

        return None, False
