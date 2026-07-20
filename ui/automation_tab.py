"""
AutomationTab - تب اتوماسیون دیوار.

ویژگی‌ها:
- نمایش لیست شهرها با قابلیت جستجو
- انتخاب چندگانه شهرها
- انتخاب دسته‌بندی (اختیاری)
- ساخت URL دیوار با شهرها و دسته‌بندی انتخاب شده
- باز کردن سایت دیوار با Session ذخیره شده
- بستن مرورگر به صورت اختصاصی برای تب اتوماسیون
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

logger = logging.getLogger("divar.automation")

CITIES_FILE = PROJECT_ROOT / "data" / "cities.json"
CATEGORIES_FILE = PROJECT_ROOT / "data" / "categories.json"


# ---------------------------------------------------------------------------
# سیگنال‌ها
# ---------------------------------------------------------------------------
class AutomationSignals(QObject):
    status_changed = Signal(str)
    error_occurred = Signal(str)
    finished = Signal(str)


# ---------------------------------------------------------------------------
# Worker برای باز کردن دیوار
# ---------------------------------------------------------------------------
class DivarBrowserWorker(QRunnable):
    """باز کردن سایت دیوار با شهرها و دسته‌بندی انتخاب شده."""

    def __init__(self, url: str, cities_names: List[str], category_name: str, phone: Optional[str] = None):
        super().__init__()
        self.url = url
        self.cities_names = cities_names
        self.category_name = category_name
        self.phone = phone
        self.signals = AutomationSignals()
        self.setAutoDelete(True)
        self._browser_manager: Optional[BrowserManager] = None
        self._loop = None
        self._is_active = True

    def is_browser_running(self) -> bool:
        if not self._is_active:
            return False
        if self._browser_manager is not None:
            return self._browser_manager.is_running
        return True

    def request_close(self):
        if self._loop is not None and self._browser_manager is not None:
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), self._loop
                )
            except Exception:
                pass

    @Slot()
    def run(self):
        self._is_active = True
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            self.signals.status_changed.emit(f"🌐 URL: {self.url}")

            async def _run():
                sm = SessionManager(platform="divar")
                record = sm.load(phone=self.phone) if self.phone else sm.load()

                bm = BrowserManager(session_record=record)
                self._browser_manager = bm

                async with bm:
                    self.signals.status_changed.emit("🔄 در حال باز کردن سایت دیوار...")

                    await bm.page.goto(self.url, wait_until="domcontentloaded", timeout=30_000)
                    await bm.page.wait_for_load_state("networkidle")

                    self.signals.status_changed.emit(
                        f"✅ سایت دیوار باز شد!\n"
                        f"URL: {self.url}\n"
                        f"شهرها: {', '.join(self.cities_names)}\n"
                        f"دسته‌بندی: {self.category_name}\n\n"
                        f"🟢 مرورگر باز است. هر وقت کارتان تمام شد ببندید."
                    )

                    try:
                        await bm.page.wait_for_event("close", timeout=0)
                    except Exception:
                        pass

                self.signals.finished.emit(self.url)

            loop.run_until_complete(_run())

        except Exception as e:
            self.signals.error_occurred.emit(f"خطا: {e}")
        finally:
            self._is_active = False
            loop.close()


# ---------------------------------------------------------------------------
# تب اتوماسیون
# ---------------------------------------------------------------------------
class AutomationTab(QWidget):
    """تب اتوماسیون - انتخاب شهر، دسته‌بندی و باز کردن دیوار."""

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cities: List[dict] = []
        self._categories: List[dict] = []
        self._current_worker: Optional[DivarBrowserWorker] = None
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # عنوان
        title = QLabel("🤖 اتوماسیون دیوار")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        hint = QLabel(
            "شهرها و دسته‌بندی مورد نظر خود را انتخاب کنید و دکمه «شروع» را بزنید. "
            "سایت دیوار با فیلترهای انتخاب شده باز می‌شود."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ===== ردیف بالا: شهرها و دسته‌بندی کنار هم =====
        top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter = top_splitter

        # ----- بخش شهرها -----
        cities_group = QGroupBox("🏙️ انتخاب شهرها")
        cities_layout = QVBoxLayout(cities_group)
        cities_layout.setSpacing(10)

        city_search_row = QHBoxLayout()
        self.city_search = QLineEdit()
        self.city_search.setPlaceholderText("🔍 جستجوی شهر... (مثال: تهران)")
        self.city_search.textChanged.connect(self._filter_cities)
        city_search_row.addWidget(self.city_search, stretch=1)

        self.selected_cities_count = QLabel("0 شهر")
        self.selected_cities_count.setObjectName("mutedLabel")
        city_search_row.addWidget(self.selected_cities_count)
        cities_layout.addLayout(city_search_row)

        self.city_list = QListWidget()
        self.city_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.city_list.setMinimumHeight(150)
        self.city_list.itemSelectionChanged.connect(self._update_selection_info)
        cities_layout.addWidget(self.city_list, stretch=1)

        city_btn_row = QHBoxLayout()
        self.select_all_cities_btn = QPushButton("✅ انتخاب همه")
        self.select_all_cities_btn.setObjectName("successBtn")
        self.select_all_cities_btn.setMinimumHeight(40)
        self.select_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_cities_btn.clicked.connect(lambda: self.city_list.selectAll())
        city_btn_row.addWidget(self.select_all_cities_btn)

        self.deselect_all_cities_btn = QPushButton("❌ حذف انتخاب")
        self.deselect_all_cities_btn.setObjectName("dangerBtn")
        self.deselect_all_cities_btn.setMinimumHeight(40)
        self.deselect_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_cities_btn.clicked.connect(lambda: self.city_list.clearSelection())
        city_btn_row.addWidget(self.deselect_all_cities_btn)
        cities_layout.addLayout(city_btn_row)
        top_splitter.addWidget(cities_group)

        # ----- بخش دسته‌بندی‌ها -----
        cat_group = QGroupBox("📂 انتخاب دسته‌بندی (اختیاری)")
        cat_layout = QVBoxLayout(cat_group)
        cat_layout.setSpacing(10)

        cat_search_row = QHBoxLayout()
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText("🔍 جستجوی دسته‌بندی... (مثال: خودرو، مسکونی)")
        self.category_search.textChanged.connect(self._filter_categories)
        cat_search_row.addWidget(self.category_search, stretch=1)

        self.selected_category_label = QLabel("همه دسته‌ها")
        self.selected_category_label.setObjectName("mutedLabel")
        cat_search_row.addWidget(self.selected_category_label)
        cat_layout.addLayout(cat_search_row)

        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_list.setMinimumHeight(150)
        self.category_list.itemSelectionChanged.connect(self._update_selection_info)
        cat_layout.addWidget(self.category_list, stretch=1)

        cat_btn_row = QHBoxLayout()
        self.clear_category_btn = QPushButton("❌ حذف فیلتر دسته‌بندی")
        self.clear_category_btn.setObjectName("ghostBtn")
        self.clear_category_btn.setMinimumHeight(40)
        self.clear_category_btn.setCursor(Qt.PointingHandCursor)
        self.clear_category_btn.clicked.connect(self._clear_category)
        cat_btn_row.addWidget(self.clear_category_btn)
        cat_layout.addLayout(cat_btn_row)
        top_splitter.addWidget(cat_group)

        top_splitter.setSizes([400, 400])
        layout.addWidget(top_splitter, stretch=1)

        # ===== بخش اطلاعات و شروع =====
        info_group = QGroupBox("📋 اطلاعات و شروع")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(12)

        self.url_display = QTextEdit()
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(96)
        self.url_display.setPlaceholderText("URL دیوار اینجا نمایش داده می‌شود...")
        info_layout.addWidget(self.url_display)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.start_btn = QPushButton("🚀 شروع - باز کردن دیوار")
        self.start_btn.setObjectName("primaryDivar")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setMinimumHeight(52)
        start_font = QFont()
        start_font.setPointSize(13)
        start_font.setBold(True)
        self.start_btn.setFont(start_font)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setEnabled(False)
        action_row.addWidget(self.start_btn, stretch=2)

        self.close_btn = QPushButton("🔴 بستن مرورگر")
        self.close_btn.setObjectName("dangerBtn")
        self.close_btn.setMinimumHeight(52)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._close_browser)
        action_row.addWidget(self.close_btn, stretch=1)

        info_layout.addLayout(action_row)
        layout.addWidget(info_group)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    def restyle(self):
        """سازگاری با سوییچ تم - objectNameها از QSS سراسری پیروی می‌کنند."""
        for w in (self.city_list, self.category_list, self.url_display,
                  self.city_search, self.category_search):
            try:
                w.style().unpolish(w)
                w.style().polish(w)
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            if not hasattr(self, "top_splitter"):
                return
            w = self.width()
            if w < 680 and self.top_splitter.orientation() != Qt.Vertical:
                self.top_splitter.setOrientation(Qt.Vertical)
                self.top_splitter.setSizes([300, 300])
            elif w >= 680 and self.top_splitter.orientation() != Qt.Horizontal:
                self.top_splitter.setOrientation(Qt.Horizontal)
                self.top_splitter.setSizes([400, 400])
        except Exception:
            pass

    def _load_data(self):
        self._load_cities()
        self._load_categories()

    def _load_cities(self):
        if not CITIES_FILE.exists():
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

    def _load_categories(self):
        if not CATEGORIES_FILE.exists():
            item = QListWidgetItem("⚠️ فایل دسته‌بندی‌ها پیدا نشد! ابتدا fetch_categories.py را اجرا کنید.")
            item.setFlags(Qt.NoItemFlags)
            self.category_list.clear()
            self.category_list.addItem(item)
            return
        try:
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._categories = data.get("categories", [])
            self._log("INFO", f"[اتوماسیون] Loaded {len(self._categories)} categories")
            self._populate_category_list(self._categories)
        except Exception as e:
            self._log("ERROR", f"[اتوماسیون] خطا در بارگذاری دسته‌بندی‌ها: {e}")

    def _populate_city_list(self, cities: List[dict]):
        self.city_list.clear()
        if not cities:
            item = QListWidgetItem("— هیچ شهری پیدا نشد —")
            item.setFlags(Qt.NoItemFlags)
            self.city_list.addItem(item)
            return
        for city in cities:
            city_id = city.get("id", "")
            name = city.get("name", "")
            text = f"{name}  [ID: {city_id}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, city)
            self.city_list.addItem(item)

    def _populate_category_list(self, categories: List[dict]):
        self.category_list.clear()
        all_item = QListWidgetItem("📋 همه دسته‌ها (بدون فیلتر)")
        all_item.setData(Qt.UserRole, None)
        self.category_list.addItem(all_item)
        for cat in categories:
            name = cat.get("name", "")
            category = cat.get("category", "")
            slug = cat.get("slug", "")
            display_text = f"{name}"
            if category:
                display_text += f"  [{category}]"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, slug)
            self.category_list.addItem(item)
        self.category_list.setCurrentRow(0)

    def _filter_cities(self, text: str):
        if not text.strip():
            self._populate_city_list(self._cities)
            return
        filtered = [c for c in self._cities if text.lower() in c.get("name", "").lower() or text.lower() in c.get("slug", "").lower()]
        self._populate_city_list(filtered)

    def _filter_categories(self, text: str):
        self.category_list.clear()
        all_item = QListWidgetItem("📋 همه دسته‌ها (بدون فیلتر)")
        all_item.setData(Qt.UserRole, None)
        self.category_list.addItem(all_item)
        if not text.strip():
            for cat in self._categories:
                name = cat.get("name", "")
                category = cat.get("category", "")
                slug = cat.get("slug", "")
                display_text = f"{name}"
                if category:
                    display_text += f"  [{category}]"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, slug)
                self.category_list.addItem(item)
            return
        filtered = [c for c in self._categories if text.lower() in c.get("name", "").lower() or text.lower() in c.get("slug", "").lower() or text.lower() in c.get("category", "").lower()]
        for cat in filtered:
            name = cat.get("name", "")
            category = cat.get("category", "")
            slug = cat.get("slug", "")
            display_text = f"{name}"
            if category:
                display_text += f"  [{category}]"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, slug)
            self.category_list.addItem(item)

    def _clear_category(self):
        self.category_list.setCurrentRow(0)

    def _update_selection_info(self):
        selected_cities = self.city_list.selectedItems()
        city_count = len(selected_cities)
        self.selected_cities_count.setText(f"{city_count} شهر")
        self.start_btn.setEnabled(city_count > 0)

        selected_cats = self.category_list.selectedItems()
        if selected_cats:
            cat_slug = selected_cats[0].data(Qt.UserRole)
            if cat_slug:
                cat_name = selected_cats[0].text()
                self.selected_category_label.setText(cat_name[:20])
            else:
                self.selected_category_label.setText("همه دسته‌ها")
        else:
            self.selected_category_label.setText("همه دسته‌ها")

        self._update_url_display()

    def _update_url_display(self):
        selected_cities = self.city_list.selectedItems()
        if not selected_cities:
            self.url_display.clear()
            return

        cities_data = [item.data(Qt.UserRole) for item in selected_cities]
        cities_ids = [c.get("id", 0) for c in cities_data]
        cities_names = [c.get("name", "") for c in cities_data]

        cities_param = ",".join(str(cid) for cid in cities_ids)

        selected_cats = self.category_list.selectedItems()
        category_slug = None
        if selected_cats:
            category_slug = selected_cats[0].data(Qt.UserRole)

        if category_slug:
            url = f"https://divar.ir/s/iran/{category_slug}?cities={cities_param}"
        else:
            url = f"https://divar.ir/s/iran?cities={cities_param}"

        self.url_display.setPlainText(
            f"🌐 {url}\n\n"
            f"🏙️ شهرها: {', '.join(cities_names)}"
        )

    def _on_start(self):
        selected_cities = self.city_list.selectedItems()
        if not selected_cities:
            QMessageBox.information(self, "انتخاب شهر", "لطفاً حداقل یک شهر انتخاب کنید.")
            return

        cities_data = [item.data(Qt.UserRole) for item in selected_cities]
        cities_ids = [c.get("id", 0) for c in cities_data]
        cities_names = [c.get("name", "") for c in cities_data]

        selected_cats = self.category_list.selectedItems()
        category_slug = None
        category_name = "همه دسته‌ها"
        if selected_cats:
            category_slug = selected_cats[0].data(Qt.UserRole)
            if category_slug:
                category_name = selected_cats[0].text()

        cities_param = ",".join(str(cid) for cid in cities_ids)
        if category_slug:
            url = f"https://divar.ir/s/iran/{category_slug}?cities={cities_param}"
        else:
            url = f"https://divar.ir/s/iran?cities={cities_param}"

        self._log("INFO", f"[اتوماسیون] شروع: {len(cities_ids)} شهر - دسته: {category_name}")

        sm = SessionManager(platform="divar")
        record = sm.load()
        phone = record.phone if record else None

        self.start_btn.setEnabled(False)
        self.start_btn.setText("⏳ در حال باز کردن دیوار...")

        worker = DivarBrowserWorker(url, cities_names, category_name, phone)
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

    def is_browser_open(self) -> bool:
        """بررسی اینکه آیا مرورگر اتوماسیون باز و فعال است یا خیر."""
        return self._current_worker is not None and self._current_worker.is_browser_running()

    def _close_browser(self):
        """بستن مرورگر اختصاصی اتوماسیون."""
        if not self.is_browser_open():
            QMessageBox.information(
                self,
                "بستن مرورگر",
                "ℹ️ هیچ مرورگری برای اتوماسیون باز نیست.",
            )
            self._log("INFO", "[اتوماسیون] درخواست بستن مرورگر رد شد (مرورگری باز نیست)")
            return

        if self._current_worker:
            try:
                self._current_worker.request_close()
                self._log("INFO", "[اتوماسیون] درخواست بستن مرورگر اختصاصی اتوماسیون ارسال شد")
            except Exception as e:
                self._log("WARNING", f"[اتوماسیون] خطا در بستن مرورگر اتوماسیون: {e}")
