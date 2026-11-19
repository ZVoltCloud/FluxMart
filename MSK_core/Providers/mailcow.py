"""Mailcow email provider implementation."""
import time
from typing import Optional, Callable, List

import requests

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError


class MailcowProvider(IEmailProvider):
    """Mailcow self-hosted email provider."""

    def __init__(self, host_url: str = "", api_key: str = "", domain: str = "") -> None:
        self.host_url = host_url.rstrip('/')
        if self.host_url and not self.host_url.startswith("http"):
            self.host_url = f"https://{self.host_url}"
        self.api_key = api_key
        self.domain = domain
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-Key': api_key,
            'Content-Type': 'application/json'
        })

    @property
    def name(self) -> str:
        return "Mailcow"

    def get_domains(self) -> List[str]:
        try:
            response = self.session.get(f"{self.host_url}/api/v1/get/domain/all")
            if response.status_code == 200:
                domains = response.json()
                return [d.get('domain_name', '') for d in domains if d.get('active', 0) == 1]
        except Exception:
            pass
        return []

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Utils.utils import Utils

        domain = self.domain
        if not domain:
            Logger.STATUS = f"{MskColor.RED}Mailcow domain not configured."
            Logger.queue_log(worker_id=worker_id)
            return None

        username = Utils.sanitize_email_local(Utils.random_string())
        email_address = f"{username}@{domain}"
        password = Utils.random_password()

        try:
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
                    Logger.STATUS = f"{MskColor.PRIMARY}Mailcow email created: {email_address}"
                    Logger.queue_log(worker_id=worker_id)
                    return EmailAccount(email=email_address, password=password, provider_name=self.name)
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}Mailcow error: {str(e)[:60]}"
            Logger.queue_log(worker_id=worker_id)

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
        """Retrieve Discord verification email via IMAP."""
        import imaplib
        import email as email_module
        from urllib.parse import urlparse
        from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic

        if not timeout or timeout <= 0:
            timeout = 120

        start_time = time.time()

        imap_host = self.host_url
        if imap_host:
            parsed = urlparse(imap_host)
            imap_host = parsed.hostname or parsed.path

        if not imap_host:
            return None

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

                        subject = message.get("Subject", "")
                        sender = message.get("From", "")
                        _log_email_diagnostic("Mailcow", subject, body, "discord" in body.lower(), sender=sender)

                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

            except imaplib.IMAP4.error:
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass
            except ConnectionRefusedError:
                return None
            except OSError:
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
