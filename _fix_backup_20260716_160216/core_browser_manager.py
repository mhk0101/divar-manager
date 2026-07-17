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


# ============================================================
# [PATCHED] Phone Number List Selector
# ============================================================
def show_phone_number_selector(phone_numbers: list, parent=None):
    """
    نمایش لیست شماره‌ها برای انتخاب کاربر
    phone_numbers: لیست شماره‌های موبایل (رشته)
    برمیگرداند: شماره انتخاب شده یا None
    """
    try:
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
            QListWidgetItem, QPushButton, QLabel, QApplication
        )
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont

        if not phone_numbers:
            print("[!] لیست شماره خالی است")
            return None

        dialog = QDialog(parent)
        dialog.setWindowTitle("انتخاب شماره تماس")
        dialog.setMinimumWidth(380)
        dialog.setMinimumHeight(300)
        dialog.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # عنوان
        title_label = QLabel(f"📞 {len(phone_numbers)} شماره یافت شد - یکی را انتخاب کنید:")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # لیست شماره‌ها
        list_widget = QListWidget()
        list_widget.setAlternatingRowColors(True)
        list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 6px;
                font-size: 14px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #e8f4fd;
            }
        """)

        for i, num in enumerate(phone_numbers, 1):
            item = QListWidgetItem(f"  {i}.  {num}")
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            list_widget.addItem(item)

        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)

        list_widget.doubleClicked.connect(dialog.accept)
        layout.addWidget(list_widget)

        # دکمه‌ها
        btn_layout = QHBoxLayout()

        btn_cancel = QPushButton("❌ انصراف")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.setStyleSheet("QPushButton { background:#e74c3c; color:white; border-radius:5px; font-size:13px; }")
        btn_cancel.clicked.connect(dialog.reject)

        btn_ok = QPushButton("✅ انتخاب")
        btn_ok.setMinimumHeight(36)
        btn_ok.setDefault(True)
        btn_ok.setStyleSheet("QPushButton { background:#27ae60; color:white; border-radius:5px; font-size:13px; }")
        btn_ok.clicked.connect(dialog.accept)

        btn_copy_all = QPushButton("📋 کپی همه")
        btn_copy_all.setMinimumHeight(36)
        btn_copy_all.setStyleSheet("QPushButton { background:#2980b9; color:white; border-radius:5px; font-size:13px; }")

        def copy_all():
            clipboard = QApplication.clipboard()
            clipboard.setText("\n".join(phone_numbers))
            btn_copy_all.setText("✅ کپی شد!")

        btn_copy_all.clicked.connect(copy_all)

        btn_layout.addWidget(btn_copy_all)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        result = dialog.exec()

        if result == QDialog.Accepted and list_widget.currentItem():
            selected_text = list_widget.currentItem().text().strip()
            # جدا کردن شماره از متن لیست
            parts = selected_text.split(".")
            phone = parts[-1].strip() if len(parts) > 1 else selected_text
            return phone
        return None

    except ImportError:
        # اگر PySide6 نبود، از ترمینال استفاده کن
        return show_phone_selector_terminal(phone_numbers)


def show_phone_selector_terminal(phone_numbers: list):
    """نسخه ترمینالی انتخاب شماره"""
    if not phone_numbers:
        return None
    print("\n" + "="*40)
    print("📞 شماره‌های یافت شده:")
    print("="*40)
    for i, num in enumerate(phone_numbers, 1):
        print(f"  {i}. {num}")
    print("="*40)
    while True:
        try:
            choice = input(f"شماره مورد نظر را وارد کنید (1-{len(phone_numbers)}) یا 0 برای انصراف: ")
            idx = int(choice)
            if idx == 0:
                return None
            if 1 <= idx <= len(phone_numbers):
                return phone_numbers[idx - 1]
            print(f"[!] عدد بین 1 تا {len(phone_numbers)} وارد کنید")
        except ValueError:
            print("[!] لطفاً یک عدد وارد کنید")
# ============================================================

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
