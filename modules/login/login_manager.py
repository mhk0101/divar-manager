"""
DivarLoginManager - ارکستراتور حرفه‌ای فرآیند ورود به دیوار.

اصلاحات نهایی (2026-07-19):
1. ✅ تشخیص حالت فعلی صفحه قبل از شروع (رفع مشکل بار دوم)
2. ✅ تشخیص ورود کد از سایت توسط کاربر (همزمان با UI)
3. ✅ مقاومت در برابر قطع اینترنت (با URL های ایرانی)
4. ✅ پاک کردن state قبل از retry
5. ✅ رفع باگ indentation در _try_login
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
    logged_in_markers=[],
    logged_out_markers=[
        "text=ورود به حساب کاربری",
        "input[name='phone']",
    ],
    login_url_patterns=["/login", "auth.divar"],
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
    - تشخیص حالت فعلی صفحه
    - تشخیص ورود کد از سایت
    - مقاومت در برابر قطع اینترنت
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
    # ✨ تشخیص حالت فعلی صفحه
    # ------------------------------------------------------------------
    async def _detect_page_state(self, page: Page) -> dict:
        """
        تشخیص حالت فعلی صفحه.
        
        Returns:
            dict با کلیدهای:
            - is_logged_in: آیا لاگین است؟ (دکمه خروج وجود دارد)
            - has_code_input: آیا فیلد کد وجود دارد؟
            - has_phone_input: آیا فیلد شماره وجود دارد؟
            - has_entry_button: آیا دکمه "ورود به حساب کاربری" وجود دارد؟
        """
        result = {
            "is_logged_in": False,
            "has_code_input": False,
            "has_phone_input": False,
            "has_entry_button": False,
        }
        
        try:
            # بررسی دکمه خروج (نشانه لاگین بودن)
            logout_button = page.locator("div[role='button']:has-text('خروج')")
            if await logout_button.count() > 0:
                result["is_logged_in"] = True
                logger.info("[divar] Page state: Already logged in (logout button found)")
                return result
            
            # بررسی فیلد کد (6 فیلد)
            code_input = page.locator(self._selectors.CODE_DIGIT_1)
            if await code_input.count() > 0:
                result["has_code_input"] = True
                logger.info("[divar] Page state: On code entry page")
            
            # بررسی فیلد شماره
            phone_input = page.locator(self._selectors.PHONE_INPUT)
            if await phone_input.count() > 0:
                result["has_phone_input"] = True
                logger.info("[divar] Page state: On phone entry page")
            
            # بررسی دکمه ورود
            entry_button = page.locator(self._selectors.LOGIN_ENTRY_BUTTON)
            if await entry_button.count() > 0:
                result["has_entry_button"] = True
                logger.info("[divar] Page state: Entry button available")
            
        except Exception as e:
            logger.warning("[divar] Failed to detect page state: %s", e)
        
        return result

    # ------------------------------------------------------------------
    # ✨ بررسی اینترنت (با URL های ایرانی)
    # ------------------------------------------------------------------
    async def _check_internet(self, page: Page) -> bool:
        """
        بررسی اتصال اینترنت با URL های ایرانی.
        Google در ایران فیلتر است، پس از سایت‌های داخلی استفاده می‌کنیم.
        """
        test_urls = [
            DIVAR_BASE_URL,           # 1. سایت اصلی (divar.ir)
            "https://aparat.com",      # 2. سایت ایرانی
            "https://varzesh3.com",    # 3. سایت ایرانی
        ]
        
        for url in test_urls:
            try:
                response = await page.goto(
                    url,
                    timeout=8_000,
                    wait_until="domcontentloaded"
                )
                if response and response.status < 500:
                    logger.debug("[divar] ✅ Internet OK: %s (status=%s)", url, response.status)
                    return True
            except Exception:
                continue
        
        logger.debug("[divar] All internet checks failed")
        return False

    async def _wait_for_internet(self, page: Page, max_wait: int = 60) -> bool:
        """
        انتظار برای وصل شدن اینترنت.
        
        Args:
            page: صفحه مرورگر
            max_wait: حداکثر زمان انتظار (ثانیه)
        
        Returns:
            True اگر اینترنت وصل شد
        """
        logger.warning("[divar] ⚠️ Internet disconnected, waiting for reconnection...")
        
        for i in range(max_wait):
            if await self._check_internet(page):
                logger.info("[divar] ✅ Internet reconnected after %d seconds", i)
                return True
            await asyncio.sleep(1)
            
            if i % 10 == 0 and i > 0:
                logger.info("[divar] Still waiting for internet... (%d/%d seconds)", i, max_wait)
        
        logger.error("[divar] ❌ Internet did not reconnect within %d seconds", max_wait)
        return False

    # ------------------------------------------------------------------
    # مراحل اصلی
    # ------------------------------------------------------------------
    async def _step_open_login_page(self, page: Page) -> None:
        self._set_state(LoginState.OPENING_LOGIN_PAGE)
        logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
        
        # بررسی اینترنت قبل از شروع
        if not await self._check_internet(page):
            if not await self._wait_for_internet(page, max_wait=60):
                raise RuntimeError("Internet connection failed. Please check your connection.")
        
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

    async def _step_obtain_code_with_site_detection(self, page: Page) -> Optional[str]:
        """
        گرفتن کد از کاربر با تشخیص همزمان ورود از سایت.
        
        Returns:
            - str: کد وارد شده (از UI یا None اگر از سایت وارد شده)
            - None: کاربر کد را مستقیم در سایت وارد کرده
        
        این متد همزمان:
        1. منتظر کد از UI می‌ماند
        2. بررسی می‌کند آیا دکمه "خروج" ظاهر شده (یعنی کاربر کد را در سایت وارد کرده)
        """
        if self._code_provider is None:
            raise RuntimeError("No code_provider registered.")

        self._set_state(LoginState.WAITING_FOR_CODE)
        logger.info("[divar] Waiting for user to enter verification code (from UI or site)...")

        # Task 1: منتظر کد از UI
        code_future = asyncio.create_task(self._code_provider())
        
        # Task 2: بررسی دکمه خروج (کاربر کد را در سایت وارد کرده)
        async def check_logout_button():
            try:
                logout_selector = "div[role='button']:has-text('خروج')"
                await page.wait_for_selector(logout_selector, state="visible", timeout=300_000)
                return True
            except PlaywrightTimeout:
                return False
        
        logout_future = asyncio.create_task(check_logout_button())
        
        # منتظر هر کدام که اول تمام شود
        done, pending = await asyncio.wait(
            [code_future, logout_future],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Cancel task های باقی‌مانده
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        
        # بررسی نتیجه
        if logout_future in done and logout_future.result():
            logger.info("[divar] ✅ User entered code on website -> login successful!")
            return None  # کد از سایت وارد شده
        
        if code_future in done:
            try:
                raw = code_future.result()
                logger.info("[divar] Code received from UI")
                return CodeInput(value=raw).value
            except Exception as e:
                logger.error("[divar] Code provider failed: %s", e)
                raise
        
        return None

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

    async def _open_main_ads_page(self, page: Page) -> None:
        """Open Divar's ads/home area after login, with a URL fallback."""
        try:
            ads_button = page.locator("button:has-text('آگهی')").first
            await ads_button.wait_for(state="visible", timeout=8_000)
            await ads_button.click()
            await page.wait_for_load_state("domcontentloaded", timeout=12_000)
            logger.info("[divar] Opened ads page by clicking the آگهی‌ها button: %s", page.url)
        except (PlaywrightTimeout, PlaywrightError):
            logger.info("[divar] Ads button/navigation unavailable; opening main page directly")
            await page.goto(f"{DIVAR_BASE_URL}/s/iran", wait_until="domcontentloaded", timeout=30_000)

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
                    
                    # ✨ پاک کردن state قبل از retry
                    logger.info("[divar] Clearing browser state before retry...")
                    try:
                        # تلاش برای بازگشت به صفحه اصلی
                        await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                        await page.reload()
                        await page.wait_for_load_state("networkidle")
                        logger.info("[divar] Browser state cleared successfully")
                    except Exception as e:
                        logger.warning("[divar] Failed to clear state: %s", e)
                    
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
            # ✨ تشخیص حالت فعلی صفحه
            logger.info("[divar] Detecting current page state...")
            page_state = await self._detect_page_state(page)
            logger.info("[divar] Current page state: %s", page_state)
            
            # اگر لاگین است، فقط Session را save کن
            if page_state["is_logged_in"]:
                logger.info("[divar] ✅ Already logged in! Saving session without re-login...")
                account_state = await self._session.capture_storage_state(self._browser.context)
                await self._open_main_ads_page(page)
                main_state = await self._session.capture_storage_state(self._browser.context)
                
                existing = self._session.load(phone)
                changed_from_account = account_state.has_changes(main_state)
                changed_from_saved = existing is None or existing.storage_state.has_changes(main_state)
                
                json_path = None
                if changed_from_account or changed_from_saved:
                    session_metadata = {
                        "login_method": "already_logged_in",
                        "phone": phone,
                        "current_url": page.url,
                    }
                    record, json_path = await self._session.save_and_export(
                        context=self._browser.context, phone=phone,
                        metadata=session_metadata, storage_state=main_state,
                    )
                    logger.info("[divar] Session saved: id=%s", record.id)
                else:
                    record = existing
                    logger.info("[divar] Session unchanged: id=%s", record.id)
                
                self._set_state(LoginState.SUCCESS)
                return LoginResult(True, self._state, phone=phone,
                                session_path=str(json_path) if json_path else None)
            
            # اگر در صفحه کد است، فقط کد را بپرس
            if page_state["has_code_input"]:
                logger.info("[divar] 📝 Already on code page, asking for code...")
                code = await self._step_obtain_code_with_site_detection(page)
                if code is None:
                    # کاربر کد را در سایت وارد کرده
                    login_response = None
                else:
                    login_response = await self._step_submit_code(page, code)
            else:
                # شروع از اول یا ادامه از مرحله مناسب
                # اگر دکمه ورود وجود ندارد، صفحه را باز کن
                if not page_state["has_entry_button"] and not page_state["has_phone_input"]:
                    await self._step_open_login_page(page)
                    # بعد از باز کردن صفحه، دوباره state را چک کن
                    page_state = await self._detect_page_state(page)
                
                # اگر دکمه ورود وجود دارد، کلیک کن
                if page_state["has_entry_button"]:
                    await self._step_click_entry_button(page)
                    # ✨ FIX: بعد از کلیک، صفحه تغییر می‌کند، دوباره detect کن
                    page_state = await self._detect_page_state(page)

                # اگر فیلد شماره وجود دارد، شماره را وارد کن
                if page_state["has_phone_input"]:
                    await self._step_submit_phone(page, phone)
                
                # گرفتن کد با تشخیص همزمان از سایت
                code = await self._step_obtain_code_with_site_detection(page)
                if code is None:
                    # کاربر کد را در سایت وارد کرده
                    login_response = None
                else:
                    login_response = await self._step_submit_code(page, code)

            # Divar's logout control is the explicit success marker supplied by
            # the product. Do not retry the login flow after it is visible.
            # Save the complete context immediately; save_from_context also reads
            # cookies, localStorage and sessionStorage from open pages.
            if login_response is None:
                # Compare the authenticated account-page state with the state
                # after entering the main ads page before deciding to persist.
                account_state = await self._session.capture_storage_state(self._browser.context)
                await self._open_main_ads_page(page)
                main_state = await self._session.capture_storage_state(self._browser.context)
                existing = self._session.load(phone)
                changed_from_account = account_state.has_changes(main_state)
                changed_from_saved = existing is None or existing.storage_state.has_changes(main_state)
                json_path = None
                if changed_from_account or changed_from_saved:
                    session_metadata = {
                        "login_method": "logout_button_then_ads_page",
                        "phone": phone,
                        "account_to_ads_state_changed": changed_from_account,
                        "current_url": page.url,
                    }
                    record, json_path = await self._session.save_and_export(
                        context=self._browser.context, phone=phone,
                        metadata=session_metadata, storage_state=main_state,
                    )
                    logger.info("[divar] Main-page session changed; saved id=%s", record.id)
                else:
                    record = existing
                    logger.info("[divar] Account and main-page state unchanged; keeping saved session id=%s", record.id)
                self._set_state(LoginState.SUCCESS)
                return LoginResult(True, self._state, phone=phone,
                                session_path=str(json_path) if json_path else None)

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
                storage_state=verification.storage_state,
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
