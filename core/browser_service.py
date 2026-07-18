# -*- coding: utf-8 -*-
"""
BrowserService - Singleton واقعی برای مدیریت یک نمونه Browser مشترک بین
تمام پلتفرم‌ها (دیوار، شیپور، ...).

معماری:
- یک Thread اختصاصی با یک asyncio event loop ثابت اجرا می‌شود.
- تمام عملیات Playwright (goto, login, validate) باید به عنوان یک
  coroutine واحد از طریق submit() به این loop فرستاده شوند - چون
  اشیاء Playwright (Page/Context/Browser) فقط در همان loop/thread که
  ساخته شده‌اند قابل استفاده‌اند.
- هر platform+phone یک BrowserContext ایزوله (کوکی‌های جدا) می‌گیرد،
  اما همه از یک Browser مشترک استفاده می‌کنند (طبق درخواست بهینه‌سازی).
- بعد از IDLE_TIMEOUT_SECONDS بی‌فعالیتی (بدون عملیات فعال)، Browser به
  صورت خودکار بسته می‌شود.
- SharedBrowserManager یک Adapter سازگار با رابط BrowserManager قدیمی
  است (page, context manager) تا کد LoginManager بدون تغییر کار کند.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import Future as ConcurrentFuture
from contextlib import asynccontextmanager
from typing import Callable, Coroutine, Dict, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
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

logger = logging.getLogger("divar.browser_service")

IDLE_TIMEOUT_SECONDS = 300  # 5 دقیقه - بستن خودکار مرورگر مشترک پس از بی‌فعالیتی


class BrowserService:
    """Singleton مدیریت یک Browser مشترک با Contextهای ایزوله."""

    _instance: Optional["BrowserService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._contexts: Dict[str, BrowserContext] = {}
        self._async_lock: Optional[asyncio.Lock] = None
        self._last_activity = time.time()
        self._active_operations = 0
        self._idle_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "BrowserService":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance._start()
            return cls._instance

    def _start(self) -> None:
        def _runner():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._async_lock = asyncio.Lock()
            self._ready.set()
            try:
                loop.run_forever()
            finally:
                loop.close()

        self._thread = threading.Thread(
            target=_runner, name="BrowserServiceLoop", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=10)

    # ------------------------------------------------------------------
    def submit(self, coro_factory: Callable[[], Coroutine]) -> ConcurrentFuture:
        """اجرای یک coroutine در thread اختصاصی مرورگر (قابل فراخوانی از هر thread)."""
        if self._loop is None:
            raise RuntimeError("BrowserService not started")
        return asyncio.run_coroutine_threadsafe(coro_factory(), self._loop)

    def mark_operation_start(self) -> None:
        self._active_operations += 1
        self._last_activity = time.time()

    def mark_operation_end(self) -> None:
        self._active_operations = max(0, self._active_operations - 1)
        self._last_activity = time.time()

    @property
    def has_active_browser(self) -> bool:
        return self._browser is not None

    # ------------------------------------------------------------------
    async def _ensure_browser(self) -> None:
        self._last_activity = time.time()
        if self._browser is not None:
            return
        logger.info("Launching shared browser instance (headless=%s)", HEADLESS)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=HEADLESS, slow_mo=SLOW_MO_MS,
        )
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.ensure_future(self._idle_watcher())

    async def _idle_watcher(self) -> None:
        while True:
            await asyncio.sleep(15)
            if self._browser is None:
                return
            idle_for = time.time() - self._last_activity
            if self._active_operations == 0 and idle_for > IDLE_TIMEOUT_SECONDS:
                logger.info(
                    "Idle timeout (%ds) reached -> closing shared browser",
                    IDLE_TIMEOUT_SECONDS,
                )
                await self._close_all_internal()
                return

    async def get_or_create_context(
        self, platform: str, session_record: Optional[SessionRecord] = None
    ) -> BrowserContext:
        await self._ensure_browser()
        key = f"{platform}:{session_record.phone if session_record else '_shared'}"
        async with self._async_lock:
            ctx = self._contexts.get(key)
            if ctx is None:
                kwargs: dict = dict(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="fa-IR",
                    timezone_id="Asia/Tehran",
                    ignore_https_errors=True,
                )
                if session_record:
                    kwargs["storage_state"] = session_record.storage_state.to_playwright()
                ctx = await self._browser.new_context(**kwargs)
                ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
                ctx.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
                self._contexts[key] = ctx
                logger.info("Created isolated context: %s", key)
        self._last_activity = time.time()
        return ctx

    async def close_context(self, platform: str, phone: Optional[str] = None) -> None:
        key = f"{platform}:{phone or '_shared'}"
        async with self._async_lock:
            ctx = self._contexts.pop(key, None)
        if ctx:
            try:
                await ctx.close()
            except Exception:
                pass
            logger.info("Closed context: %s", key)

    async def _close_all_internal(self) -> None:
        async with self._async_lock:
            contexts = list(self._contexts.values())
            self._contexts.clear()
        for ctx in contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.info("Shared browser closed completely")
        # متوقف کردن loop برای آزادسازی Thread
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def request_close_all(self, timeout: float = 15.0) -> None:
        """بستن دستی synchronous - قابل فراخوانی از GUI/هر thread دیگر."""
        try:
            # استفاده از coroutine مستقیم به جای lambda شکننده
            async def _close_coro():
                return await self._close_all_internal()
            fut = self.submit(_close_coro)
            fut.result(timeout=timeout)
        except Exception as e:
            logger.warning("Error while closing browser: %s", e)


@asynccontextmanager
async def operation_context(service: "BrowserService"):
    """Context manager آسنکرون: مدت اجرای عملیات را علامت می‌زند تا
    idle-watcher در حین استفاده فعال، مرورگر را نبندد."""
    service.mark_operation_start()
    try:
        yield
    finally:
        service.mark_operation_end()


class SharedBrowserManager:
    """
    Adapter سازگار با رابط BrowserManager قدیمی (page, async context manager)
    اما به‌جای باز کردن Browser جدید، از BrowserService مشترک (Singleton) و
    Context ایزوله استفاده می‌کند. کد LoginManager بدون تغییر کار می‌کند.
    """

    def __init__(self, platform: str, session_record: Optional[SessionRecord] = None):
        self._platform = platform
        self._session_record = session_record
        self._service = BrowserService.instance()
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> Page:
        self._context = await self._service.get_or_create_context(
            self._platform, self._session_record
        )
        self._page = await self._context.new_page()
        return self._page

    async def stop(self) -> None:
        """فقط صفحه بسته می‌شود؛ Context (و کوکی‌ها) و Browser مشترک باقی می‌مانند."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        # بستن Context هم برای پاک‌سازی کوکی‌ها و حافظه
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("start() must be called first")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("start() must be called first")
        return self._context

    async def __aenter__(self) -> "SharedBrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()
