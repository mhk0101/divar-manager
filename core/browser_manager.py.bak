"""
BrowserManager - مدیریت lifecycle مرورگر و context.

مسئولیت‌ها:
- راه‌اندازی و بستن Browser
- ساخت BrowserContext (با storage_state از SessionRecord در صورت وجود)
- ایجاد Page جدید

این کلاس فعلاً مستقل از Login Manager است و در مراحل بعد نیز
توسط سایر ماژول‌ها استفاده خواهد شد.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import TracebackType
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
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
    """مدیریت Browser و Context با پشتیبانی از context manager."""

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
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            slow_mo=SLOW_MO_MS,
        )

        context_kwargs: dict = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "ignore_https_errors": True,
        }

        # اولویت: SessionRecord (از SQLite)
        if self._session_record:
            context_kwargs["storage_state"] = self._session_record.storage_state.to_playwright()
            logger.info(
                "Using SessionRecord for context: platform=%s phone=%s",
                self._session_record.platform,
                self._session_record.phone,
            )
        # بعدی: فایل storage_state
        elif self._storage_state_path and self._storage_state_path.exists():
            context_kwargs["storage_state"] = str(self._storage_state_path)
            logger.info("Using storage_state file: %s", self._storage_state_path)

        self._context = await self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        self._context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        # گوش دادن به رویدادهای مهم Context
        self._context.on("close", self._on_context_close)

        self._page = await self._context.new_page()
        logger.info("Browser started successfully")
        return self._page

    def _on_context_close(self) -> None:
        logger.info("Browser context closed")

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
        """ایجاد یک Page جدید روی همان Context (مثلاً برای تب جدید)."""
        return await self.context.new_page()

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
