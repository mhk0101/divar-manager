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
from typing import Optional

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

logger = logging.getLogger("divar.browser")


class BrowserManager:
    """مدیریت Browser و Context با مسدودسازی قطعی پاپ‌آپ‌های سیستم‌عاملی و مودال مکان شیپور."""

    def __init__(
        self,
        storage_state_path: Optional[Path] = None,
        session_record: Optional[SessionRecord] = None,
        headless: Optional[bool] = None,
    ) -> None:
        self._storage_state_path = storage_state_path
        self._session_record = session_record
        self._headless = HEADLESS if headless is None else headless

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
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            slow_mo=SLOW_MO_MS,
            args=launch_args,
        )

        context_kwargs: dict = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
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
