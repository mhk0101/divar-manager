"""
SessionValidator - اعتبارسنجی Session با تست واقعی روی سایت.

برای بررسی اعتبار Session، یک صفحه protected از سایت را باز می‌کنیم
و بررسی می‌کنیم که آیا کاربر واقعاً لاگین است یا خیر.
"""

from __future__ import annotations

import logging
from typing import Optional

from playwright.async_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeout

from config.settings import SESSION_VALIDATION_TIMEOUT_MS
from core.retry import SessionExpired, async_retry
from core.session_models import SessionStatus

logger = logging.getLogger("divar.session.validator")


class SessionValidator:
    """
    اعتبارسنجی Session بر اساس platform.

    هر platform قوانین خاص خود را برای تشخیص لاگین بودن دارد.
    """

    def __init__(self, platform: str):
        self._platform = platform

    @async_retry(
        max_attempts=2,
        delay=1.5,
        exceptions=(PlaywrightTimeout, PlaywrightError),
    )
    async def validate(self, page: Page) -> SessionStatus:
        """
        بررسی اعتبار Session با باز کردن یک صفحه protected.

        Returns:
            SessionStatus.VALID اگر لاگین باشیم
            SessionStatus.INVALID اگر لاگین نباشیم
            SessionStatus.UNKNOWN اگر نتوانستیم تشخیص دهیم
        """
        if self._platform == "divar":
            return await self._validate_divar(page)
        elif self._platform == "sheypoor":
            return await self._validate_sheypoor(page)
        else:
            logger.warning("Unknown platform for validation: %s", self._platform)
            return SessionStatus.UNKNOWN

    async def _validate_divar(self, page: Page) -> SessionStatus:
        """
        اعتبارسنجی Session دیوار.

        معیار: در صفحه my-divar، اگر دکمه «ورود به حساب کاربری» وجود داشته باشد
        یعنی لاگین نیستیم. در غیر این صورت لاگین هستیم.
        """
        from config.settings import DIVAR_LOGIN_URL

        try:
            await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

            # بررسی وجود دکمه ورود (نشانه لاگین نبودن)
            login_button = page.locator("text=ورود به حساب کاربری").first
            try:
                await login_button.wait_for(
                    state="visible",
                    timeout=SESSION_VALIDATION_TIMEOUT_MS,
                )
                logger.info("[divar] Session INVALID - login button visible")
                return SessionStatus.INVALID
            except PlaywrightTimeout:
                # دکمه ورود وجود ندارد => لاگین هستیم
                logger.info("[divar] Session VALID - no login button")
                return SessionStatus.VALID

        except PlaywrightTimeout as e:
            logger.warning("[divar] Validation timeout: %s", e)
            raise
        except PlaywrightError as e:
            logger.error("[divar] Validation playwright error: %s", e)
            raise

    async def _validate_sheypoor(self, page: Page) -> SessionStatus:
        """
        اعتبارسنجی Session شیپور.

        معیار: در صفحه session، اگر فیلد شماره موبایل وجود داشته باشد
        یعنی لاگین نیستیم. در غیر این صورت لاگین هستیم.
        """
        from config.settings import SHEYPOOR_LOGIN_URL

        try:
            await page.goto(SHEYPOOR_LOGIN_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

            # بررسی وجود فیلد شماره (نشانه لاگین نبودن)
            phone_field = page.locator("input[data-test-id='login-field-tel']").first
            try:
                await phone_field.wait_for(
                    state="visible",
                    timeout=SESSION_VALIDATION_TIMEOUT_MS,
                )
                logger.info("[sheypoor] Session INVALID - phone field visible")
                return SessionStatus.INVALID
            except PlaywrightTimeout:
                # فیلد شماره وجود ندارد => لاگین هستیم
                logger.info("[sheypoor] Session VALID - no phone field")
                return SessionStatus.VALID

        except PlaywrightTimeout as e:
            logger.warning("[sheypoor] Validation timeout: %s", e)
            raise
        except PlaywrightError as e:
            logger.error("[sheypoor] Validation playwright error: %s", e)
            raise
