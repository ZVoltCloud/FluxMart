"""Lution email provider implementation."""
import re
import time
from typing import Optional, Callable, Dict

import requests

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError, EmailStockExhausted


class LutionProvider(IEmailProvider):
    """Lution (lution.ee) V2 email provider."""

    BASE_URL = "https://api.lution.ee/v2"

    CATEGORY_CODES = {
        "Hotmail": "hotmail",
        "Outlook": "outlook",
        "Hotmail Trusted (IMAP,GRAPH)": "hotmail.trusted",
        "Outlook Trusted (IMAP,GRAPH)": "outlook.trusted",
        "Hotmail Trusted (GRAPH)": "hotmail.trusted.graph",
        "Outlook Trusted (GRAPH)": "outlook.trusted.graph",
        "Hotmail SMTP": "hotmail.smtp",
        "Outlook SMTP": "outlook.smtp",
    }

    _LEGACY_CODE_MAP = {
        "hotmail_trusted": "hotmail.trusted",
        "outlook_trusted": "outlook.trusted",
        "hotmail_trusted_graph": "hotmail.trusted.graph",
        "outlook_trusted_graph": "outlook.trusted.graph",
    }

    def __init__(self, api_key: str = "", category: str = "hotmail.trusted.graph") -> None:
        self.api_key = api_key
        resolved = self.CATEGORY_CODES.get(category, category)
        resolved = self._LEGACY_CODE_MAP.get(resolved, resolved)
        self.category = resolved
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    @property
    def name(self) -> str:
        return "Lution"

    def _params(self, extra=None):
        p = {"apikey": self.api_key}
        if extra:
            p.update(extra)
        return p

    def check_balance(self) -> Optional[float]:
        try:
            resp = self.session.get(f"{self.BASE_URL}/user/me", params=self._params(), timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("data", {}).get("balance")
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_dict_account(acc: dict) -> Optional[Dict[str, str]]:
        email = acc.get("email", "").strip()
        password = acc.get("password", "").strip()
        if not email or not password:
            return None
        result = {"email": email, "password": password}
        rt = acc.get("graph_refresh_token") or acc.get("refresh_token") or acc.get("token") or ""
        if rt:
            result["refresh_token"] = str(rt).strip()
        cid = acc.get("thunderbird_client_id") or acc.get("client_id") or ""
        if cid:
            result["client_id"] = str(cid).strip()
        return result

    @staticmethod
    def _parse_account_string(account_str: str) -> Optional[Dict[str, str]]:
        if not isinstance(account_str, str):
            return None
        parts = account_str.split(":")
        if len(parts) < 2:
            return None
        result = {"email": parts[0].strip(), "password": parts[1].strip()}
        if len(parts) >= 3 and parts[2].strip():
            remainder = ":".join(parts[2:])
            uuid_pattern = re.compile(r'^[0-9a-fA-F\-]{32,36}$')
            sub_parts = remainder.split(":")
            if len(sub_parts) >= 2 and uuid_pattern.match(sub_parts[-1]):
                result["client_id"] = sub_parts[-1].strip()
                result["refresh_token"] = ":".join(sub_parts[:-1]).strip()
            else:
                result["refresh_token"] = remainder.strip()
                if len(parts) >= 4 and parts[3].strip():
                    result["client_id"] = parts[3].strip()
        return result

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Helper.mail import _save_account_data_to_file

        try:
            resp = self.session.post(
                f"{self.BASE_URL}/email/buy",
                params=self._params(),
                json={"category": self.category, "quantity": 1},
                timeout=30
            )

            if resp.status_code != 200:
                raise EmailCreationError(f"Lution HTTP {resp.status_code}: {resp.text[:120]}")

            data = resp.json()

            if not isinstance(data, dict) or not data.get("success"):
                error_msg = data.get("message") or data.get("msg") or data.get("error") or "unknown"
                raise EmailCreationError(f"Lution: {error_msg}")

            response_data = data.get("data", {})

            # Format 1: list of account dicts
            if isinstance(response_data, list) and len(response_data) > 0:
                acc = response_data[0]
                if isinstance(acc, dict):
                    result = self._extract_dict_account(acc)
                    if result:
                        _save_account_data_to_file(result, "lution")
                        Logger.STATUS = f"{MskColor.PRIMARY}Lution account purchased: {result['email']}"
                        Logger.queue_log(worker_id=worker_id)
                        return EmailAccount(
                            email=result["email"], password=result["password"],
                            refresh_token=result.get("refresh_token", ""),
                            client_id=result.get("client_id", ""),
                            provider_name=self.name,
                        )
                if isinstance(acc, str):
                    result = self._parse_account_string(acc)
                    if result:
                        _save_account_data_to_file(result, "lution")
                        return EmailAccount(
                            email=result["email"], password=result["password"],
                            refresh_token=result.get("refresh_token", ""),
                            client_id=result.get("client_id", ""),
                            provider_name=self.name,
                        )

            # Format 2: dict with list/string fields
            if isinstance(response_data, dict):
                for key in ["emails", "list", "purchase"]:
                    sub = response_data.get(key)
                    if key == "list" and isinstance(sub, str):
                        lines = [ln.strip() for ln in sub.strip().split("\n") if ln.strip()]
                        if lines:
                            result = self._parse_account_string(lines[0])
                            if result:
                                _save_account_data_to_file(result, "lution")
                                return EmailAccount(
                                    email=result["email"], password=result["password"],
                                    refresh_token=result.get("refresh_token", ""),
                                    client_id=result.get("client_id", ""),
                                    provider_name=self.name,
                                )
                    elif isinstance(sub, list) and len(sub) > 0:
                        acc = sub[0]
                        if isinstance(acc, dict):
                            result = self._extract_dict_account(acc)
                            if result:
                                _save_account_data_to_file(result, "lution")
                                return EmailAccount(
                                    email=result["email"], password=result["password"],
                                    refresh_token=result.get("refresh_token", ""),
                                    client_id=result.get("client_id", ""),
                                    provider_name=self.name,
                                )
                    elif isinstance(sub, dict):
                        accounts_raw = sub.get("accounts", [])
                        if accounts_raw and len(accounts_raw) > 0:
                            result = self._parse_account_string(accounts_raw[0])
                            if result:
                                _save_account_data_to_file(result, "lution")
                                return EmailAccount(
                                    email=result["email"], password=result["password"],
                                    refresh_token=result.get("refresh_token", ""),
                                    client_id=result.get("client_id", ""),
                                    provider_name=self.name,
                                )

            raise EmailCreationError(f"Lution: could not parse response: {str(response_data)[:120]}")

        except (EmailCreationError, EmailStockExhausted):
            raise
        except requests.exceptions.RequestException as e:
            raise EmailCreationError(f"Lution connection error: {str(e)[:60]}")

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
                    "client_id": cid, "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "scope": "https://graph.microsoft.com/.default",
                },
                timeout=30, verify=False
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
                    "client_id": cid, "grant_type": "refresh_token",
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

                    _log_email_diagnostic("Lution-Graph", email_msg.get("subject", ""), body_html, True)

            except Exception:
                pass

            time.sleep(poll_interval)

        return None

    def _get_verification_via_imap(self, email: str, password: str, timeout: int = 60,
                                    poll_interval: int = 3,
                                    stop_signal: Optional[Callable[[], bool]] = None) -> Optional[str]:
        import imaplib
        import email as email_module
        from ..Helper.mail import _extract_discord_verification_url

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
                if "login" in err_str or "authentication" in err_str:
                    return None
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
        if stop_signal and stop_signal():
            return None

        if refresh_token and client_id:
            graph_result = self._get_verification_via_graph(
                refresh_token, client_id, timeout=timeout, poll_interval=poll_interval, stop_signal=stop_signal
            )
            if graph_result:
                return graph_result

        return self._get_verification_via_imap(email, password, timeout, poll_interval, stop_signal)
