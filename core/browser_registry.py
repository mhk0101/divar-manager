# -*- coding: utf-8 -*-
"""
BrowserRegistry - registry سراسری برای ردیابی تمام BrowserManager های فعال.
امکان بستن تمام مرورگرها با یک دکمه از UI را فراهم می‌کند.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, List

logger = logging.getLogger("divar.browser_registry")


class BrowserRegistry:
    """Singleton برای مدیریت تمام BrowserManager های فعال."""

    _instance: "BrowserRegistry | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._managers: List[Any] = []
        self._close_callbacks: List[Callable[[], None]] = []
        self._registry_lock = threading.Lock()
        self._force_close_event = threading.Event()

    @classmethod
    def instance(cls) -> "BrowserRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def register(self, manager: Any) -> None:
        """ثبت یک BrowserManager فعال."""
        with self._registry_lock:
            if manager not in self._managers:
                self._managers.append(manager)
                logger.debug(
                    "Browser registered. Active count: %d", len(self._managers)
                )

    def unregister(self, manager: Any) -> None:
        """حذف یک BrowserManager از registry."""
        with self._registry_lock:
            if manager in self._managers:
                self._managers.remove(manager)
                logger.debug(
                    "Browser unregistered. Active count: %d", len(self._managers)
                )

    def on_all_closed(self, callback: Callable[[], None]) -> None:
        """ثبت callback برای فراخوانی پس از بسته شدن تمام مرورگرها."""
        self._close_callbacks.append(callback)

    def get_active_count(self) -> int:
        """تعداد مرورگرهای فعال."""
        with self._registry_lock:
            return len(self._managers)

    def is_force_close_requested(self) -> bool:
        """آیا درخواست بستن اجباری مرورگرها از UI داده شده؟"""
        return self._force_close_event.is_set()

    def request_close_all(self, timeout: float = 15.0) -> int:
        """
        بستن تمام مرورگرهای فعال - قابل فراخوانی از هر thread (از جمله GUI).
        تعداد مرورگرهای بسته شده را برمی‌گرداند.
        """
        self._force_close_event.set()

        # کپی لیست manager ها قبل از حلقه
        with self._registry_lock:
            managers = list(self._managers)

        if not managers:
            logger.info("No active browsers to close")
            self._fire_callbacks()
            self._force_close_event.clear()
            return 0

        logger.info("Requesting close for %d browser(s)...", len(managers))

        def _run():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self._close_all_async(managers))
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        closed = 0
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                fut = executor.submit(_run)
                closed = fut.result(timeout=timeout)
        except Exception as e:
            logger.warning("Error while closing browsers: %s", e)

        self._force_close_event.clear()
        self._fire_callbacks()
        logger.info("Closed %d browser(s)", closed)
        return closed

    async def _close_all_async(self, managers: List[Any]) -> int:
        """بستن آسنکرون تمام manager ها."""
        closed = 0
        for mgr in managers:
            try:
                await mgr.stop()
                closed += 1
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
        return closed

    def _fire_callbacks(self) -> None:
        for cb in self._close_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Error in close callback: %s", e)
