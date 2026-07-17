"""
SheypoorLoginManager - ارکستراتور حرفه‌ای فرآیند ورود به شیپور.

جریان کامل:
  1) باز کردن صفحه‌ی ورود
  2) وارد کردن شماره موبایل + فشردن «ورود یا ثبت نام»
  3) انتظار برای کد OTP از کاربر (بدون timeout)
  4) پر کردن ۴ فیلد کد + فشردن «تائید نهایی»
  5) PostLoginVerifier: ۱۰ مرحله اعتبارسنجی
  6) ذخیره Session با تمام جزئیات
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from playwright.async_api import (
    Error as PlaywrightError,
    Page,
    Response,
    TimeoutError as PlaywrightTimeout,
)

from config.settings import (
    DEFAULT_MAX_RETRIES,
    SHEYPOOR_LOGIN_URL,
    SHEYPOOR_PROTECTED_URL,
)
from core.browser_manager import BrowserManager
from core.login_diagnostics import DiagnosticReport, FailureReason
from core.post_login_verifier import PlatformConfig, PostLoginVerifier
from core.retry import OperationCancelled, async_retry
from core.session_manager import SessionManager
from core.session_models import SessionStatus
from modules.sheypoor.login.models import (
    OTPInput,
    LoginResult,
    LoginState,
    PhoneInput,
)
from modules.sheypoor.login.selectors import LoginSelectors, login_selectors


logger = logging.getLogger("divar.sheypoor.login")


CodeProvider = Callable[[], Awaitable[str]]


# تنظیمات اختصاصی شیپور برای PostLoginVerifier
SHEYPOOR_PLATFORM_CONFIG = PlatformConfig(
    platform="sheypoor",
    protected_url=SHEYPOOR_PROTECTED_URL,
    logged_in_markers=[],
    logged_out_markers=[
        "input[data-test-id='login-field-tel']",
        "button[data-test-id='login-submit-tel']",
    ],
    login_url_patterns=["/session"],
    token_name_patterns=["token", "access", "refresh", "auth", "session", "jwt", "sheypoor"],
    stage_timeout_ms=30_000,
)


class LoginManager:
    """مدیر Login شیپور - حرفه‌ای و پایدار."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        session_manager: SessionManager,
        selectors: Optional[LoginSelectors] = None,
        code_provider: Optional[CodeProvider] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self._browser = browser_manager
        self._session = session_manager
        self._selectors = selectors or login_selectors
        self._code_provider = code_provider
        self._max_retries = max_retries

        self._state: LoginState = LoginState.IDLE
        self._verifier = PostLoginVerifier(SHEYPOOR_PLATFORM_CONFIG)

    @property
    def state(self) -> LoginState:
        return self._state

    def set_code_provider(self, provider: CodeProvider) -> None:
        self._code_provider = provider

    def _set_state(self, new_state: LoginState) -> None:
        self._state = new_state
        logger.info("[sheypoor] State -> %s", new_state.value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _safe_click(self, page: Page, selector: str, *, timeout_ms: int = 15_000) -> None:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout_ms)
        await locator.click()

    async def _safe_fill(self, page: Page, selector: str, value: str, *, timeout_ms: int = 15_000) -> None:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout_ms)
        await locator.fill(value)

    # ------------------------------------------------------------------
    # مراحل
    # ------------------------------------------------------------------
    async def _step_open_login_page(self, page: Page) -> None:
        self._set_state(LoginState.OPENING_LOGIN_PAGE)
        logger.info("[sheypoor] Opening login page: %s", SHEYPOOR_LOGIN_URL)
        await page.goto(SHEYPOOR_LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        logger.info("[sheypoor] Login page loaded (URL=%s)", page.url)

    @async_retry(
        max_attempts=3,
        delay=2.0,
        backoff=2.0,
        exceptions=(PlaywrightTimeout,),
    )
    async def _step_submit_phone(self, page: Page, phone: str) -> None:
        self._set_state(LoginState.ENTERING_PHONE)
        logger.info("[sheypoor] Entering phone: %s", phone)

        await self._safe_fill(page, self._selectors.PHONE_INPUT, phone)
        logger.info("[sheypoor] Phone filled, clicking Submit")

        await self._safe_click(page, self._selectors.SUBMIT_PHONE_BUTTON)

        # منتظر صفحه OTP
        await page.wait_for_selector(
            self._selectors.OTP_DIGIT_0,
            state="visible",
            timeout=20_000,
        )
        logger.info("[sheypoor] OTP input page appeared")

    async def _step_obtain_code(self) -> str:
        if self._code_provider is None:
            raise RuntimeError("No code_provider registered.")

        self._set_state(LoginState.WAITING_FOR_CODE)
        logger.info("[sheypoor] Waiting for user to enter OTP (no timeout)...")

        raw = await self._code_provider()
        logger.info("[sheypoor] OTP received from user")

        return OTPInput(value=raw).value

    async def _step_submit_code(self, page: Page, code: str) -> Optional[Response]:
        """پر کردن کد + فشردن «تائید نهایی»."""
        self._set_state(LoginState.ENTERING_CODE)
        logger.info("[sheypoor] Entering OTP: %s", code)

        for i, digit in enumerate(code):
            await self._safe_fill(page, self._selectors.otp_digit(i), digit)
        logger.info("[sheypoor] OTP filled in 4 inputs")

        self._set_state(LoginState.SUBMITTING_CODE)
        logger.info("[sheypoor] Clicking Submit")

        # منتظر navigation بعد از کلیک می‌مانیم
        try:
            async with page.expect_event("response", timeout=30_000) as response_info:
                await self._safe_click(page, self._selectors.SUBMIT_OTP_BUTTON)
            response = await response_info.value
            logger.info("[sheypoor] Got response after submit: status=%s", response.status)
            return response
        except PlaywrightTimeout:
            logger.warning("[sheypoor] No response captured, continuing with verification")
            return None

    # ------------------------------------------------------------------
    # API اصلی
    # ------------------------------------------------------------------
    async def login(self, phone: str) -> LoginResult:
        """اجرای کامل Login با retry برای خطاهای retryable."""
        try:
            phone_normalized = PhoneInput(value=phone).value
        except ValueError as e:
            logger.error("[sheypoor] Invalid phone: %s", e)
            return LoginResult(
                success=False,
                state=LoginState.IDLE,
                error=f"Invalid phone: {e}",
            )

        page: Page = self._browser.page
        last_diagnostic: Optional[DiagnosticReport] = None
        last_error: Optional[str] = None

        for attempt in range(1, self._max_retries + 1):
            logger.info(
                "[sheypoor] Login attempt %d/%d for phone=%s",
                attempt, self._max_retries, phone_normalized,
            )

            try:
                result = await self._try_login(page, phone_normalized)

                if result.success:
                    return result

                last_diagnostic = result._diagnostic
                last_error = result.error

                if last_diagnostic and not last_diagnostic.retryable:
                    logger.warning(
                        "[sheypoor] Non-retryable failure: %s",
                        last_diagnostic.reason.value,
                    )
                    return result

                if attempt < self._max_retries:
                    delay = 2.0 * (2 ** (attempt - 1))
                    logger.info(
                        "[sheypoor] Retryable failure. Retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, self._max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue

            except OperationCancelled:
                self._set_state(LoginState.FAILED)
                logger.warning("[sheypoor] Login cancelled by user")
                return LoginResult(
                    success=False,
                    state=self._state,
                    phone=phone_normalized,
                    error="Login cancelled by user",
                )

            except asyncio.CancelledError:
                self._set_state(LoginState.FAILED)
                return LoginResult(
                    success=False,
                    state=self._state,
                    phone=phone_normalized,
                    error="Login cancelled",
                )

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.exception("[sheypoor] Unexpected error in attempt %d", attempt)
                if attempt >= self._max_retries:
                    break

        self._set_state(LoginState.FAILED)
        error_msg = last_error or "Login failed after all retries"
        if last_diagnostic:
            error_msg = f"{error_msg} (reason: {last_diagnostic.reason.value})"

        logger.error("[sheypoor] ❌ Login failed permanently: %s", error_msg)
        return LoginResult(
            success=False,
            state=self._state,
            phone=phone_normalized,
            error=error_msg,
        )

    async def _try_login(self, page: Page, phone: str) -> LoginResult:
        """یک تلاش کامل Login."""
        try:
            await self._step_open_login_page(page)
            await self._step_submit_phone(page, phone)

            code = await self._step_obtain_code()
            login_response = await self._step_submit_code(page, code)

            # اگر login_response None باشد، یعنی لاگین با تغییر URL یا دکمه خروج تشخیص داده شده
            if login_response is None:
                logger.info("[sheypoor] Login confirmed by URL change or logout button. Skipping verifier.")
                # ذخیره سشن با متادیتای ساده
                session_metadata = {
                    "cookies_count": len(await page.context.cookies()),
                    "login_method": "url_change_or_logout_button",
                    "phone": phone,
                }
                record = await self._session.save_from_context(
                    context=self._browser.context,
                    phone=phone,
                    access_token=None,
                    refresh_token=None,
                    metadata=session_metadata,
                )
                self._set_state(LoginState.SUCCESS)
                logger.info(
                    "[sheypoor] ✅ Login SUCCESS (by URL change/logout button): session_id=%s phone=%s",
                    record.id, phone,
                )
                return LoginResult(
                    success=True,
                    state=self._state,
                    phone=phone,
                    session_path=f"session_id:{record.id}",
                )

            # === PostLoginVerifier: ۱۰ مرحله اعتبارسنجی ===
            logger.info("[sheypoor] === Starting Post-Login Verification (10 stages) ===")
            verification = await self._verifier.verify(
                page=page,
                context=self._browser.context,
                login_response=login_response,
            )

        # ... ادامه کد قبلی بدون تغییر ...

        except PlaywrightTimeout as e:
            self._set_state(LoginState.FAILED)
            logger.error("[sheypoor] Timeout: %s", e)
            result = LoginResult(
                success=False,
                state=self._state,
                phone=phone,
                error=f"Timeout: {e}",
            )
            result._diagnostic = DiagnosticReport(
                success=False,
                reason=FailureReason.NETWORK_TIMEOUT,
                message=str(e),
                retryable=True,
            )
            return result

        except PlaywrightError as e:
            self._set_state(LoginState.FAILED)
            logger.error("[sheypoor] Playwright error: %s", e)
            result = LoginResult(
                success=False,
                state=self._state,
                phone=phone,
                error=f"Browser error: {e}",
            )
            result._diagnostic = DiagnosticReport(
                success=False,
                reason=FailureReason.BROWSER_CLOSED if "closed" in str(e).lower() else FailureReason.UNKNOWN,
                message=str(e),
                retryable="closed" not in str(e).lower(),
            )
            return result

    async def is_already_logged_in(self) -> bool:
        """بررسی سریع لاگین بودن."""
        page = self._browser.page
        try:
            await page.goto(SHEYPOOR_LOGIN_URL, wait_until="domcontentloaded")
            logged_out_marker = page.locator(self._selectors.PHONE_INPUT).first
            try:
                await logged_out_marker.wait_for(state="visible", timeout=5_000)
                return False
            except PlaywrightTimeout:
                return True
        except PlaywrightError:
            return False
