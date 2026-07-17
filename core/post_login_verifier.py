"""
PostLoginVerifier - اعتبارسنجی کامل Login در ۱۰ مرحله.

این ماژول پس از کلیک روی دکمه ورود، مراحل زیر را انجام می‌دهد:

 1. انتظار برای کامل شدن درخواست Login
 2. انتظار برای آماده شدن DOM
 3. انتظار برای پایان درخواست‌های شبکه
 4. بررسی ناپدید شدن صفحه Login
 5. بررسی وجود المنت‌های مخصوص کاربران لاگین
 6. خواندن تمام Cookieها
 7. خواندن تمام LocalStorage
 8. خواندن تمام SessionStorage
 9. استخراج Tokenها
10. اعتبارسنجی نهایی با دسترسی به صفحه protected

تمام انتظارها با Playwright wait_* انجام می‌شوند - هیچ sleep ثابتی وجود ندارد.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Response,
    TimeoutError as PlaywrightTimeout,
)

from core.login_diagnostics import (
    DiagnosticReport,
    FailureReason,
    LoginDiagnostics,
)
from core.session_models import Cookie, SessionStatus, StorageState

logger = logging.getLogger("divar.login.verifier")


@dataclass
class PlatformConfig:
    """تنظیمات platform-specific برای PostLoginVerifier."""

    platform: str
    # URL صفحه protected (فقط کاربران لاگین می‌توانند ببینند)
    protected_url: str
    # Selectorهای المنت‌هایی که نشان‌دهنده لاگین بودن هستند (حداقل یکی کافی است)
    logged_in_markers: List[str] = field(default_factory=list)
    # Selectorهای المنت‌هایی که نشان‌دهنده لاگین نبودن هستند
    logged_out_markers: List[str] = field(default_factory=list)
    # URL الگوهایی که نشان‌دهنده صفحه login هستند
    login_url_patterns: List[str] = field(default_factory=list)
    # الگوهای نام Token در localStorage/cookies
    token_name_patterns: List[str] = field(default_factory=lambda: [
        "token", "access", "refresh", "auth", "jwt", "session",
    ])
    # Timeout برای هر مرحله (میلی‌ثانیه)
    stage_timeout_ms: int = 30_000


@dataclass
class VerificationResult:
    """نتیجه اعتبارسنجی Login."""

    success: bool
    status: SessionStatus
    storage_state: Optional[StorageState] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    stages_passed: List[str] = field(default_factory=list)
    stages_failed: List[str] = field(default_factory=list)
    diagnostic: Optional[DiagnosticReport] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def stage_summary(self) -> str:
        return (
            f"passed={len(self.stages_passed)} "
            f"failed={len(self.stages_failed)}"
        )


class PostLoginVerifier:
    """
    اعتبارسنجی Login در ۱۰ مرحله.

    تمام مراحل با Playwright wait_* انجام می‌شوند و هیچ sleep ثابتی وجود ندارد.
    """

    STAGE_NAMES = [
        "wait_login_response",
        "wait_dom_ready",
        "wait_network_idle",
        "check_login_page_gone",
        "check_logged_in_markers",
        "read_cookies",
        "read_local_storage",
        "read_session_storage",
        "extract_tokens",
        "final_validation",
    ]

    def __init__(
        self,
        config: PlatformConfig,
        diagnostics: Optional[LoginDiagnostics] = None,
    ):
        self._config = config
        self._diagnostics = diagnostics or LoginDiagnostics()
        self._login_response: Optional[Response] = None

    # ------------------------------------------------------------------
    # API اصلی
    # ------------------------------------------------------------------
    async def verify(
        self,
        page: Page,
        context: BrowserContext,
        login_response: Optional[Response] = None,
    ) -> VerificationResult:
        """
        اجرای کامل ۱۰ مرحله اعتبارسنجی.

        Args:
            page: صفحه فعلی
            context: BrowserContext فعلی
            login_response: response درخواست Login (اختیاری، از قبل)
        """
        result = VerificationResult(success=False, status=SessionStatus.UNKNOWN)
        self._login_response = login_response

        stages = [
            ("wait_login_response", self._stage_wait_login_response, page),
            ("wait_dom_ready", self._stage_wait_dom_ready, page),
            ("wait_network_idle", self._stage_wait_network_idle, page),
            ("check_login_page_gone", self._stage_check_login_page_gone, page),
            ("check_logged_in_markers", self._stage_check_logged_in_markers, page),
            ("read_cookies", self._stage_read_cookies, context),
            ("read_local_storage", self._stage_read_local_storage, context),
            ("read_session_storage", self._stage_read_session_storage, page),
            ("extract_tokens", self._stage_extract_tokens, None),
            ("final_validation", self._stage_final_validation, page),
        ]

        storage_state = StorageState()

        for stage_name, stage_func, arg in stages:
            logger.info("[%s] === Stage: %s ===", self._config.platform, stage_name)
            try:
                stage_result = await stage_func(arg, storage_state, result)
                if stage_result is False:
                    # مرحله شکست خورد - Login ناموفق
                    result.stages_failed.append(stage_name)
                    logger.warning(
                        "[%s] ✗ Stage failed: %s",
                        self._config.platform, stage_name,
                    )

                    # تشخیص علت
                    try:
                        diagnostic = await self._diagnostics.analyze_failure(
                            page, stage=stage_name,
                        )
                        result.diagnostic = diagnostic
                    except Exception as e:
                        logger.warning("Diagnostics failed: %s", e)

                    result.status = SessionStatus.INVALID
                    return result

                result.stages_passed.append(stage_name)
                logger.info("[%s] ✓ Stage passed: %s", self._config.platform, stage_name)

            except PlaywrightTimeout as e:
                logger.error("[%s] Timeout at stage %s: %s", self._config.platform, stage_name, e)
                result.stages_failed.append(stage_name)
                result.diagnostic = DiagnosticReport(
                    success=False,
                    reason=FailureReason.NETWORK_TIMEOUT,
                    message=f"Timeout at {stage_name}: {e}",
                    details={"stage": stage_name},
                    retryable=True,
                )
                result.status = SessionStatus.INVALID
                return result

            except PlaywrightError as e:
                logger.error("[%s] Playwright error at %s: %s", self._config.platform, stage_name, e)
                result.stages_failed.append(stage_name)
                result.diagnostic = await self._diagnostics.analyze_failure(
                    page, exception=e, stage=stage_name,
                )
                result.status = SessionStatus.INVALID
                return result

            except Exception as e:
                logger.exception("[%s] Unexpected error at %s", self._config.platform, stage_name)
                result.stages_failed.append(stage_name)
                result.diagnostic = await self._diagnostics.analyze_failure(
                    page, exception=e, stage=stage_name,
                )
                result.status = SessionStatus.INVALID
                return result

        # همه مراحل با موفقیت انجام شدند
        result.success = True
        result.status = SessionStatus.VALID
        result.storage_state = storage_state
        logger.info(
            "[%s] ✅ Login verified successfully (%s)",
            self._config.platform, result.stage_summary(),
        )
        return result

    # ------------------------------------------------------------------
    # مرحله ۱: انتظار برای کامل شدن درخواست Login
    # ------------------------------------------------------------------
    async def _stage_wait_login_response(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """منتظر می‌مانیم تا پاسخ درخواست Login کامل دریافت شود."""
        logger.info("[%s] Waiting for login response to complete...", self._config.platform)

        if self._login_response is not None:
            # اگر response از قبل داریم، فقط منتظر finish آن می‌مانیم
            try:
                await self._login_response.finished()
                status = self._login_response.status
                logger.info("[%s] Login response finished with status %s", self._config.platform, status)
                if status >= 500:
                    result.metadata["login_http_status"] = status
                    logger.warning("[%s] Server error status: %s", self._config.platform, status)
                    return False
                return True
            except PlaywrightError as e:
                logger.warning("[%s] Response finish error: %s", self._config.platform, e)
                # ادامه می‌دهیم - ممکن است response سریع finish شده باشد

        # اگر response نداریم، کمی منتظر network idle می‌مانیم
        page = arg
        try:
            await page.wait_for_load_state("networkidle", timeout=self._config.stage_timeout_ms)
        except PlaywrightTimeout:
            logger.warning("[%s] Network not fully idle, continuing anyway", self._config.platform)

        return True

    # ------------------------------------------------------------------
    # مرحله ۲: انتظار برای آماده شدن DOM
    # ------------------------------------------------------------------
    async def _stage_wait_dom_ready(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """منتظر می‌مانیم تا DOM صفحه آماده شود."""
        page = arg
        logger.info("[%s] Waiting for DOM ready...", self._config.platform)
        await page.wait_for_load_state("domcontentloaded", timeout=self._config.stage_timeout_ms)
        logger.info("[%s] DOM ready at URL: %s", self._config.platform, page.url)
        return True

    # ------------------------------------------------------------------
    # مرحله ۳: انتظار برای پایان درخواست‌های شبکه
    # ------------------------------------------------------------------
    async def _stage_wait_network_idle(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """منتظر می‌مانیم تا تمام درخواست‌های شبکه پایان یابند."""
        page = arg
        logger.info("[%s] Waiting for network idle...", self._config.platform)
        try:
            await page.wait_for_load_state("networkidle", timeout=self._config.stage_timeout_ms)
            logger.info("[%s] Network is idle", self._config.platform)
            return True
        except PlaywrightTimeout:
            # network idle اجباری نیست - ادامه می‌دهیم
            logger.warning(
                "[%s] Network not fully idle after timeout, continuing",
                self._config.platform,
            )
            return True

    # ------------------------------------------------------------------
    # مرحله ۴: بررسی ناپدید شدن صفحه Login
    # ------------------------------------------------------------------
    async def _stage_check_login_page_gone(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """بررسی می‌کنیم که صفحه Login دیگر نمایش داده نشود."""
        page = arg
        logger.info("[%s] Checking login page is gone...", self._config.platform)

        # بررسی URL
        current_url = page.url
        for pattern in self._config.login_url_patterns:
            if pattern in current_url:
                logger.warning(
                    "[%s] Still on login URL: %s (pattern: %s)",
                    self._config.platform, current_url, pattern,
                )
                # بررسی نهایی: شاید URL موقتاً این باشد ولی منتظر redirect هستیم
                try:
                    await page.wait_for_url(
                        lambda url: pattern not in url,
                        timeout=10_000,
                    )
                    logger.info("[%s] URL changed after wait", self._config.platform)
                except PlaywrightTimeout:
                    return False

        # بررسی وجود logged_out_markers
        for selector in self._config.logged_out_markers:
            try:
                locator = page.locator(selector).first
                is_visible = await locator.is_visible()
                if is_visible:
                    logger.warning(
                        "[%s] Logged-out marker visible: %s",
                        self._config.platform, selector,
                    )
                    return False
            except PlaywrightError:
                continue

        logger.info("[%s] Login page is gone", self._config.platform)
        return True

    # ------------------------------------------------------------------
    # مرحله ۵: بررسی وجود المنت‌های مخصوص کاربران لاگین
    # ------------------------------------------------------------------
    async def _stage_check_logged_in_markers(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """بررسی می‌کنیم که المنت‌های مخصوص کاربران لاگین وجود دارند."""
        page = arg

        if not self._config.logged_in_markers:
            logger.info(
                "[%s] No logged-in markers defined, skipping",
                self._config.platform,
            )
            return True

        logger.info(
            "[%s] Checking for logged-in markers (%d patterns)...",
            self._config.platform, len(self._config.logged_in_markers),
        )

        for selector in self._config.logged_in_markers:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=8_000)
                logger.info("[%s] Found logged-in marker: %s", self._config.platform, selector)
                result.metadata["logged_in_marker_found"] = selector
                return True
            except PlaywrightTimeout:
                logger.debug("[%s] Marker not found: %s", self._config.platform, selector)
                continue
            except PlaywrightError as e:
                logger.debug("[%s] Marker check error %s: %s", self._config.platform, selector, e)
                continue

        logger.warning("[%s] No logged-in markers found", self._config.platform)
        return False

    # ------------------------------------------------------------------
    # مرحله ۶: خواندن تمام Cookieها
    # ------------------------------------------------------------------
    async def _stage_read_cookies(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """خواندن تمام Cookieهای مرورگر."""
        context = arg
        logger.info("[%s] Reading cookies...", self._config.platform)

        try:
            state = await context.storage_state()
            raw_cookies = state.get("cookies", [])

            cookies = []
            for c in raw_cookies:
                cookies.append(Cookie(
                    name=c.get("name", ""),
                    value=c.get("value", ""),
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                    expires=c.get("expires"),
                    http_only=c.get("httpOnly", False),
                    secure=c.get("secure", False),
                    same_site=c.get("sameSite", "Lax"),
                ))

            storage.cookies = cookies
            logger.info("[%s] Read %d cookies", self._config.platform, len(cookies))
            result.metadata["cookies_count"] = len(cookies)

            # لاگ cookieهای مهم
            for c in cookies:
                if any(p in c.name.lower() for p in self._config.token_name_patterns):
                    logger.info(
                        "[%s] Found auth cookie: %s (domain=%s)",
                        self._config.platform, c.name, c.domain,
                    )

            return True

        except PlaywrightError as e:
            logger.error("[%s] Failed to read cookies: %s", self._config.platform, e)
            return False

    # ------------------------------------------------------------------
    # مرحله ۷: خواندن تمام LocalStorage
    # ------------------------------------------------------------------
    async def _stage_read_local_storage(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """خواندن تمام LocalStorage."""
        context = arg
        logger.info("[%s] Reading localStorage...", self._config.platform)

        try:
            state = await context.storage_state()
            origins = state.get("origins", [])

            for origin_data in origins:
                origin = origin_data.get("origin", "")
                items = {}
                for item in origin_data.get("localStorage", []):
                    items[item.get("name", "")] = item.get("value", "")
                if items:
                    storage.local_storage[origin] = items
                    logger.info(
                        "[%s] Read %d localStorage items from %s",
                        self._config.platform, len(items), origin,
                    )

            result.metadata["local_storage_origins"] = len(storage.local_storage)
            return True

        except PlaywrightError as e:
            logger.error("[%s] Failed to read localStorage: %s", self._config.platform, e)
            return False

    # ------------------------------------------------------------------
    # مرحله ۸: خواندن تمام SessionStorage
    # ------------------------------------------------------------------
    async def _stage_read_session_storage(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """
        خواندن SessionStorage از طریق اجرای JavaScript در صفحه.

        Playwright.storage_state() SessionStorage را برنمی‌گرداند،
        بنابراین باید با JS آن را استخراج کنیم.
        """
        page = arg
        logger.info("[%s] Reading sessionStorage via JS...", self._config.platform)

        try:
            session_data = await page.evaluate("""
                () => {
                    const data = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        if (key !== null) {
                            data[key] = sessionStorage.getItem(key);
                        }
                    }
                    return {
                        origin: window.location.origin,
                        data: data
                    };
                }
            """)

            origin = session_data.get("origin", "")
            data = session_data.get("data", {})

            if data and origin:
                storage.session_storage[origin] = data
                logger.info(
                    "[%s] Read %d sessionStorage items from %s",
                    self._config.platform, len(data), origin,
                )
            else:
                logger.info("[%s] sessionStorage is empty", self._config.platform)

            result.metadata["session_storage_items"] = len(data)
            return True

        except PlaywrightError as e:
            # SessionStorage ممکن است خالی باشد - خطا نیست
            logger.warning(
                "[%s] Could not read sessionStorage: %s",
                self._config.platform, e,
            )
            return True  # این مرحله بحرانی نیست

    # ------------------------------------------------------------------
    # مرحله ۹: استخراج Tokenها
    # ------------------------------------------------------------------
    async def _stage_extract_tokens(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """استخراج Access Token و Refresh Token از Cookieها و LocalStorage."""
        logger.info("[%s] Extracting tokens...", self._config.platform)

        access_token: Optional[str] = None
        refresh_token: Optional[str] = None

        # جستجو در localStorage
        for origin, data in storage.local_storage.items():
            for key, value in data.items():
                key_lower = key.lower()
                if "access" in key_lower and "token" in key_lower:
                    access_token = value
                    logger.info("[%s] Found access_token in localStorage[%s]", self._config.platform, key)
                elif "refresh" in key_lower and "token" in key_lower:
                    refresh_token = value
                    logger.info("[%s] Found refresh_token in localStorage[%s]", self._config.platform, key)
                elif key_lower in ("token", "jwt", "auth_token"):
                    if not access_token:
                        access_token = value
                        logger.info("[%s] Found token in localStorage[%s]", self._config.platform, key)

        # جستجو در cookies
        for cookie in storage.cookies:
            name_lower = cookie.name.lower()
            if "access" in name_lower and "token" in name_lower:
                if not access_token:
                    access_token = cookie.value
                    logger.info("[%s] Found access_token in cookie %s", self._config.platform, cookie.name)
            elif "refresh" in name_lower and "token" in name_lower:
                if not refresh_token:
                    refresh_token = cookie.value
                    logger.info("[%s] Found refresh_token in cookie %s", self._config.platform, cookie.name)

        result.access_token = access_token
        result.refresh_token = refresh_token

        if access_token:
            logger.info("[%s] Access token extracted", self._config.platform)
        if refresh_token:
            logger.info("[%s] Refresh token extracted", self._config.platform)

        result.metadata["has_access_token"] = access_token is not None
        result.metadata["has_refresh_token"] = refresh_token is not None

        # نبودن token لزوماً به معنی شکست نیست (برخی سایت‌ها فقط از cookie استفاده می‌کنند)
        return True

    # ------------------------------------------------------------------
    # مرحله ۱۰: اعتبارسنجی نهایی با دسترسی به protected page
    # ------------------------------------------------------------------
    async def _stage_final_validation(
        self,
        arg: Any,
        storage: StorageState,
        result: VerificationResult,
    ) -> bool:
        """
        اعتبارسنجی نهایی: دسترسی به یک صفحه protected.

        یک صفحه که فقط کاربران لاگین می‌توانند ببینند را باز می‌کنیم.
        اگر صفحه به درستی بارگذاری شد، Login موفق بوده است.
        """
        page = arg
        logger.info(
            "[%s] Final validation: accessing protected page %s",
            self._config.platform, self._config.protected_url,
        )

        try:
            # رفتن به protected URL
            response = await page.goto(
                self._config.protected_url,
                wait_until="domcontentloaded",
                timeout=self._config.stage_timeout_ms,
            )

            if response is None:
                logger.warning("[%s] No response from protected page", self._config.platform)
                return False

            status = response.status
            logger.info(
                "[%s] Protected page responded with status %s",
                self._config.platform, status,
            )

            # بررسی redirect به login
            await page.wait_for_load_state("networkidle", timeout=15_000)
            final_url = page.url

            for pattern in self._config.login_url_patterns:
                if pattern in final_url:
                    logger.warning(
                        "[%s] Redirected to login: %s",
                        self._config.platform, final_url,
                    )
                    return False

            # بررسی نهایی: logged_out_markers نباید دیده شوند
            for selector in self._config.logged_out_markers:
                try:
                    locator = page.locator(selector).first
                    is_visible = await locator.is_visible()
                    if is_visible:
                        logger.warning(
                            "[%s] Logged-out marker on protected page: %s",
                            self._config.platform, selector,
                        )
                        return False
                except PlaywrightError:
                    continue

            logger.info(
                "[%s] ✅ Final validation passed - protected page accessible",
                self._config.platform,
            )
            result.metadata["protected_page_url"] = final_url
            result.metadata["protected_page_status"] = status
            return True

        except PlaywrightTimeout as e:
            logger.error(
                "[%s] Timeout accessing protected page: %s",
                self._config.platform, e,
            )
            raise
        except PlaywrightError as e:
            logger.error(
                "[%s] Error accessing protected page: %s",
                self._config.platform, e,
            )
            raise
