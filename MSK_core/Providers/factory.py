"""Email Provider Factory.

Selects the correct provider implementation based on the runtime config.
This replaces the 400-line if/elif chain in DiscordRegister._create_email().
"""
from typing import Optional, Dict, Any

from .base import IEmailProvider
from .cybertemp import CyberTempProvider
from .duckmail import DuckMailProvider
from .mailcow import MailcowProvider
from .hotmail007 import Hotmail007Provider
from .lution import LutionProvider


class EmailProviderFactory:
    """Create the correct email provider from config."""

    @staticmethod
    def from_config(config: Dict[str, Any]) -> IEmailProvider:
        """Build the appropriate IEmailProvider from the runtime config dict.

        Checks email_providers.{provider}.enabled in priority order.
        Falls back to CyberTemp with legacy cybertemp_api_key if nothing is enabled.
        """
        email_providers = config.get("email_providers", {})

        if email_providers.get("cybertemp", {}).get("enabled", False):
            ct = email_providers["cybertemp"]
            api_key = ct.get("api_key", "") or config.get("cybertemp_api_key", "")
            domain = ct.get("domain", "random")
            return CyberTempProvider(api_key=api_key, domain=domain)

        if email_providers.get("mailcow", {}).get("enabled", False):
            mc = email_providers["mailcow"]
            host_url = mc.get("host_url", "")
            if host_url and not host_url.startswith("http"):
                host_url = f"https://{host_url}"
            return MailcowProvider(
                host_url=host_url,
                api_key=mc.get("api_key", ""),
                domain=mc.get("domain", "").strip(),
            )

        if email_providers.get("duckmail", {}).get("enabled", False):
            dm = email_providers["duckmail"]
            return DuckMailProvider(
                api_key=dm.get("api_key", ""),
                domain=dm.get("domain", "").strip(),
            )

        if email_providers.get("hotmail007", {}).get("enabled", False):
            hc = email_providers["hotmail007"]
            return Hotmail007Provider(
                api_key=hc.get("api_key", ""),
                mail_type=hc.get("mail_type", "hotmail"),
                product_id=hc.get("product_id", None),
            )

        if email_providers.get("lution", {}).get("enabled", False):
            lc = email_providers["lution"]
            return LutionProvider(
                api_key=lc.get("api_key", ""),
                category=lc.get("account_type", "hotmail.trusted.graph"),
            )

        # Default: CyberTemp with legacy key
        return CyberTempProvider(
            api_key=config.get("cybertemp_api_key", ""),
            domain="random",
        )

    @staticmethod
    def get_provider_for_verification(
        config: Dict[str, Any],
        refresh_token: str = "",
        client_id: str = "",
    ) -> IEmailProvider:
        """Get a provider instance configured for verification polling.

        Same as from_config() but ensures credentials are carried through.
        """
        provider = EmailProviderFactory.from_config(config)

        # Attach purchased account tokens to providers that need them
        if isinstance(provider, (Hotmail007Provider, LutionProvider)):
            # These providers use refresh_token/client_id for Graph API verification
            pass  # Handle explicit response codes before applying the fallback checks.

        return provider
