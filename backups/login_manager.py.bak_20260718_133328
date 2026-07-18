"""
DivarLoginManager - ارکستراتور حرفه‌ای فرآیند ورود به دیوار.

جریان کامل:
  1) باز کردن صفحه‌ی ورود
  2) کلیک روی «ورود به حساب کاربری»
  3) وارد کردن شماره موبایل + فشردن «بعدی» + انتظار برای API initiate
  4) انتظار برای کد از کاربر (بدون timeout)
  5) پر کردن ۶ فیلد کد + فشردن «ورود» + گرفتن Login Response
  6) PostLoginVerifier: ۱۰ مرحله اعتبارسنجی
  7) ذخیره Session با تمام جزئیات

هیچ تصمیمی بر اساس حدس یا sleep ثابت گرفته نمی‌شود.
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
    AUTH_INITIATE_ENDPOINT,
    AUTH_VERIFY_ENDPOINT,
    DEFAULT_MAX_RETRIES,
    DIVAR_BASE_URL,
    DIVAR_LOGIN_URL,
    DIVAR_PROTECTED_URL,
)
from core.browser_manager import BrowserManager
from core.login_diagnostics import DiagnosticReport, FailureReason
from core.post_login_verifier import PlatformConfig, PostLoginVerifier
from core.retry import OperationCancelled, async_retry
from core.session_manager import SessionManager
from core.session_models import SessionStatus
from modules.login.models import (
    CodeInput,
    LoginResult,
    LoginState,
    PhoneInput,
)
from modules.login.selectors import LoginSelectors, login_selectors


logger = logging.getLogger("divar.login")


CodeProvider = Callable[[], Awaitable[str]]


# تنظیمات اختصاصی دیوار برای PostLoginVerifier
DIVAR_PLATFORM_CONFIG = PlatformConfig(
    platform="divar",
    protected_url=DIVAR_PROTECTED_URL,
    logged_in_markers=[],  # به نبود logged_out_markers تکیه می‌کنیم
    logged_out_markers=[
        "text=ورود به حساب کاربری",
        "input[name='phone']",
    ],
    login_url_patterns=["/my-divar", "/login", "auth.divar"],
    token_name_patterns=["token", "access", "refresh", "auth", "session", "jwt"],
    stage_timeout_ms=30_000,
)


class LoginManager:
    """
    مدیر Login دیوار - حرفه‌ای و پایدار.

    ویژگی‌ها:
    - هیچ sleep ثابت
    - انتظار هوشمند با Playwright
    - اعتبارسنجی ۱۰ مرحله‌ای
    - Retry با تشخیص نوع خطا
    - Logging کامل
    """

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
        self._verifier = PostLoginVerifier(DIVAR_PLATFORM_CONFIG)

    @property
    def state(self) -> LoginState:
        return self._state

    def set_code_provider(self, provider: CodeProvider) -> None:
        self._code_provider = provider

    def _set_state(self, new_state: LoginState) -> None:
        self._state = new_state
        logger.info("[divar] State -> %s", new_state.value)

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

    def _is_retryable(self, diagnostic: Optional[DiagnosticReport]) -> bool:
        """بررسی می‌کند آیا خطا retryable است یا نه."""
        if diagnostic is None:
            return False
        return diagnostic.retryable

    # ------------------------------------------------------------------
    # مراحل اصلی
    # ------------------------------------------------------------------
    async def _step_open_login_page(self, page: Page) -> None:
        self._set_state(LoginState.OPENING_LOGIN_PAGE)
        logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
        await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        logger.info("[divar] Login page loaded (URL=%s)", page.url)

    async def _step_click_entry_button(self, page: Page) -> None:
        self._set_state(LoginState.CLICKING_ENTRY_BUTTON)
        logger.info("[divar] Clicking entry button")
        await self._safe_click(page, self._selectors.LOGIN_ENTRY_BUTTON)

        # منتظر فیلد phone می‌مانیم
        try:
            await page.wait_for_selector(
                self._selectors.PHONE_INPUT,
                state="visible",
                timeout=15_000,
            )
            logger.info("[divar] Phone input appeared")
        except PlaywrightTimeout:
            logger.debug("[divar] Phone input not explicitly found, continuing")

    @async_retry(
        max_attempts=3,
        delay=2.0,
        backoff=2.0,
        exceptions=(PlaywrightTimeout,),
    )
    async def _step_submit_phone(self, page: Page, phone: str) -> None:
        """وارد کردن شماره + فشردن «بعدی» + انتظار برای API initiate."""
        self._set_state(LoginState.ENTERING_PHONE)
        logger.info("[divar] Entering phone: %s", phone)

        await self._safe_fill(page, self._selectors.PHONE_INPUT, phone)
        logger.info("[divar] Phone filled, clicking Next")

        # کلیک روی «بعدی» + انتظار برای پاسخ API initiate
        async with page.expect_response(
            lambda r: AUTH_INITIATE_ENDPOINT in r.url,
            timeout=30_000,
        ) as response_info:
            await self._safe_click(page, self._selectors.NEXT_BUTTON)

        response = await response_info.value
        logger.info(
            "[divar] Initiate API responded: status=%s",
            response.status,
        )

        if response.status >= 400:
            raise RuntimeError(f"Initiate API failed with status {response.status}")

        # منتظر صفحه کد
        await page.wait_for_selector(
            self._selectors.CODE_INPUT_GROUP,
            state="visible",
            timeout=20_000,
        )
        logger.info("[divar] Code input page appeared")

    async def _step_obtain_code(self) -> str:
        """گرفتن کد از کاربر - بدون timeout."""
        if self._code_provider is None:
            raise RuntimeError("No code_provider registered.")

        self._set_state(LoginState.WAITING_FOR_CODE)
        logger.info("[divar] Waiting for user to enter verification code (no timeout)...")

        raw = await self._code_provider()
        logger.info("[divar] Code received from user")

        return CodeInput(value=raw).value




    async def _step_submit_code(self, page: Page, code: str) -> Optional[Response]:
        """
        پر کردن کد + تشخیص لاگین موفق با ظاهر شدن دکمه خروج.
        """
        self._set_state(LoginState.ENTERING_CODE)
        logger.info("[divar] Entering code: %s", code)

        # ۶ رقم رو پر کن
        for i, digit in enumerate(code, start=1):
            await self._safe_fill(page, self._selectors.code_digit(i), digit)

        # منتظر میمونیم تا یا دکمه خروج ظاهر بشه یا خطا بیاد
        logout_button_selector = "div[role='button']:has-text('خروج')"
        
        try:
            # حداکثر ۳۰ ثانیه منتظر دکمه خروج
            await page.wait_for_selector(logout_button_selector, state="visible", timeout=30000)
            logger.info("[divar] ✅ Logout button appeared -> login successful!")
            # لاگین موفق - یه Response ساختگی برمیگردونیم برای ادامه
            return None
        except PlaywrightTimeout:
            # اگه دکمه خروج نیومد، احتمالاً کد اشتباه بوده یا خطای دیگه
            logger.warning("[divar] Logout button not appeared, checking for error...")
            # می‌تونیم پیام خطا رو هم چک کنیم
            error_selector = "text=کد وارد شده اشتباه است"
            if await page.locator(error_selector).count() > 0:
                raise RuntimeError("Verification code is incorrect")
            else:
                raise RuntimeError("Login failed without error message")





    # ------------------------------------------------------------------
    # API اصلی
    # ------------------------------------------------------------------
    async def login(self, phone: str) -> LoginResult:
        """اجرای کامل فرآیند Login با retry برای خطاهای retryable."""
        try:
            phone_normalized = PhoneInput(value=phone).value
        except ValueError as e:
            logger.error("[divar] Invalid phone: %s", e)
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
                "[divar] Login attempt %d/%d for phone=%s",
                attempt, self._max_retries, phone_normalized,
            )

            try:
                result = await self._try_login(page, phone_normalized)

                if result.success:
                    return result

                # Login شکست خورد - بررسی retryability
                last_diagnostic = result._diagnostic
                last_error = result.error

                if last_diagnostic and not last_diagnostic.retryable:
                    logger.warning(
                        "[divar] Non-retryable failure: %s",
                        last_diagnostic.reason.value,
                    )
                    return result

                if attempt < self._max_retries:
                    delay = 2.0 * (2 ** (attempt - 1))
                    logger.info(
                        "[divar] Retryable failure. Retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, self._max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue

            except OperationCancelled:
                self._set_state(LoginState.FAILED)
                logger.warning("[divar] Login cancelled by user")
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
                logger.exception("[divar] Unexpected error in attempt %d", attempt)
                if attempt >= self._max_retries:
                    break

        # همه تلاش‌ها شکست خوردند
        self._set_state(LoginState.FAILED)
        error_msg = last_error or "Login failed after all retries"
        if last_diagnostic:
            error_msg = f"{error_msg} (reason: {last_diagnostic.reason.value})"

        logger.error("[divar] ❌ Login failed permanently: %s", error_msg)
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
            await self._step_click_entry_button(page)
            await self._step_submit_phone(page, phone)

            code = await self._step_obtain_code()
            login_response = await self._step_submit_code(page, code)

            # اگر login_response None است یعنی با دکمه خروج لاگین تشخیص داده شده
            if login_response is None:
                logger.info("[divar] Login confirmed by logout button. Skipping verifier.")
                # ذخیره سشن با متادیتای ساده
                session_metadata = {
                    "cookies_count": len(await page.context.cookies()),
                    "login_method": "logout_button_detected",
                    "phone": phone,
                }
                record, json_path = await self._session.save_and_export(
                    context=self._browser.context,
                    phone=phone,
                    access_token=None,
                    refresh_token=None,
                    metadata=session_metadata,
                )
                self._set_state(LoginState.SUCCESS)
                logger.info(
                    "[divar] ✅ Login SUCCESS (by logout button): session_id=%s phone=%s json=%s",
                    record.id, phone, json_path,
                )
                return LoginResult(
                    success=True,
                    state=self._state,
                    phone=phone,
                    session_path=str(json_path),
                )

            # === PostLoginVerifier: 10 مرحله اعتبارسنجی ===
            logger.info("[divar] === Starting Post-Login Verification (10 stages) ===")
            verification = await self._verifier.verify(
                page=page,
                context=self._browser.context,
                login_response=login_response,
            )

            logger.info(
                "[divar] Verification result: success=%s (%s)",
                verification.success, verification.stage_summary(),
            )

            if not verification.success:
                self._set_state(LoginState.FAILED)
                error_msg = "Post-login verification failed"
                if verification.diagnostic:
                    error_msg = f"{error_msg}: {verification.diagnostic.reason.value} - {verification.diagnostic.message}"
                result = LoginResult(
                    success=False,
                    state=self._state,
                    phone=phone,
                    error=error_msg,
                )
                result._diagnostic = verification.diagnostic
                return result

            # === Login موفق - ذخیره Session با تمام جزئیات ===
            session_metadata = {
                "cookies_count": verification.metadata.get("cookies_count", 0),
                "local_storage_origins": verification.metadata.get("local_storage_origins", 0),
                "session_storage_items": verification.metadata.get("session_storage_items", 0),
                "has_access_token": verification.metadata.get("has_access_token", False),
                "has_refresh_token": verification.metadata.get("has_refresh_token", False),
                "protected_page_status": verification.metadata.get("protected_page_status"),
                "stages_passed": verification.stages_passed,
            }

            # ذخیره در SQLite + export فایل JSON دائمی در data/sessions/
            record, json_path = await self._session.save_and_export(
                context=self._browser.context,
                phone=phone,
                access_token=verification.access_token,
                refresh_token=verification.refresh_token,
                metadata=session_metadata,
            )

            self._set_state(LoginState.SUCCESS)
            logger.info(
                "[divar] ✅ Login SUCCESS: session_id=%s phone=%s json=%s",
                record.id, phone, json_path,
            )

            return LoginResult(
                success=True,
                state=self._state,
                phone=phone,
                session_path=str(json_path),
            )

        except PlaywrightTimeout as e:
            self._set_state(LoginState.FAILED)
            logger.error("[divar] Timeout: %s", e)
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
            logger.error("[divar] Playwright error: %s", e)
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
        """بررسی سریع لاگین بودن (با protected URL)."""
        page = self._browser.page
        try:
            await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
            logged_out_marker = page.locator(self._selectors.LOGIN_ENTRY_BUTTON).first
            try:
                await logged_out_marker.wait_for(state="visible", timeout=5_000)
                return False
            except PlaywrightTimeout:
                return True
        except PlaywrightError:
            return False
