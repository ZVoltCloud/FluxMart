"""DuckMail email provider implementation."""
import random
import time
from typing import Optional, Callable, List

import requests

from .base import IEmailProvider, EmailAccount
from ..Utils.logger import Logger
from ..MskColors.color import MskColor
from ..Exceptions import EmailCreationError


class DuckMailProvider(IEmailProvider):
    """DuckMail (duckmail.sbs) email provider."""

    def __init__(self, api_key: str = "", domain: str = "") -> None:
        self.api_key = api_key
        self.domain = domain
        self.api_url = "https://api.duckmail.sbs"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.token = None
        if self.api_key:
            self.session.headers.update({'Authorization': f'Bearer {self.api_key}'})

    @property
    def name(self) -> str:
        return "DuckMail"

    def get_domains(self, domain_type: Optional[str] = None) -> List[str]:
        try:
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
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
            resp = self.session.post(f"{self.api_url}/token", json={"address": email, "password": password})
            if resp.status_code == 200:
                self.token = resp.json().get('token')
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
                return True
        except Exception:
            pass
        return False

    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        from ..Utils.utils import Utils

        domain = self.domain
        if not domain:
            domains = self.get_domains() or []
            domain = random.choice(domains) if domains else ""
        
        if not domain:
            Logger.STATUS = f"{MskColor.RED}DuckMail: no domain available"
            Logger.queue_log(worker_id=worker_id)
            return None

        username = Utils.sanitize_email_local(Utils.random_string())
        email_address = f"{username}@{domain}"
        password = Utils.random_password()

        try:
            payload = {"address": email_address, "password": password, "expiresIn": 0}
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            resp = self.session.post(f"{self.api_url}/accounts", json=payload, headers=headers)
            if resp.status_code in (201, 409):
                self.authenticate(email_address, password)
        except Exception as e:
            Logger.STATUS = f"{MskColor.RED}DuckMail error: {str(e)[:60]}"
            Logger.queue_log(worker_id=worker_id)

        Logger.STATUS = f"{MskColor.PRIMARY}DuckMail email created: {email_address}"
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
        from ..Helper.mail import _extract_discord_verification_url

        start_time = time.time()
        self.authenticate(email, password)

        while True:
            if stop_signal and stop_signal():
                return None

            try:
                resp = self.session.get(f"{self.api_url}/messages")
                if resp.status_code == 200:
                    data = resp.json()
                    members = data.get('hydra:member', [])
                    for msg in members:
                        msg_id = msg.get('id')
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
                                if not body:
                                    continue
                                url = _extract_discord_verification_url(body)
                                if url:
                                    return url
            except Exception:
                pass

            if timeout > 0 and time.time() - start_time > timeout:
                return None
            time.sleep(poll_interval)
