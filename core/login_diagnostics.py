"""
LoginDiagnostics - تشخیص علت شکست Login.

این ماژول با بررسی وضعیت صفحه، شبکه، Cookieها و ... علت دقیق
شکست Login را تشخیص می‌دهد و در لاگ ثبت می‌کند.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from playwright.async_api import Page, Error as PlaywrightError

logger = logging.getLogger("divar.login.diagnostics")


class FailureReason(str, Enum):
    """دلایل ممکن برای شکست Login."""

    UNKNOWN = "unknown"
    NETWORK_DISCONNECTED = "network_disconnected"
    NETWORK_TIMEOUT = "network_timeout"
    PAGE_NOT_LOADED = "page_not_loaded"
    SERVER_NO_RESPONSE = "server_no_response"
    WRONG_CODE = "wrong_code"
    INVALID_PHONE = "invalid_phone"
    RATE_LIMITED = "rate_limited"
    LOGIN_PAGE_STILL_VISIBLE = "login_page_still_visible"
    NO_SESSION_CREATED = "no_session_created"
    NO_COOKIE_CREATED = "no_cookie_created"
    NO_TOKEN_CREATED = "no_token_created"
    PROTECTED_PAGE_INACCESSIBLE = "protected_page_inaccessible"
    BROWSER_CLOSED = "browser_closed"
    USER_CANCELLED = "user_cancelled"


@dataclass
class DiagnosticReport:
    """گزارش تشخیص علت شکست."""

    success: bool
    reason: FailureReason
    message: str
    details: dict = field(default_factory=dict)
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{'OK' if self.success else 'FAIL'}] {self.reason.value}: {self.message}"


class LoginDiagnostics:
    """تشخیص‌گر علت شکست Login."""

    # پیام‌های خطای رایج در صفحه
    WRONG_CODE_KEYWORDS = ["اشتباه", "نادرست", "invalid", "incorrect", "wrong"]
    RATE_LIMIT_KEYWORDS = ["بعدا", "later", "بیش از حد", "too many", "rate"]
    INVALID_PHONE_KEYWORDS = ["معتبر", "صحیح", "valid", "correct"]

    async def analyze_failure(
        self,
        page: Page,
        exception: Optional[BaseException] = None,
        stage: str = "unknown",
    ) -> DiagnosticReport:
        """
        تحلیل علت شکست Login.

        Args:
            page: صفحه فعلی مرورگر
            exception: exception رخ‌داده (در صورت وجود)
            stage: مرحله‌ای که شکست در آن رخ داد
        """
        logger.info("[diagnostics] Analyzing failure at stage=%s", stage)

        # بررسی exception
        if exception:
            return await self._analyze_exception(page, exception, stage)

        # بررسی وضعیت صفحه
        return await self._analyze_page_state(page, stage)

    async def _analyze_exception(
        self,
        page: Page,
        exc: BaseException,
        stage: str,
    ) -> DiagnosticReport:
        """تحلیل exception."""
        exc_str = str(exc).lower()
        exc_type = type(exc).__name__

        # Timeout
        if "timeout" in exc_str or exc_type == "TimeoutError":
            logger.warning("[diagnostics] Timeout detected: %s", exc)
            return DiagnosticReport(
                success=False,
                reason=FailureReason.NETWORK_TIMEOUT,
                message=f"Timeout at stage {stage}: {exc}",
                details={"exception": exc_type, "stage": stage},
                retryable=True,
            )

        # Browser closed / Target closed
        if any(kw in exc_str for kw in ["target closed", "browser closed", "context closed"]):
            logger.warning("[diagnostics] Browser/context closed: %s", exc)
            return DiagnosticReport(
                success=False,
                reason=FailureReason.BROWSER_CLOSED,
                message=f"Browser was closed: {exc}",
                details={"exception": exc_type},
                retryable=False,
            )

        # Network errors
        if any(kw in exc_str for kw in ["net::", "network", "err_connection", "err_internet"]):
            logger.warning("[diagnostics] Network error: %s", exc)
            return DiagnosticReport(
                success=False,
                reason=FailureReason.NETWORK_DISCONNECTED,
                message=f"Network error: {exc}",
                details={"exception": exc_type},
                retryable=True,
            )

        # Generic playwright error
        if isinstance(exc, PlaywrightError):
            logger.warning("[diagnostics] Playwright error: %s", exc)
            return DiagnosticReport(
                success=False,
                reason=FailureReason.UNKNOWN,
                message=f"Playwright error at {stage}: {exc}",
                details={"exception": exc_type, "stage": stage},
                retryable=True,
            )

        # Cancelled
        if "cancel" in exc_str:
            return DiagnosticReport(
                success=False,
                reason=FailureReason.USER_CANCELLED,
                message=f"Operation cancelled: {exc}",
                details={"exception": exc_type},
                retryable=False,
            )

        # Unknown
        logger.error("[diagnostics] Unknown exception: %s: %s", exc_type, exc)
        return DiagnosticReport(
            success=False,
            reason=FailureReason.UNKNOWN,
            message=f"{exc_type}: {exc}",
            details={"exception": exc_type, "stage": stage},
            retryable=False,
        )

    async def _analyze_page_state(self, page: Page, stage: str) -> DiagnosticReport:
        """تحلیل وضعیت صفحه."""
        try:
            url = page.url
            content = await page.content()
            content_lower = content.lower()

            # کد اشتباه
            if any(kw in content_lower for kw in self.WRONG_CODE_KEYWORDS):
                logger.warning("[diagnostics] Wrong code detected in page")
                return DiagnosticReport(
                    success=False,
                    reason=FailureReason.WRONG_CODE,
                    message="Verification code appears to be wrong",
                    details={"url": url, "stage": stage},
                    retryable=False,
                )

            # Rate limit
            if any(kw in content_lower for kw in self.RATE_LIMIT_KEYWORDS):
                logger.warning("[diagnostics] Rate limit detected")
                return DiagnosticReport(
                    success=False,
                    reason=FailureReason.RATE_LIMITED,
                    message="Rate limited by server",
                    details={"url": url},
                    retryable=True,
                )

            # شماره نامعتبر
            if any(kw in content_lower for kw in self.INVALID_PHONE_KEYWORDS):
                logger.warning("[diagnostics] Invalid phone detected")
                return DiagnosticReport(
                    success=False,
                    reason=FailureReason.INVALID_PHONE,
                    message="Phone number is invalid",
                    details={"url": url},
                    retryable=False,
                )

            # Generic - page loaded but login didn't succeed
            return DiagnosticReport(
                success=False,
                reason=FailureReason.LOGIN_PAGE_STILL_VISIBLE,
                message=f"Login did not complete at stage {stage}",
                details={"url": url, "stage": stage, "content_length": len(content)},
                retryable=True,
            )

        except PlaywrightError as e:
            logger.error("[diagnostics] Error reading page: %s", e)
            return DiagnosticReport(
                success=False,
                reason=FailureReason.PAGE_NOT_LOADED,
                message=f"Cannot read page state: {e}",
                details={"stage": stage},
                retryable=True,
            )
