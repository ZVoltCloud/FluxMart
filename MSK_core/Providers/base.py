"""Abstract base class for all email providers.

Every provider must implement create_account() and get_verification_url().
The EmailAccount dataclass standardizes the return format.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class EmailAccount:
    """Standardized email account result returned by all providers."""
    email: str
    password: str
    refresh_token: str = ""
    client_id: str = ""
    provider_name: str = ""
    extra: dict = field(default_factory=dict)


class IEmailProvider(ABC):
    """Interface that all email providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for logging."""
        ...

    @abstractmethod
    def create_account(self, worker_id: int = 0) -> Optional[EmailAccount]:
        """Create a new email account.

        Returns an EmailAccount on success, or None on failure.
        Raises EmailCreationError or EmailStockExhausted on known failures.
        """
        ...

    @abstractmethod
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
        """Poll for the Discord verification email and return the verification URL.

        Returns the URL string on success, None on timeout or failure.
        """
        ...

    def check_balance(self) -> Optional[float]:
        """Check provider account balance. Returns None if not supported."""
        return None

    def get_domains(self) -> list:
        """Get available domains. Returns empty list if not supported."""
        return []
