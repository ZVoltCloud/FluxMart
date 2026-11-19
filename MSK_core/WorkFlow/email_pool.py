"""Email Buffer Pool — prepares email accounts in the background for zero-wait
generation.

Two distinct provider styles are supported:

  • Paid-stock providers (Zeus / Hotmail007 / Lution): we *purchase* a ready-made
    Hotmail or Outlook account from their stock. Subject to "no stock" errors
    and Multi Buy fallback.

  • API providers (Mailcow / CyberTemp): we *create* (or just generate) a fresh
    address on a domain you control. No stock, no purchase.

Fast Mails: a background thread keeps a queue of prepared accounts so worker
threads never block.

Multi Buy: when a paid-stock provider is out of stock, falls back to the next
paid-stock provider in the configured order.
"""

import queue
import random
import string
import threading
import time
from typing import Optional, Dict, List, Tuple

from ..MskColors.color import MskColor
from ..Utils.logger import Logger
from ..Utils.utils import Config


def _random_local_part(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _random_password(length: int = 14) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    pw = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice("!@#$%"),
    ]
    pw += random.choices(chars, k=length - 4)
    random.shuffle(pw)
    return "".join(pw)


class EmailPool:
    """Shared thread-safe pool of pre-purchased email accounts.
    
    Usage:
        pool = EmailPool.instance()
        pool.start(config, target_count=100)
        ...
        account = pool.get_email(worker_id=0, timeout=120)
        # account = {email, password, refresh_token, client_id, provider}
        ...
        pool.stop()
    """
    
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def instance(cls) -> "EmailPool":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance
    
    @classmethod
    def reset(cls):
        with cls._lock:
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None
    
    HOTMAIL_PROVIDERS = ("zeus", "hotmail007", "lution")

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._config: Dict = {}
        self._target_count: int = 0
        self._total_bought: int = 0
        self._buffer_size: int = 3
        self._running = False
    
    @property
    def available(self) -> int:
        return self._queue.qsize()

    def _is_hotmail_pool(self) -> bool:
        """True when the active email provider is a paid Hotmail-style stock
        provider (Zeus / Hotmail007 / Lution). Used to gate verbose pool logs
        so Mailcow / CyberTemp users don't see misleading 'Pool →' lines.
        """
        try:
            config = Config.config or self._config or {}
        except Exception:
            config = self._config or {}

        multi_buy = config.get("multi_buy", {}) or {}
        if multi_buy.get("enabled", False):
            for p in (multi_buy.get("providers") or []):
                if str(p).lower() in self.HOTMAIL_PROVIDERS:
                    return True
            return False

        eps = config.get("email_providers", {}) or {}
        for name in self.HOTMAIL_PROVIDERS:
            if eps.get(name, {}).get("enabled", False):
                return True
        return False

    @staticmethod
    def _is_hotmail_account(account: Optional[Dict[str, str]]) -> bool:
        if not account:
            return False
        return str(account.get("provider", "")).lower() in (
            "zeus", "hotmail007", "lution"
        )
    
    def start(self, config: Dict, target_count: int):
        """Start the background pre-buying thread.
        
        Args:
            config: Full application config dict
            target_count: Total tokens the user wants to generate
        """
        if self._running:
            return
        
        self._config = config
        self._target_count = target_count
        self._total_bought = 0
        self._stop_event.clear()
        
        fast_mails = config.get("fast_mails", {})
        self._buffer_size = max(2, fast_mails.get("buffer_size", 3))
        
        initial_batch = max(3, min(self._buffer_size * 2, int(target_count * 0.10)))
        
        self._running = True
        self._thread = threading.Thread(
            target=self._buy_loop,
            args=(initial_batch,),
            daemon=True,
            name="EmailPool-buyer"
        )
        self._thread.start()
    
    def stop(self):
        """Stop the background buying thread and drain the queue."""
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
    
    def get_email(self, worker_id: int = 0, timeout: float = 120) -> Optional[Dict[str, str]]:
        """Get a pre-purchased email from the pool. Blocks until available.
        
        Returns dict: {email, password, refresh_token, client_id, provider}
        """
        try:
            account = self._queue.get(timeout=timeout)
            if self._is_hotmail_account(account):
                Logger.STATUS = (
                    f"{MskColor.PRIMARY}Pool → {account['email'][:25]}... "
                    f"(remaining: {self.available})"
                )
                Logger.queue_log(worker_id=worker_id)
            return account
        except queue.Empty:
            Logger.STATUS = f"{MskColor.RED}Email pool empty after {timeout}s wait"
            Logger.queue_log(worker_id=worker_id)
            return None
    
    def _buy_loop(self, initial_batch: int):
        """Background thread: keeps the queue filled."""
        bought = 0
        for _ in range(initial_batch):
            if self._stop_event.is_set():
                return
            account = self._buy_one_with_fallback()
            if account:
                self._queue.put(account)
                bought += 1
                self._total_bought += 1
            else:
                time.sleep(2)
        
        if bought > 0 and self._is_hotmail_pool():
            Logger.STATUS = (
                f"{MskColor.GREEN}Prepared {bought} emails "
                f"(pool: {self.available})"
            )
            Logger.queue_log(worker_id=0)
        
        backoff = 1
        while not self._stop_event.is_set():
            if self._total_bought >= self._target_count:
                time.sleep(2)
                continue
            
            if self.available < self._buffer_size:
                batch_target = min(self._buffer_size, self._target_count - self._total_bought)
                batch_bought = 0
                
                for _ in range(max(1, batch_target)):
                    if self._stop_event.is_set():
                        return
                    if self._total_bought >= self._target_count:
                        break
                    
                    account = self._buy_one_with_fallback()
                    if account:
                        self._queue.put(account)
                        batch_bought += 1
                        self._total_bought += 1
                        backoff = 1
                    else:
                        time.sleep(min(backoff, 30))
                        backoff = min(backoff * 2, 30)
                        break
                
                if batch_bought > 0 and self._is_hotmail_pool():
                    Logger.STATUS = (
                        f"{MskColor.GREEN}Refilled +{batch_bought} emails "
                        f"(pool: {self.available}, total: "
                        f"{self._total_bought}/{self._target_count})"
                    )
                    Logger.queue_log(worker_id=0)
            else:
                time.sleep(1)
    
    def _buy_one_with_fallback(self) -> Optional[Dict[str, str]]:
        """Buy one email account, with Multi Buy fallback across providers.
        
        Tries enabled providers in order. If primary fails (stock/error),
        falls back to the next provider.
        """
        config = Config.config
        multi_buy = config.get("multi_buy", {})
        multi_buy_enabled = multi_buy.get("enabled", False)
        
        if multi_buy_enabled:
            providers = self._get_multi_buy_providers(config)
        else:
            providers = self._get_primary_provider(config)
        
        if not providers:
            Logger.STATUS = f"{MskColor.RED}No email provider configured"
            Logger.queue_log(worker_id=0)
            return None
        
        for provider_name, buy_func in providers:
            if self._stop_event.is_set():
                return None
            try:
                account = buy_func()
                if account:
                    account["provider"] = provider_name
                    return account
            except Exception as e:
                err_str = str(e).lower()
                is_stock_error = any(kw in err_str for kw in ['stock', 'insufficient', 'quantity', 'buy error'])
                
                if is_stock_error and multi_buy_enabled and len(providers) > 1:
                    Logger.STATUS = f"{MskColor.YELLOW}{provider_name} no stock, trying next..."
                    Logger.queue_log(worker_id=0)
                    continue
                elif is_stock_error:
                    Logger.STATUS = f"{MskColor.RED}{provider_name} no stock"
                    Logger.queue_log(worker_id=0)
                    return None
                else:
                    Logger.STATUS = f"{MskColor.RED}{provider_name} error: {str(e)[:50]}"
                    Logger.queue_log(worker_id=0)
                    return None
        
        return None
    
    def _get_primary_provider(self, config: Dict) -> List[Tuple[str, callable]]:
        """Get the single active email provider (for non-Multi Buy mode).

        Order matches the provider list users typically prefer:
          paid-stock first (Zeus / Hotmail007 / Lution), then self-hosted
          (Mailcow), then free temp-mail (CyberTemp).
        """
        email_providers = config.get("email_providers", {})

        if email_providers.get("zeus", {}).get("enabled", False):
            z = email_providers["zeus"]
            return [("Zeus", lambda: self._buy_zeus(z))]

        if email_providers.get("hotmail007", {}).get("enabled", False):
            h = email_providers["hotmail007"]
            return [("Hotmail007", lambda: self._buy_hotmail007(h))]

        if email_providers.get("lution", {}).get("enabled", False):
            l = email_providers["lution"]
            return [("Lution", lambda: self._buy_lution(l))]

        if email_providers.get("mailcow", {}).get("enabled", False):
            m = email_providers["mailcow"]
            return [("Mailcow", lambda: self._buy_mailcow(m))]

        if email_providers.get("duckmail", {}).get("enabled", False):
            d = email_providers["duckmail"]
            dm_key = d.get("api_key", "")
            return [("DuckMail", lambda: self._buy_duckmail(dm_key, d))]

        if email_providers.get("cybertemp", {}).get("enabled", False):
            c = email_providers["cybertemp"]
            ct_key = c.get("api_key", "") or config.get("cybertemp_api_key", "")
            return [("CyberTemp", lambda: self._buy_cybertemp(ct_key, c))]

        return []
    
    def _get_multi_buy_providers(self, config: Dict) -> List[Tuple[str, callable]]:
        """Get ordered list of providers for Multi Buy fallback.
        
        Uses the multi_buy.providers config to determine which providers
        are in the fallback chain and their order.
        """
        multi_buy = config.get("multi_buy", {})
        provider_list = multi_buy.get("providers", ["zeus", "hotmail007", "lution"])
        email_providers = config.get("email_providers", {})
        
        result = []
        for p in provider_list:
            p_lower = p.lower()
            if p_lower == "zeus":
                z = email_providers.get("zeus", {})
                if z.get("api_key"):
                    result.append(("Zeus", lambda z=z: self._buy_zeus(z)))
            elif p_lower == "hotmail007":
                h = email_providers.get("hotmail007", {})
                if h.get("api_key"):
                    result.append(("Hotmail007", lambda h=h: self._buy_hotmail007(h)))
            elif p_lower == "lution":
                l = email_providers.get("lution", {})
                if l.get("api_key"):
                    result.append(("Lution", lambda l=l: self._buy_lution(l)))
        
        return result
    
    @staticmethod
    def _buy_zeus(zeus_config: Dict) -> Optional[Dict[str, str]]:
        from ..Helper.mail import ZeusApi
        api = ZeusApi(
            api_key=zeus_config.get("api_key", ""),
            account_type=zeus_config.get("account_type", "HOTMAIL")
        )
        return api.create_account()
    
    @staticmethod
    def _buy_hotmail007(h007_config: Dict) -> Optional[Dict[str, str]]:
        from ..Helper.mail import Hotmail007Api
        api = Hotmail007Api(
            api_key=h007_config.get("api_key", ""),
            mail_type=h007_config.get("mail_type", "hotmail")
        )
        return api.create_account()
    
    @staticmethod
    def _buy_lution(lution_config: Dict) -> Optional[Dict[str, str]]:
        from ..Helper.mail import LutionApi
        api = LutionApi(
            api_key=lution_config.get("api_key", ""),
            category=lution_config.get("account_type", "hotmail")
        )
        return api.create_account()

    @staticmethod
    def _buy_mailcow(mailcow_config: Dict) -> Optional[Dict[str, str]]:
        """Provision a fresh mailbox on the user's Mailcow server.

        Picks the configured domain (or the first active one from the server),
        generates a random local-part + password, and calls the Mailcow API to
        create the mailbox so we can later read the verification email via IMAP.
        """
        from ..Helper.mail import MailcowApi
        host_url = mailcow_config.get("host_url", "")
        api_key = mailcow_config.get("api_key", "")
        if not host_url or not api_key:
            raise RuntimeError("Mailcow host_url or api_key is missing")

        api = MailcowApi(host_url=host_url, api_key=api_key)

        domain = (mailcow_config.get("domain") or "").strip()
        if not domain:
            domains = api.get_domains() or []
            if not domains:
                raise RuntimeError("No active Mailcow domains available")
            domain = domains[0]

        local = _random_local_part()
        email = f"{local}@{domain}"
        password = _random_password()

        created = api.create_account(email, password)
        if not created:
            raise RuntimeError(f"Mailcow create_account failed for {email}")

        return {
            "email": email,
            "password": password,
            "refresh_token": "",
            "client_id": "",
        }

    @staticmethod
    def _buy_cybertemp(api_key: str, cybertemp_config: Dict) -> Optional[Dict[str, str]]:
        """Generate a random CyberTemp address.

        CyberTemp is a temp-mail service — no actual provisioning required, we
        just pick an available domain and build a random address on it.
        """
        from ..Helper.mail import MskMailApi
        api = MskMailApi(api_key=api_key)

        domain = (cybertemp_config.get("domain") or "").strip()
        if not domain:
            domains = api.get_domains(domain_type="discord") or []
            if not domains:
                raise RuntimeError("CyberTemp returned no domains")
            domain = random.choice(domains)

        local = _random_local_part()
        email = f"{local}@{domain}"

        return {
            "email": email,
            "password": "",
            "refresh_token": "",
            "client_id": "",
        }

    @staticmethod
    def _buy_duckmail(api_key: str, duckmail_config: Dict) -> Optional[Dict[str, str]]:
        """Provision a fresh mailbox on DuckMail."""
        from ..Helper.mail import DuckMailApi
        api = DuckMailApi(api_key=api_key)

        domain = (duckmail_config.get("domain") or "").strip()
        if not domain:
            domains = api.get_domains() or []
            if not domains:
                raise RuntimeError("DuckMail returned no domains")
            domain = random.choice(domains)

        local = _random_local_part()
        email = f"{local}@{domain}"
        password = _random_password()

        created = api.create_account(email, password)
        if not created:
            raise RuntimeError(f"DuckMail create_account failed for {email}")

        return {
            "email": email,
            "password": password,
            "refresh_token": "",
            "client_id": "",
        }
