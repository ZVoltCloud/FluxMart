"""Zeus email provider implementation."""
import re
import time
from typing import Optional, Callable, Dict, List

import requests

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError, EmailStockExhausted


class ZeusProvider(IEmailProvider):
    """Zeus (api.zeus-x.ru) email provider."""

    ACCOUNT_CODES = {
        "Hotmail New": "HOTMAIL",
        "Outlook New": "OUTLOOK",
        "Hotmail Trusted [Graph API]": "HOTMAIL_TRUSTED_GRAPH_API",
        "Outlook Trusted [Graph API]": "OUTLOOK_TRUSTED_GRAPH_API",
        "Hotmail Trusted [IMAP/POP3]": "HOTMAIL_TRUSTED",
        "Outlook Trusted [IMAP/POP3]": "OUTLOOK_TRUSTED",
    }

    def __init__(self, api_key: str = "", account_type: str = "HOTMAIL") -> None:
        self.api_key = api_key
        self.account_code = self.ACCOUNT_CODES.get(account_type, account_type)
        self.base_url = "https://api.zeus-x.ru"
        self.session = requests.Session()

    @property
    def name(self) -> str:
        return "Zeus"

    def check_balance(self) -> Optional[float]:
        try:
            resp = self.session.get(
                f"{self.base_url}/balance",
                params={"apikey": self.api_key},
                timeout=15,
                verify=False
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    return 0.0
                code = data.get("Code", data.get("code", None))
                if code == 0 or code == "0":
                    bal = data.get("Data", data.get("data", {}))
                    if isinstance(bal, dict):
                        bal = bal.get("Balance", bal.get("balance", 0))
                    return float(bal) if bal is not None else 0.0
                if code is None:
                    return 0.0
            elif resp.status_code in (401, 403):
                return None
            else:
                return 0.0
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_account_fields(d: dict) -> Optional[Dict[str, str]]:
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

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Helper.mail import _save_account_data_to_file

        try:
            resp = self.session.get(
                f"{self.base_url}/purchase",
                params={
                    "apikey": self.api_key,
                    "accountcode": self.account_code,
                    "quantity": 1
                },
                timeout=30,
                verify=False
            )

            if resp.status_code != 200:
                raise EmailCreationError(f"Zeus HTTP {resp.status_code}: {resp.text[:80]}")

            data = resp.json()

            if not isinstance(data, dict):
                raise EmailCreationError(f"Zeus unexpected response: {str(data)[:80]}")

            code = data.get("Code")

            if code == 0 or code == "0":
                purchase_data = data.get("Data")
                if not purchase_data:
                    raise EmailStockExhausted("Zeus: purchase succeeded but no data returned (out of stock?)")

                accounts = None
                if isinstance(purchase_data, dict):
                    for key in ["Accounts", "accounts", "Items", "items", "Data", "data"]:
                        if key in purchase_data and isinstance(purchase_data[key], list):
                            accounts = purchase_data[key]
                            break

                    if accounts is None:
                        result = self._extract_account_fields(purchase_data)
                        if result:
                            _save_account_data_to_file(result, "zeus")
                            return EmailAccount(
                                email=result["email"], password=result["password"],
                                refresh_token=result.get("refresh_token", ""),
                                client_id=result.get("client_id", ""),
                                provider_name=self.name,
                            )
                        for val in purchase_data.values():
                            if isinstance(val, str) and ":" in val and "@" in val:
                                parts = val.split(":", 1)
                                r = {"email": parts[0].strip(), "password": parts[1].strip()}
                                _save_account_data_to_file(r, "zeus")
                                return EmailAccount(email=r["email"], password=r["password"], provider_name=self.name)
                        raise EmailCreationError(f"Zeus: can't find accounts in response: {str(purchase_data)[:100]}")

                elif isinstance(purchase_data, list):
                    accounts = purchase_data
                elif isinstance(purchase_data, str) and ":" in purchase_data:
                    parts = purchase_data.split(":", 1)
                    return EmailAccount(email=parts[0].strip(), password=parts[1].strip(), provider_name=self.name)
                else:
                    raise EmailCreationError(f"Zeus: unexpected Data type: {str(purchase_data)[:80]}")

                if accounts and len(accounts) > 0:
                    acc = accounts[0]
                    if isinstance(acc, dict):
                        result = self._extract_account_fields(acc)
                        if result:
                            _save_account_data_to_file(result, "zeus")
                            return EmailAccount(
                                email=result["email"], password=result["password"],
                                refresh_token=result.get("refresh_token", ""),
                                client_id=result.get("client_id", ""),
                                provider_name=self.name,
                            )
                    acc_str = str(acc)
                    if ":" in acc_str:
                        parts = acc_str.split(":", 1)
                        r = {"email": parts[0].strip(), "password": parts[1].strip()}
                        _save_account_data_to_file(r, "zeus")
                        return EmailAccount(email=r["email"], password=r["password"], provider_name=self.name)
                    raise EmailCreationError(f"Zeus: can't parse account: {acc_str[:60]}")
                else:
                    raise EmailStockExhausted("Zeus: empty accounts list returned")
            else:
                error_msg = data.get("Message") or data.get("message") or f"error code {code}"
                err_lower = error_msg.lower()
                if any(kw in err_lower for kw in ['insufficient', 'stock', 'quantity']):
                    raise EmailStockExhausted(f"Zeus: {error_msg}")
                raise EmailCreationError(f"Zeus: {error_msg}")

        except (EmailCreationError, EmailStockExhausted):
            raise
        except requests.exceptions.RequestException as e:
            raise EmailCreationError(f"Zeus connection error: {str(e)[:60]}")

    @staticmethod
    def _get_access_token(refresh_token: str, client_id: str) -> Optional[str]:
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

    def _get_verification_via_graph(self, refresh_token: str, client_id: str,
                                     timeout: int = 120, poll_interval: int = 3,
                                     stop_signal: Optional[Callable[[], bool]] = None) -> Optional[str]:
        from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic

        access_token = self._get_access_token(refresh_token, client_id)
        if not access_token:
            return None

        start_time = time.time()

        while time.time() - start_time < timeout:
            if stop_signal and stop_signal():
                return None
            try:
                headers = {"Authorization": f"Bearer {access_token}"}
                resp = requests.get(
                    "https://graph.microsoft.com/v1.0/me/messages",
                    headers=headers,
                    params={
                        "$top": 10,
                        "$orderby": "receivedDateTime desc",
                        "$select": "subject,body,from,bodyPreview,receivedDateTime"
                    },
                    timeout=15
                )

                if resp.status_code in (401, 403):
                    access_token = self._get_access_token(refresh_token, client_id)
                    if not access_token:
                        break
                    continue

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

                            # Follow click.discord.com redirect links
                            click_patterns = [
                                re.compile(r'https://click\.discord\.com/ls/click\?[^"\'>\\s]+'),
                                re.compile(r'https://links\.discord\.com[^"\'>\\s]+')
                            ]
                            for pat in click_patterns:
                                for m in pat.finditer(body_content):
                                    click_url = m.group(0)
                                    try:
                                        click_resp = requests.get(click_url, allow_redirects=True, timeout=15, verify=False)
                                        final_url = click_resp.url
                                        if "discord.com/verify" in final_url:
                                            return final_url
                                        verify_in_body = re.search(r'https://discord\.com/verify\?token=[^"\'>\\s]+', click_resp.text)
                                        if verify_in_body:
                                            return verify_in_body.group(0)
                                    except Exception:
                                        pass

                            _log_email_diagnostic("Zeus-Graph", msg.get("subject", ""), body_content, True)
            except Exception:
                pass

            if timeout > 0 and time.time() - start_time > timeout:
                return None

            time.sleep(poll_interval)

        return None

    def _get_verification_via_imap(self, email: str, password: str, timeout: int = 60,
                                    poll_interval: int = 3,
                                    stop_signal: Optional[Callable[[], bool]] = None) -> Optional[str]:
        import imaplib
        import email as email_module
        from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic

        imap_host = "outlook.office365.com"
        start_time = time.time()

        while time.time() - start_time < timeout:
            if stop_signal and stop_signal():
                return None

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

                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

            except imaplib.IMAP4.error as e:
                err_str = str(e).lower()
                if "login" in err_str or "authentication" in err_str or "invalid" in err_str:
                    return None
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except (ConnectionRefusedError, OSError):
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
        if not refresh_token or not client_id:
            return self._get_verification_via_imap(email, password, timeout, poll_interval, stop_signal)

        start_time = time.time()
        graph_result = self._get_verification_via_graph(
            refresh_token, client_id, timeout=timeout, poll_interval=poll_interval, stop_signal=stop_signal
        )
        if graph_result:
            return graph_result

        remaining = max(30, timeout - int(time.time() - start_time))
        return self._get_verification_via_imap(email, password, remaining, poll_interval, stop_signal)
