"""
AutomationTab - تب اتوماسیون دیوار.

ویژگی‌ها:
- نمایش لیست شهرها با قابلیت جستجو
- انتخاب چندگانه شهرها
- ساخت URL دیوار با شهرهای انتخاب شده
- باز کردن سایت دیوار با Session ذخیره شده
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QThreadPool, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QGroupBox,
    QSplitter,
    QTextEdit,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from core.browser_manager import BrowserManager
from core.session_manager import SessionManager
from core.session_models import SessionRecord, SessionStatus

logger = logging.getLogger("divar.automation")

CITIES_FILE = PROJECT_ROOT / "data" / "cities.json"


# ---------------------------------------------------------------------------
# سیگنال‌ها
# ---------------------------------------------------------------------------
class AutomationSignals(QObject):
    status_changed = Signal(str)
    error_occurred = Signal(str)
    finished = Signal(str)
    cities_loaded = Signal(list)


# ---------------------------------------------------------------------------
# Worker برای باز کردن دیوار
# ---------------------------------------------------------------------------
class DivarBrowserWorker(QRunnable):
    """باز کردن سایت دیوار با شهرهای انتخاب شده."""

    def __init__(self, cities_ids: List[int], cities_names: List[str], phone: Optional[str] = None):
        super().__init__()
        self.cities_ids = cities_ids
        self.cities_names = cities_names
        self.phone = phone
        self.signals = AutomationSignals()
        self.setAutoDelete(True)
        self._browser_manager = None

    def request_close(self):
        if self._browser_manager:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), loop
                )
            except Exception:
                pass

    @Slot()
    def run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # ساخت URL - همیشه از cities parameter استفاده کن
            cities_param = ",".join(str(cid) for cid in self.cities_ids)
            url = f"https://divar.ir/s/iran?cities={cities_param}"
            
            self.signals.status_changed.emit(f"🌐 URL: {url}")

            async def _run():
                # بارگذاری Session
                sm = SessionManager(platform="divar")
                record = sm.load(phone=self.phone) if self.phone else sm.load()
                
                bm = BrowserManager(session_record=record)
                self._browser_manager = bm
                
                async with bm:
                    self.signals.status_changed.emit("🔄 در حال باز کردن سایت دیوار...")
                    
                    await bm.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    await bm.page.wait_for_load_state("networkidle")
                    
                    self.signals.status_changed.emit(
                        f"✅ سایت دیوار باز شد!\n"
                        f"URL: {url}\n"
                        f"شهرها: {', '.join(self.cities_names)}\n\n"
                        f"🟢 مرورگر باز است. هر وقت کارتان تمام شد ببندید."
                    )
                    
                    # منتظر بمان تا کاربر مرورگر را ببندد
                    try:
                        await bm.page.wait_for_event("close", timeout=0)
                    except Exception:
                        pass
                
                self.signals.finished.emit(url)

            loop.run_until_complete(_run())

        except Exception as e:
            self.signals.error_occurred.emit(f"خطا: {e}")
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# تب اتوماسیون
# ---------------------------------------------------------------------------
class AutomationTab(QWidget):
    """تب اتوماسیون - انتخاب شهر و باز کردن دیوار."""

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cities: List[dict] = []
        self._current_worker: Optional[DivarBrowserWorker] = None
        self._setup_ui()
        self._load_cities()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(15)

        # عنوان
        title = QLabel("🤖 اتوماسیون دیوار")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "شهرهای مورد نظر خود را انتخاب کنید و دکمه «شروع» را بزنید.\n"
            "سایت دیوار با شهرهای انتخاب شده باز می‌شود."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)

        # Splitter برای لیست و جزئیات
        splitter = QSplitter(Qt.Vertical)

        # --- بخش جستجو و لیست شهرها ---
        search_group = QGroupBox("🏙️ انتخاب شهرها")
        search_layout = QVBoxLayout(search_group)

        # جستجو
        search_row = QHBoxLayout()
        search_label = QLabel("🔍 جستجو:")
        search_label.setStyleSheet("font-weight: bold;")
        search_row.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("نام شهر را وارد کنید... (مثال: تهران)")
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #A62626;
            }
        """)
        self.search_input.textChanged.connect(self._filter_cities)
        search_row.addWidget(self.search_input)

        self.selected_count = QLabel("0 شهر انتخاب شده")
        self.selected_count.setStyleSheet("color: #A62626; font-weight: bold; font-size: 12px;")
        search_row.addWidget(self.selected_count)

        search_layout.addLayout(search_row)

        # لیست شهرها
        self.city_list = QListWidget()
        self.city_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.city_list.setMinimumHeight(200)
        self.city_list.setStyleSheet("""
            QListWidget {
                border: 2px solid #ddd;
                border-radius: 8px;
                background: white;
                font-size: 13px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #A62626;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        self.city_list.itemSelectionChanged.connect(self._update_selection_info)
        search_layout.addWidget(self.city_list)

        # دکمه‌های انتخاب
        select_row = QHBoxLayout()
        
        self.select_all_btn = QPushButton("✅ انتخاب همه")
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.select_all_btn.clicked.connect(self._select_all)
        select_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("❌ حذف انتخاب")
        self.deselect_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        select_row.addWidget(self.deselect_all_btn)

        self.reload_btn = QPushButton("🔄 بارگذاری مجدد شهرها")
        self.reload_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #138496; }
        """)
        self.reload_btn.clicked.connect(self._load_cities)
        select_row.addWidget(self.reload_btn)

        search_layout.addLayout(select_row)
        splitter.addWidget(search_group)

        # --- بخش اطلاعات و شروع ---
        info_group = QGroupBox("📋 اطلاعات")
        info_layout = QVBoxLayout(info_group)

        # URL نمایشی
        self.url_display = QTextEdit()
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(80)
        self.url_display.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 2px solid #ddd;
                border-radius: 6px;
                padding: 8px;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.url_display.setPlaceholderText("URL دیوار اینجا نمایش داده می‌شود...")
        info_layout.addWidget(self.url_display)

        # دکمه شروع
        self.start_btn = QPushButton("🚀 شروع - باز کردن دیوار")
        self.start_btn.setMinimumHeight(50)
        start_font = QFont()
        start_font.setPointSize(14)
        start_font.setBold(True)
        self.start_btn.setFont(start_font)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #A62626;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #8B1E1E;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setEnabled(False)
        info_layout.addWidget(self.start_btn)

        # دکمه بستن مرورگر
        self.close_btn = QPushButton("🔴 بستن مرورگر")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.close_btn.clicked.connect(self._close_browser)
        info_layout.addWidget(self.close_btn)

        splitter.addWidget(info_group)
        layout.addWidget(splitter)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    # ------------------------------------------------------------------
    # بارگذاری شهرها
    # ------------------------------------------------------------------
    def _load_cities(self):
        """بارگذاری لیست شهرها از فایل JSON."""
        if not CITIES_FILE.exists():
            self._log("WARNING", "فایل شهرها پیدا نشد. لطفاً fetch_cities.py را اجرا کنید.")
            item = QListWidgetItem("⚠️ فایل شهرها پیدا نشد! ابتدا fetch_cities.py را اجرا کنید.")
            item.setFlags(Qt.NoItemFlags)
            self.city_list.clear()
            self.city_list.addItem(item)
            return

        try:
            with open(CITIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._cities = data.get("cities", [])
            self._log("INFO", f"[اتوماسیون] Loaded {len(self._cities)} cities")

            self._populate_city_list(self._cities)

        except Exception as e:
            self._log("ERROR", f"[اتوماسیون] خطا در بارگذاری شهرها: {e}")

    def _populate_city_list(self, cities: List[dict]):
        """پر کردن لیست شهرها."""
        self.city_list.clear()

        if not cities:
            item = QListWidgetItem("— هیچ شهری پیدا نشد —")
            item.setFlags(Qt.NoItemFlags)
            self.city_list.addItem(item)
            return

        for city in cities:
            city_id = city.get("id", "")
            name = city.get("name", "")
            slug = city.get("slug", "")

            text = f"{name}"
            if slug:
                text += f"  ({slug})"
            text += f"  [ID: {city_id}]"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, city)
            self.city_list.addItem(item)

    def _filter_cities(self, text: str):
        """فیلتر کردن لیست شهرها بر اساس متن جستجو."""
        if not text.strip():
            self._populate_city_list(self._cities)
            return

        filtered = [
            city for city in self._cities
            if text.lower() in city.get("name", "").lower()
            or text.lower() in city.get("slug", "").lower()
        ]
        self._populate_city_list(filtered)

    def _select_all(self):
        """انتخاب همه شهرهای نمایش داده شده."""
        self.city_list.selectAll()

    def _deselect_all(self):
        """حذف انتخاب همه."""
        self.city_list.clearSelection()

    def _update_selection_info(self):
        """بروزرسانی اطلاعات انتخاب."""
        selected = self.city_list.selectedItems()
        count = len(selected)
        self.selected_count.setText(f"{count} شهر انتخاب شده")
        self.start_btn.setEnabled(count > 0)

        # بروزرسانی URL
        self._update_url_display()

    def _update_url_display(self):
        """بروزرسانی نمایش URL."""
        selected = self.city_list.selectedItems()
        if not selected:
            self.url_display.clear()
            return

        cities_data = [item.data(Qt.UserRole) for item in selected]
        cities_ids = [c.get("id", 0) for c in cities_data]
        cities_names = [c.get("name", "") for c in cities_data]

        # همیشه از cities parameter استفاده کن
        cities_param = ",".join(str(cid) for cid in cities_ids)
        url = f"https://divar.ir/s/iran?cities={cities_param}"

        self.url_display.setPlainText(
            f"🌐 {url}\n\n"
            f"🏙️ شهرها: {', '.join(cities_names)}"
        )

    # ------------------------------------------------------------------
    # شروع
    # ------------------------------------------------------------------
    def _on_start(self):
        """شروع - باز کردن دیوار با شهرهای انتخاب شده."""
        selected = self.city_list.selectedItems()
        if not selected:
            QMessageBox.information(
                self, "انتخاب شهر",
                "لطفاً حداقل یک شهر انتخاب کنید.",
            )
            return

        cities_data = [item.data(Qt.UserRole) for item in selected]
        cities_ids = [c.get("id", 0) for c in cities_data]
        cities_names = [c.get("name", "") for c in cities_data]

        self._log(
            "INFO",
            f"[اتوماسیون] شروع: {len(cities_ids)} شهر - {', '.join(cities_names)}",
        )

        # بارگذاری Session دیوار
        sm = SessionManager(platform="divar")
        record = sm.load()
        phone = record.phone if record else None

        self.start_btn.setEnabled(False)
        self.start_btn.setText("⏳ در حال باز کردن دیوار...")

        worker = DivarBrowserWorker(cities_ids, cities_names, phone)
        worker.signals.status_changed.connect(self._on_status_changed)
        worker.signals.error_occurred.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        self._current_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _on_status_changed(self, status: str):
        self._log("INFO", f"[اتوماسیون] {status}")

    @Slot(str)
    def _on_error(self, error: str):
        self._log("ERROR", f"[اتوماسیون] {error}")
        self.start_btn.setEnabled(True)
        self.start_btn.setText("🚀 شروع - باز کردن دیوار")
        self._current_worker = None
        QMessageBox.critical(self, "خطا", f"خطا:\n{error}")

    @Slot(str)
    def _on_finished(self, url: str):
        self._log("INFO", f"[اتوماسیون] تمام شد: {url}")
        self.start_btn.setEnabled(True)
        self.start_btn.setText("🚀 شروع - باز کردن دیوار")
        self._current_worker = None

    def _close_browser(self):
        """بستن مرورگر."""
        if self._current_worker:
            self._current_worker.request_close()

        try:
            from ui.platform_tab import _force_close_all_browsers
            _force_close_all_browsers()
        except Exception:
            pass

        self._log("INFO", "[اتوماسیون] درخواست بستن مرورگر")
