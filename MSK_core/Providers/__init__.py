"""Email Provider abstraction layer.

This package implements the Strategy pattern for email providers.
Each provider implements the IEmailProvider interface, and the
EmailProviderFactory selects the correct provider based on config.

Usage:
    from MSK_core.Providers import EmailProviderFactory

    provider = EmailProviderFactory.from_config(config)
    email, password = provider.create_account(worker_id=1)
    url = provider.get_verification_url(email, password, timeout=120)
"""

from .base import IEmailProvider, EmailAccount
from .factory import EmailProviderFactory

__all__ = ["IEmailProvider", "EmailAccount", "EmailProviderFactory"]
