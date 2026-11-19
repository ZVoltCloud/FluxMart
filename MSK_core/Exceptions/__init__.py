"""Centralized exception hierarchy for FluxMart.

All custom exceptions derive from MskError so callers can catch
broad categories or specific errors as needed.  This replaces the
pattern of string-based error detection (e.g. 'insufficient' in str(e)).
"""


class MskError(Exception):
    """Base exception for all MSK errors."""
    pass


# ── Email Provider Errors ──────────────────────────────────────────────

class EmailProviderError(MskError):
    """Base for all email provider failures."""
    pass


class EmailCreationError(EmailProviderError):
    """Failed to create an email account."""
    pass


class EmailStockExhausted(EmailProviderError):
    """Email provider has no accounts in stock."""
    pass


class EmailVerificationTimeout(EmailProviderError):
    """Timed out waiting for the verification email to arrive."""
    pass


class EmailVerificationFailed(EmailProviderError):
    """Verification email found but the verification step itself failed."""
    pass


class EmailAuthError(EmailProviderError):
    """Authentication to the email provider failed (invalid API key, etc.)."""
    pass


# ── CAPTCHA Errors ─────────────────────────────────────────────────────

class CaptchaError(MskError):
    """Base for CAPTCHA-related failures."""
    pass


class CaptchaFailedError(CaptchaError):
    """CAPTCHA solving attempt failed."""
    pass


class CaptchaTimeoutError(CaptchaError):
    """CAPTCHA solving timed out."""
    pass


class EndlessCaptchaError(CaptchaError):
    """CAPTCHA keeps reappearing — likely flagged proxy/IP."""
    pass


# ── Phone Verification Errors ──────────────────────────────────────────

class PhoneVerificationError(MskError):
    """Base for phone verification failures."""
    pass


class PhoneStockExhausted(PhoneVerificationError):
    """No phone numbers available from the SMS provider."""
    pass


class PhoneCodeTimeout(PhoneVerificationError):
    """Timed out waiting for the SMS code."""
    pass


# ── Browser / Automation Errors ────────────────────────────────────────

class BrowserError(MskError):
    """Base for browser automation failures."""
    pass


class BrowserLaunchError(BrowserError):
    """Failed to launch or configure the browser."""
    pass


class PageNavigationError(BrowserError):
    """Failed to navigate to the expected page."""
    pass


class TokenExtractionError(BrowserError):
    """Could not extract the Discord token from the browser."""
    pass


# ── Rate Limiting ──────────────────────────────────────────────────────

class RateLimitError(MskError):
    """Discord or provider rate limit hit."""
    pass


# ── Configuration Errors ───────────────────────────────────────────────

class ConfigError(MskError):
    """Invalid or missing configuration."""
    pass


class ConfigValidationError(ConfigError):
    """Config values are present but invalid."""
    pass


# ── License / Auth Errors ──────────────────────────────────────────────

class LicenseError(MskError):
    """License validation or KeyAuth failure."""
    pass
