"""CyberTemp email provider implementation."""
import random
import time
from typing import Optional, Callable, List

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError, EmailAuthError


class CyberTempProvider(IEmailProvider):
    """CyberTemp (cybertemp API) email provider."""

    def __init__(self, api_key: str = "", domain: str = "random") -> None:
        self.api_key = api_key
        self.domain = domain
        self._client = None

    @property
    def name(self) -> str:
        return "CyberTemp"

    def _get_client(self):
        if self._client is None:
            from cybertemp import CyberTemp
            free_key = "free"
            if self.api_key and self.api_key.strip().lower() != "free" and len(self.api_key.strip()) > 10:
                free_key = self.api_key
            self._client = CyberTemp(api_key=free_key)
        return self._client

    def get_domains(self, domain_type: Optional[str] = None) -> List[str]:
        """Get available domains from CyberTemp API."""
        try:
            client = self._get_client()
            all_domains = []
            offset = 0
            limit = 100
            while True:
                kwargs = {"limit": limit, "offset": offset}
                if domain_type:
                    kwargs["type"] = domain_type
                result = client.get_domains(**kwargs)
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

            cleaned = [str(d).strip() for d in all_domains if isinstance(d, str) and "." in d]
            return cleaned if cleaned else []
        except Exception:
            return []

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Utils.utils import Utils
        
        domain = self.domain
        if not domain or domain == "random":
            domains = self.get_domains(domain_type="discord")
            domain = random.choice(domains) if domains else Utils.get_domain()

        username = Utils.sanitize_email_local(Utils.random_string())
        email_address = f"{username}@{domain}"
        password = Utils.random_password()

        try:
            client = self._get_client()
            client.get_email_content(email_address, max_retries=1, delay_between_retries=1.0)
        except Exception as e:
            Logger.STATUS = f"{MskColor.YELLOW}[CyberTemp] create_account note: {str(e)[:60]}"
            Logger.queue_log(worker_id=worker_id)

        Logger.STATUS = f"{MskColor.PRIMARY}CyberTemp email created: {email_address}"
        Logger.queue_log(worker_id=worker_id)

        return EmailAccount(
            email=email_address,
            password=password,
            provider_name=self.name,
        )

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
        from ..Helper.mail import _extract_discord_verification_url, _log_email_diagnostic
        
        client = self._get_client()
        start_time = time.time()
        consecutive_api_failures = 0
        max_api_failures = 3

        while True:
            if stop_signal and stop_signal():
                return None

            try:
                emails = client.get_email_content(
                    email, max_retries=1, delay_between_retries=1.0
                )

                if emails is None:
                    consecutive_api_failures += 1
                    if consecutive_api_failures >= max_api_failures:
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
                if stop_signal and stop_signal():
                    return None
                time.sleep(0.3)
