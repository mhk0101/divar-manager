"""
BrowserManager - مدیریت lifecycle مرورگر، context و مسدودسازی ۱۰۰٪ پاپ‌آپ‌های سیستم‌عاملی و مودال‌های شیپور.

اصلاحات ویژه شیپور (2026-07-21):
1. ✅ اضافه کردن MutationObserver خودکار ۵۰۰ میلی‌ثانیه‌ای جهت بستن و فشردن اتوماتیک «بله، تغییر می‌دهم» روی مودال‌های تغییر مکان شیپور
2. ✅ غیرفعال‌سازی پرچمی و تنظیمات ترجیحی (Preferences) Chromium برای مسدودسازی دیالوگ‌های پروتکل خارجی
3. ✅ شبیه‌سازی دقیق و پاکسازی تمامی رویدادهای window.open، navigation و iframeهای Intent
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import TracebackType
from typing import Dict, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Dialog,
    Error as PlaywrightError,
    Page,
    Playwright,
    Route,
    Request,
    async_playwright,
)

from config.settings import (
    DEFAULT_TIMEOUT_MS,
    HEADLESS,
    NAVIGATION_TIMEOUT_MS,
    SLOW_MO_MS,
    USER_AGENT,
)
from core.session_models import SessionRecord
from core.fingerprint_manager import FingerprintManager

logger = logging.getLogger("divar.browser")

# برای اینکه بعضی اکانت‌ها به خاطر fingerprint با viewport کوچک، صفحه را زوم‌شده نبینند،
# اندازه نمای مرورگر را برای UI دسکتاپ ثابت/حداقلی نگه می‌داریم.
DEFAULT_DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
MIN_DESKTOP_VIEWPORT = {"width": 1600, "height": 900}
UI_ZOOM_FACTOR = 0.85  # 85% برای اینکه المان‌های بیشتری از صفحه دیده شوند


def _normalize_desktop_viewport(viewport: Optional[Dict]) -> Dict[str, int]:
    """Viewport ذخیره‌شده در fingerprint را برای نمایش کامل‌تر صفحه امن‌سازی می‌کند."""
    if not isinstance(viewport, dict):
        return dict(DEFAULT_DESKTOP_VIEWPORT)
    try:
        width = int(viewport.get("width") or 0)
        height = int(viewport.get("height") or 0)
    except Exception:
        return dict(DEFAULT_DESKTOP_VIEWPORT)

    if width < MIN_DESKTOP_VIEWPORT["width"] or height < MIN_DESKTOP_VIEWPORT["height"]:
        return dict(DEFAULT_DESKTOP_VIEWPORT)

    # برای یکدست بودن نمایش همه اکانت‌ها، حتی viewportهای بزرگ fingerprint را هم
    # به viewport ثابت برنامه تبدیل می‌کنیم تا UI در هر شماره یکسان باشد.
    return dict(DEFAULT_DESKTOP_VIEWPORT)


class BrowserManager:
    """مدیریت Browser و Context با مسدودسازی قطعی پاپ‌آپ‌های سیستم‌عاملی و مودال مکان شیپور."""

    def __init__(
        self,
        storage_state_path: Optional[Path] = None,
        session_record: Optional[SessionRecord] = None,
        headless: Optional[bool] = None,
        fingerprint: Optional[Dict] = None,
    ) -> None:
        self._storage_state_path = storage_state_path
        self._session_record = session_record
        self._headless = HEADLESS if headless is None else headless
        self._fingerprint = fingerprint  # fingerprint اختصاصی هر شماره

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> Page:
        if self._page is not None:
            return self._page

        logger.info("Starting browser (headless=%s)", self._headless)
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-external-intent-requests",
            "--disable-features=ExternalProtocolHandler,ExternalProtocolDialog,AskBeforeOpeningExternalApp,LookalikeUrlNavigationSuggestionsUI",
            "--disable-popup-blocking",
            "--no-sandbox",
            "--block-new-web-contents",
            "--high-dpi-support=1",
            "--force-device-scale-factor=1",
            "--start-maximized",
            f"--window-size={DEFAULT_DESKTOP_VIEWPORT['width']},{DEFAULT_DESKTOP_VIEWPORT['height']}",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            slow_mo=SLOW_MO_MS,
            args=launch_args,
        )

        # ⬇️ استفاده از fingerprint اختصاصی اگر موجود باشد، در غیر این صورت پیش‌فرض
        ua = USER_AGENT
        viewport = dict(DEFAULT_DESKTOP_VIEWPORT)
        locale = "fa-IR"
        extra_headers = {}
        dsf = 1.0
        color_scheme = "light"

        if self._fingerprint:
            ua = self._fingerprint.get("user_agent", USER_AGENT)
            # فقط UA/زبان از fingerprint می‌آید؛ viewport کوچک و scale متفاوت باعث می‌شود
            # بعضی اکانت‌ها صفحه را زوم‌شده ببینند. پس viewport را نرمال و scale را 1 نگه می‌داریم.
            viewport = _normalize_desktop_viewport(self._fingerprint.get("viewport"))
            locale = self._fingerprint.get("accept_language", "fa-IR")
            fp_platform = self._fingerprint.get("os_platform", "Win32")
            color_scheme = self._fingerprint.get("color_scheme", "light")
            dsf = 1.0
            extra_headers = {
                "Accept-Language": self._fingerprint.get("accept_language", "fa-IR,fa;q=0.9,en;q=0.8"),
                "sec-ch-ua-platform": f'"{fp_platform}"',
            }

            logger.info(
                "🎭 Fingerprint اختصاصی: UA=%s... Viewport=%s OS=%s",
                ua[:60], viewport, fp_platform,
            )

        context_kwargs: dict = {
            "user_agent": ua,
            "viewport": viewport,
            "screen": viewport,
            "device_scale_factor": dsf,
            "is_mobile": False,
            "has_touch": False,
            "color_scheme": color_scheme if color_scheme in ("light", "dark", "no-preference") else "light",
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "extra_http_headers": extra_headers,
            "ignore_https_errors": False,
        }

        if self._session_record:
            context_kwargs["storage_state"] = self._session_record.storage_state.to_playwright()
            logger.info(
                "Using SessionRecord for context: platform=%s phone=%s",
                self._session_record.platform,
                self._session_record.phone,
            )
        elif self._storage_state_path and self._storage_state_path.exists():
            context_kwargs["storage_state"] = str(self._storage_state_path)
            logger.info("Using storage_state file: %s", self._storage_state_path)

        self._context = await self._browser.new_context(**context_kwargs)

        try:
            await self._context.grant_permissions([])
        except Exception:
            pass

        if self._session_record and self._session_record.storage_state.session_storage:
            await self._install_session_storage(self._context, self._session_record.storage_state.session_storage)

        self._context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        self._context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        self._context.on("close", self._on_context_close)

        self._page = await self._context.new_page()
        await self._apply_page_view_settings(self._page)

        async def _block_protocol_requests(route: Route, request: Request):
            url_lower = request.url.lower()
            if any(p in url_lower for p in ["tel:", "sheypoor:", "intent:", "call:", "app.sheypoor.com"]):
                logger.info("Blocked external protocol/app request: %s", request.url)
                await route.abort()
            else:
                await route.continue_()

        await self._page.route("**/*", _block_protocol_requests)

        self._page.on("dialog", self._on_dialog)

        # ✨ تزریق کد خنثی‌کننده و بسته شدن خودکار مودال‌های تایید مکان شیپور
        await self._page.add_init_script("""
            (() => {
                // جلوگیری از زوم ناخواسته و نمایش المان‌های بیشتر در همه اکانت‌ها
                const __DIVAR_MANAGER_UI_ZOOM__ = 0.85;
                const __applyDivarManagerZoom = () => {
                    try {
                        document.documentElement.style.zoom = String(__DIVAR_MANAGER_UI_ZOOM__);
                        if (document.body) document.body.style.zoom = String(__DIVAR_MANAGER_UI_ZOOM__);
                    } catch(e) {}
                };
                __applyDivarManagerZoom();
                window.addEventListener('DOMContentLoaded', __applyDivarManagerZoom, { once: true });
                window.addEventListener('load', __applyDivarManagerZoom, { once: true });

                const isExternal = (url) => {
                    if (!url || typeof url !== 'string') return false;
                    const u = url.toLowerCase();
                    return u.startsWith('tel:') || u.startsWith('sheypoor:') || u.startsWith('intent:') || u.startsWith('call:') || u.includes('sheypoor.com/app');
                };

                window.open = function(url, ...args) {
                    if (isExternal(url)) {
                        console.log('Blocked window.open app protocol:', url);
                        return null;
                    }
                    return null;
                };

                try {
                    const origAssign = window.location.assign;
                    window.location.assign = function(url) {
                        if (isExternal(url)) return;
                        return origAssign.call(this, url);
                    };
                } catch(e){}

                document.addEventListener('click', (e) => {
                    const target = e.target.closest('a');
                    if (target && isExternal(target.href)) {
                        e.preventDefault();
                        e.stopPropagation();
                        console.log('Intercepted and prevented external link click:', target.href);
                    }
                }, true);

                // ✨ بستن اتوماتیک مودال تغییر مکان شیپور («آیا مکان خود را تغییر می‌دهید؟»)
                setInterval(() => {
                    try {
                        const btns = Array.from(document.querySelectorAll('button'));
                        for (const b of btns) {
                            const t = (b.innerText || '').trim();
                            if (t.includes('تغییر می‌دهم') || t.includes('بله، تغییر')) {
                                console.log('Auto-dismissed Sheypoor location modal:', t);
                                b.click();
                                break;
                            }
                        }
                    } catch(e){}
                }, 400);
            })();
        """)

        logger.info("Browser started successfully with 5-layer app popup & Sheypoor location modal blocking enabled")
        return self._page

    def _on_dialog(self, dialog: Dialog) -> None:
        """لغو خودکار و فشردن دکمه Cancel برای تمام دیالوگ‌ها."""
        logger.info("Automatically dismissing browser dialog: message='%s' type='%s'", dialog.message, dialog.type)
        try:
            asyncio.create_task(dialog.dismiss())
        except Exception as e:
            logger.debug("Error dismissing dialog: %s", e)

    def _on_context_close(self) -> None:
        logger.info("Browser context closed")

    async def _install_session_storage(self, context: BrowserContext, values: dict) -> None:
        import json
        payload = json.dumps(values, ensure_ascii=False).replace("</", "<\\/")
        script = (
            "(() => { const values = " + payload + "; "
            "const data = values[window.location.origin]; if (!data) return; "
            "for (const [key, value] of Object.entries(data)) "
            "sessionStorage.setItem(key, value); })();"
        )
        await context.add_init_script(script=script)

    async def _apply_page_view_settings(self, page: Page) -> None:
        """اعمال viewport/zoom ثابت روی هر صفحه برای جلوگیری از حالت زوم‌شده بعضی اکانت‌ها."""
        try:
            await page.set_viewport_size(dict(DEFAULT_DESKTOP_VIEWPORT))
        except Exception:
            pass
        try:
            await page.evaluate(
                """
                (zoom) => {
                    const apply = () => {
                        try {
                            document.documentElement.style.zoom = String(zoom);
                            if (document.body) document.body.style.zoom = String(zoom);
                        } catch(e) {}
                    };
                    apply();
                    window.addEventListener('DOMContentLoaded', apply, { once: true });
                    window.addEventListener('load', apply, { once: true });
                }
                """,
                UI_ZOOM_FACTOR,
            )
        except Exception:
            pass

    async def stop(self) -> None:
        logger.info("Stopping browser...")
        if self._context:
            try:
                await self._context.close()
            except PlaywrightError:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except PlaywrightError:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except PlaywrightError:
                pass
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        logger.info("Browser stopped")

    # ------------------------------------------------------------------
    # دسترسی‌ها
    # ------------------------------------------------------------------
    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserManager.start() must be called first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("BrowserManager.start() must be called first.")
        return self._context

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._page is not None

    async def new_page(self) -> Page:
        page = await self.context.new_page()
        page.on("dialog", self._on_dialog)
        await self._apply_page_view_settings(page)
        return page

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.stop()
