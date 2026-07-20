"""
AutomationTab - تب اتوماسیون دیوار و شیپور.

ویژگی‌های پیشرفته:
- پشتیبانی کامل از الگوی URLهای پیچیده شیپور (تک‌شهری، چندشهری، دسته‌بندی‌ها و زیردسته‌ها)
- ساخت خودکار لینک شیپور مانند:
  * تک‌شهری: https://www.sheypoor.com/s/tehran/vehicles
  * چندشهری: https://www.sheypoor.com/s/iran/real-estate?cities[0]=291&cities[1]=292
- انتخاب حساب کاربری، تمدید خودکار و جایگزینی کوکی‌ها در پس‌زمینه
- تفکیک پلتفرم (دیوار / شیپور)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QThreadPool, QObject, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.browser_manager import BrowserManager
from core.session_manager import SessionManager
from core.session_models import SessionRecord, SessionStatus

logger = logging.getLogger("divar.automation")

DIVAR_CITIES_FILE = PROJECT_ROOT / "data" / "cities.json"
DIVAR_CATEGORIES_FILE = PROJECT_ROOT / "data" / "categories.json"

SHEYPOOR_CITIES_FILE = PROJECT_ROOT / "data" / "sheypoor_cities.json"
SHEYPOOR_CATEGORIES_FILE = PROJECT_ROOT / "data" / "sheypoor_categories.json"


def format_status_persian(status_str: str) -> str:
    """تبدیل وضعیت انگلیسی به برچسب فارسی زیبا با آیکون."""
    s = str(status_str).lower()
    if s == "valid":
        return "🟢 معتبر"
    elif s == "invalid":
        return "🔴 نامعتبر"
    elif s == "expired":
        return "🟠 منقضی شده"
    elif s == "needs_refresh":
        return "🟡 نیاز به بروزرسانی"
    return "⚪ بررسی‌نشده"


def build_sheypoor_url(cities_data: List[dict], category_slug: Optional[str]) -> str:
    """
    ساخت URL دقیق شیپور طبق الگوی رسمی سایت:
    1. بدون شهر:
       - https://www.sheypoor.com/s/iran
       - https://www.sheypoor.com/s/iran/{category}
    2. تک‌شهری:
       - https://www.sheypoor.com/s/tehran
       - https://www.sheypoor.com/s/tehran/vehicles
    3. چندشهری:
       - https://www.sheypoor.com/s/iran?cities[0]=291&cities[1]=292&cities[2]=297
       - https://www.sheypoor.com/s/iran/vehicles?cities[0]=291&cities[1]=292
    """
    cat_part = f"/{category_slug}" if category_slug else ""

    if not cities_data:
        return f"https://www.sheypoor.com/s/iran{cat_part}"

    if len(cities_data) == 1:
        city_slug = cities_data[0].get("slug") or "iran"
        return f"https://www.sheypoor.com/s/{city_slug}{cat_part}"

    # چند شهر
    query_params = "&".join(
        f"cities[{i}]={c.get('id')}"
        for i, c in enumerate(cities_data)
        if c.get("id") is not None
    )
    return f"https://www.sheypoor.com/s/iran{cat_part}?{query_params}"


def build_divar_url(cities_data: List[dict], category_slug: Optional[str]) -> str:
    """ساخت URL فیلترشده دیوار."""
    cities_ids = [c.get("id", 0) for c in cities_data if isinstance(c, dict)]
    cities_param = ",".join(str(cid) for cid in cities_ids)
    if category_slug:
        return f"https://divar.ir/s/iran/{category_slug}?cities={cities_param}" if cities_param else f"https://divar.ir/s/iran/{category_slug}"
    else:
        return f"https://divar.ir/s/iran?cities={cities_param}" if cities_param else "https://divar.ir/s/iran"


# ---------------------------------------------------------------------------
# سیگنال‌ها
# ---------------------------------------------------------------------------
class AutomationSignals(QObject):
    status_changed = Signal(str)
    error_occurred = Signal(str)
    finished = Signal(str)


# ---------------------------------------------------------------------------
# Worker پس‌زمینه برای تمدید خودکار و جایگزینی کوکی‌ها (دیوار و شیپور)
# ---------------------------------------------------------------------------
class BackgroundPeriodicRefresherWorker(QRunnable):
    """بررسی و جایگزینی خودکار کوکی‌ها و توکن‌ها در پس‌زمینه (برای همه پلتفرم‌ها)."""

    def __init__(self, platform: str = "all", phone: Optional[str] = None):
        super().__init__()
        self.platform = platform
        self.phone = phone
        self.signals = AutomationSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                platforms = ["divar", "sheypoor"] if self.platform == "all" else [self.platform]

                for plat in platforms:
                    sm = SessionManager(platform=plat)
                    records = [sm.load(phone=self.phone)] if self.phone else sm.list_sessions()
                    records = [r for r in records if r is not None]

                    for record in records:
                        if record.status == SessionStatus.INVALID:
                            continue

                        self.signals.status_changed.emit(
                            f"⏳ بررسی دوره‌ای پس‌زمینه [{plat.upper()}] برای شماره {record.phone}..."
                        )
                        bm = BrowserManager(session_record=record, headless=True)
                        try:
                            async with bm:
                                try:
                                    from core.token_refresher import TokenRefresher
                                    refresher = TokenRefresher(sm)
                                    await refresher.ensure_valid_token(bm.page, bm.context, record)
                                except Exception as te:
                                    logger.debug("Token refresh error during periodic check: %s", te)

                                status = await sm.validate(record, bm.page)
                                if status == SessionStatus.VALID:
                                    await sm.save_from_context(
                                        bm.context, record.phone, metadata=record.metadata
                                    )
                                    self.signals.status_changed.emit(
                                        f"✅ کوکی‌ها و توکن‌های [{plat.upper()}] شماره {record.phone} با موفقیت بروزرسانی و جایگزین شدند."
                                    )
                                else:
                                    self.signals.status_changed.emit(
                                        f"⚠️ نشست [{plat.upper()}] شماره {record.phone} نامعتبر تشخیص داده شد."
                                    )
                        except Exception as err:
                            logger.warning("Periodic background check failed for %s (%s): %s", plat, record.phone, err)

            loop.run_until_complete(_run())
        except Exception as e:
            logger.error("Background periodic refresher error: %s", e)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Worker برای باز کردن مرورگر (دیوار یا شیپور)
# ---------------------------------------------------------------------------
class AutomationBrowserWorker(QRunnable):
    """باز کردن مرورگر برای پلتفرم انتخاب شده (دیوار / شیپور)."""

    def __init__(
        self,
        platform: str,
        url: str,
        cities_names: List[str],
        category_name: str,
        phone: str,
    ):
        super().__init__()
        self.platform = platform
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
            plat_name = "دیوار" if self.platform == "divar" else "شیپور"
            self.signals.status_changed.emit(f"🌐 لینک هدف ({plat_name}): {self.url}")

            async def _run():
                sm = SessionManager(platform=self.platform)
                record = sm.load(phone=self.phone)
                if not record:
                    self.signals.error_occurred.emit(f"هیچ حسابی برای {plat_name} با شماره {self.phone} پیدا نشد.")
                    return

                self.signals.status_changed.emit(
                    f"📱 در حال بررسی توکن و باز کردن مرورگر [{plat_name}] شماره {record.phone}..."
                )
                bm = BrowserManager(session_record=record)
                self._browser_manager = bm

                async with bm:
                    try:
                        from core.token_refresher import TokenRefresher
                        refresher = TokenRefresher(sm)
                        await refresher.ensure_valid_token(bm.page, bm.context, record)
                    except Exception as te:
                        logger.debug("Token pre-check error: %s", te)

                    status = await sm.validate(record, bm.page)
                    if status == SessionStatus.VALID:
                        await sm.save_from_context(bm.context, record.phone, metadata=record.metadata)

                    self.signals.status_changed.emit(f"🔄 در حال انتقال به لینک فیلترشده {plat_name}...")
                    await bm.page.goto(self.url, wait_until="domcontentloaded", timeout=30_000)
                    try:
                        await bm.page.wait_for_load_state("networkidle", timeout=10_000)
                    except Exception:
                        pass

                    details = f"شهرها: {', '.join(self.cities_names)}\nدسته‌بندی: {self.category_name}\n" if self.cities_names else ""
                    self.signals.status_changed.emit(
                        f"✅ مرورگر {plat_name} با شماره {record.phone} باز شد!\n"
                        f"URL: {self.url}\n{details}\n"
                        f"🟢 مرورگر باز است. هر وقت کارتان تمام شد، پنجره مرورگر را ببندید."
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
    """تب اتوماسیون - مدیریت اتوماتیک حساب‌های دیوار و شیپور."""

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cities: List[dict] = []
        self._categories: List[dict] = []
        self._current_worker: Optional[AutomationBrowserWorker] = None

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._run_periodic_check)

        self._setup_ui()
        self._on_platform_changed()
        self._on_interval_changed()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(14)

        title = QLabel("🤖 اتوماسیون دیوار و شیپور")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        hint = QLabel(
            "پلتفرم، شماره حساب، شهرها و دسته‌بندی را انتخاب کنید. "
            "کوکی‌ها و نشست‌های هر دو پلتفرم به صورت خودکار و دوره‌ای پس‌زمینه بروزرسانی می‌شوند تا حساب منقضی نشود."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ===== بخش اول: پلتفرم، حساب کاربری و بررسی خودکار =====
        settings_group = QGroupBox("⚙️ انتخاب پلتفرم، حساب کاربری و پایداری کوکی‌ها")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setSpacing(16)
        settings_layout.setContentsMargins(16, 16, 16, 16)

        # --- ۱. انتخاب پلتفرم ---
        plat_col = QVBoxLayout()
        plat_col.setSpacing(6)
        plat_lbl = QLabel("📌 انتخاب پلتفرم:")
        plat_lbl.setObjectName("subtitleLabel")
        plat_col.addWidget(plat_lbl)

        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumHeight(42)
        self.platform_combo.addItem("🔴 دیوار (Divar)", "divar")
        self.platform_combo.addItem("🔵 شیپور (Sheypoor)", "sheypoor")
        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        plat_col.addWidget(self.platform_combo)
        settings_layout.addLayout(plat_col, stretch=1)

        # --- ۲. انتخاب شماره تلفن ---
        phone_col = QVBoxLayout()
        phone_col.setSpacing(6)
        phone_label = QLabel("📱 انتخاب حساب (شماره تلفن):")
        phone_label.setObjectName("subtitleLabel")
        phone_col.addWidget(phone_label)

        phone_row = QHBoxLayout()
        phone_row.setSpacing(8)
        self.phone_combo = QComboBox()
        self.phone_combo.setMinimumHeight(42)
        self.phone_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.phone_combo.currentIndexChanged.connect(self._update_selection_info)
        phone_row.addWidget(self.phone_combo, stretch=1)

        self.refresh_phones_btn = QPushButton("🔃")
        self.refresh_phones_btn.setObjectName("ghostBtn")
        self.refresh_phones_btn.setToolTip("به‌روزرسانی لیست شماره‌ها")
        self.refresh_phones_btn.setMinimumHeight(42)
        self.refresh_phones_btn.setFixedWidth(44)
        self.refresh_phones_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_phones_btn.clicked.connect(self._reload_phone_numbers)
        phone_row.addWidget(self.refresh_phones_btn)

        phone_col.addLayout(phone_row)
        settings_layout.addLayout(phone_col, stretch=2)

        # --- ۳. تنظیم بازه بررسی خودکار کوکی‌ها ---
        interval_col = QVBoxLayout()
        interval_col.setSpacing(6)
        interval_label = QLabel("⏱️ بررسی و جایگزینی خودکار کوکی‌ها:")
        interval_label.setObjectName("subtitleLabel")
        interval_col.addWidget(interval_label)

        self.interval_combo = QComboBox()
        self.interval_combo.setMinimumHeight(42)
        self.interval_combo.addItem("⏱️ هر ۶۰ دقیقه (پیش‌فرض)", 60)
        self.interval_combo.addItem("⏱️ هر ۱۲۰ دقیقه (۲ ساعت)", 120)
        self.interval_combo.addItem("📅 روزی یک‌بار (۲۴ ساعت)", 1440)
        self.interval_combo.addItem("❌ خاموش (غیرفعال)", 0)
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        interval_col.addWidget(self.interval_combo)

        settings_layout.addLayout(interval_col, stretch=2)

        layout.addWidget(settings_group)

        # ===== بخش دوم: شهرها و دسته‌بندی کنار هم =====
        top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter = top_splitter

        # ----- بخش شهرها -----
        cities_group = QGroupBox("🏙️ انتخاب شهرها")
        self.cities_group = cities_group
        cities_layout = QVBoxLayout(cities_group)
        cities_layout.setSpacing(10)

        city_search_row = QHBoxLayout()
        self.city_search = QLineEdit()
        self.city_search.setPlaceholderText("🔍 جستجوی شهر... (مثال: تهران، اسلامشهر)")
        self.city_search.textChanged.connect(self._filter_cities)
        city_search_row.addWidget(self.city_search, stretch=1)

        self.selected_cities_count = QLabel("0 شهر")
        self.selected_cities_count.setObjectName("mutedLabel")
        city_search_row.addWidget(self.selected_cities_count)
        cities_layout.addLayout(city_search_row)

        self.city_list = QListWidget()
        self.city_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.city_list.setMinimumHeight(140)
        self.city_list.itemSelectionChanged.connect(self._update_selection_info)
        cities_layout.addWidget(self.city_list, stretch=1)

        city_btn_row = QHBoxLayout()
        self.select_all_cities_btn = QPushButton("✅ انتخاب همه")
        self.select_all_cities_btn.setObjectName("successBtn")
        self.select_all_cities_btn.setMinimumHeight(38)
        self.select_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_cities_btn.clicked.connect(lambda: self.city_list.selectAll())
        city_btn_row.addWidget(self.select_all_cities_btn)

        self.deselect_all_cities_btn = QPushButton("❌ حذف انتخاب")
        self.deselect_all_cities_btn.setObjectName("dangerBtn")
        self.deselect_all_cities_btn.setMinimumHeight(38)
        self.deselect_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_cities_btn.clicked.connect(lambda: self.city_list.clearSelection())
        city_btn_row.addWidget(self.deselect_all_cities_btn)
        cities_layout.addLayout(city_btn_row)
        top_splitter.addWidget(cities_group)

        # ----- بخش دسته‌بندی‌ها -----
        cat_group = QGroupBox("📂 انتخاب دسته‌بندی و زیردسته‌ها")
        self.cat_group = cat_group
        cat_layout = QVBoxLayout(cat_group)
        cat_layout.setSpacing(10)

        cat_search_row = QHBoxLayout()
        self.category_search = QLineEdit()
        self.category_search.setPlaceholderText("🔍 جستجوی دسته‌بندی و زیردسته... (مثال: خودرو، املاک)")
        self.category_search.textChanged.connect(self._filter_categories)
        cat_search_row.addWidget(self.category_search, stretch=1)

        self.selected_category_label = QLabel("همه دسته‌ها")
        self.selected_category_label.setObjectName("mutedLabel")
        cat_search_row.addWidget(self.selected_category_label)
        cat_layout.addLayout(cat_search_row)

        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_list.setMinimumHeight(140)
        self.category_list.itemSelectionChanged.connect(self._update_selection_info)
        cat_layout.addWidget(self.category_list, stretch=1)

        cat_btn_row = QHBoxLayout()
        self.clear_category_btn = QPushButton("❌ حذف فیلتر دسته‌بندی")
        self.clear_category_btn.setObjectName("ghostBtn")
        self.clear_category_btn.setMinimumHeight(38)
        self.clear_category_btn.setCursor(Qt.PointingHandCursor)
        self.clear_category_btn.clicked.connect(self._clear_category)
        cat_btn_row.addWidget(self.clear_category_btn)
        cat_layout.addLayout(cat_btn_row)
        top_splitter.addWidget(cat_group)

        top_splitter.setSizes([400, 400])
        layout.addWidget(top_splitter, stretch=1)

        # ===== بخش سوم: اطلاعات و شروع =====
        info_group = QGroupBox("📋 اطلاعات و اجرای مرورگر")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        self.url_display = QTextEdit()
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(88)
        self.url_display.setPlaceholderText("اطلاعات پلتفرم و شماره انتخاب‌شده...")
        info_layout.addWidget(self.url_display)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.start_btn = QPushButton("🚀 شروع - باز کردن مرورگر")
        self.start_btn.setObjectName("primaryDivar")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setMinimumHeight(50)
        start_font = QFont()
        start_font.setPointSize(13)
        start_font.setBold(True)
        self.start_btn.setFont(start_font)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setEnabled(False)
        action_row.addWidget(self.start_btn, stretch=2)

        self.close_btn = QPushButton("🔴 بستن مرورگر")
        self.close_btn.setObjectName("dangerBtn")
        self.close_btn.setMinimumHeight(50)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._close_browser)
        action_row.addWidget(self.close_btn, stretch=1)

        info_layout.addLayout(action_row)
        layout.addWidget(info_group)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    def restyle(self):
        for w in (self.city_list, self.category_list, self.url_display,
                  self.city_search, self.category_search, self.phone_combo,
                  self.interval_combo, self.platform_combo):
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

    def get_selected_platform(self) -> str:
        return self.platform_combo.currentData() or "divar"

    def _on_platform_changed(self):
        plat = self.get_selected_platform()

        if plat == "sheypoor":
            self.start_btn.setObjectName("primarySheypoor")
            self.cities_group.setTitle("🏙️ انتخاب شهرها (شیپور)")
            self.cat_group.setTitle("📂 انتخاب دسته‌بندی و زیردسته‌ها (شیپور)")
        else:
            self.start_btn.setObjectName("primaryDivar")
            self.cities_group.setTitle("🏙️ انتخاب شهرها (دیوار)")
            self.cat_group.setTitle("📂 انتخاب دسته‌بندی و زیردسته‌ها (دیوار)")

        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

        self._load_data_for_platform(plat)
        self._reload_phone_numbers()

    def _load_data_for_platform(self, plat: str):
        if plat == "sheypoor":
            c_file = SHEYPOOR_CITIES_FILE
            cat_file = SHEYPOOR_CATEGORIES_FILE
        else:
            c_file = DIVAR_CITIES_FILE
            cat_file = DIVAR_CATEGORIES_FILE

        self._load_cities(c_file)
        self._load_categories(cat_file)

    def _reload_phone_numbers(self):
        self.phone_combo.clear()
        plat = self.get_selected_platform()
        plat_name = "دیوار" if plat == "divar" else "شیپور"

        try:
            sm = SessionManager(platform=plat)
            sessions = sm.list_sessions()
            if not sessions:
                self.phone_combo.addItem(f"— هیچ حسابی برای {plat_name} ذخیره نشده است —", None)
                self.start_btn.setEnabled(False)
                self._log("WARNING", f"[اتوماسیون] هیچ حساب {plat_name} یافت نشد.")
                self._update_selection_info()
                return

            for rec in sessions:
                status_p = format_status_persian(rec.status.value if rec.status else "unknown")
                cookies = len(rec.storage_state.cookies) if (rec.storage_state and rec.storage_state.cookies) else 0
                label = f"{rec.phone}  |  {status_p}  ({cookies} کوکی)"
                self.phone_combo.addItem(label, rec.phone)

            self._update_selection_info()
            self._log("INFO", f"[اتوماسیون] بارگذاری {len(sessions)} شماره حساب {plat_name}")
        except Exception as e:
            self._log("ERROR", f"[اتوماسیون] خطا در خواندن لیست شماره‌ها: {e}")

    def get_selected_phone(self) -> Optional[str]:
        return self.phone_combo.currentData()

    # ------------------------------------------------------------------
    # تنظیمات بررسی خودکار و دوره‌ای کوکی‌ها
    # ------------------------------------------------------------------
    def _on_interval_changed(self):
        minutes = self.interval_combo.currentData()
        if minutes and minutes > 0:
            ms = minutes * 60 * 1000
            self._auto_timer.setInterval(ms)
            if not self._auto_timer.isActive():
                self._auto_timer.start()
            self._log("INFO", f"[اتوماسیون] بررسی خودکار پس‌زمینه کوکی‌ها روی هر {minutes} دقیقه فعال شد")
        else:
            self._auto_timer.stop()
            self._log("INFO", "[اتوماسیون] بررسی خودکار پس‌زمینه کوکی‌ها غیرفعال گردید")

    def _run_periodic_check(self):
        if self.is_browser_open():
            self._log("INFO", "[اتوماسیون] مرورگر در حال استفاده است؛ بررسی دوره‌ای به تعویق افتاد.")
            return

        self._log("INFO", "[اتوماسیون] شروع بررسی خودکار و جایگزینی پس‌زمینه کوکی‌ها (دیوار و شیپور)...")
        plat = self.get_selected_platform()
        phone = self.get_selected_phone()

        worker = BackgroundPeriodicRefresherWorker(platform=plat, phone=phone)
        worker.signals.status_changed.connect(self._on_status_changed)
        QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------
    # بارگذاری داده‌های شهرها و دسته‌ها
    # ------------------------------------------------------------------
    def _load_cities(self, filepath: Path):
        if not filepath.exists():
            item = QListWidgetItem(f"⚠️ فایل شهرها ({filepath.name}) پیدا نشد!")
            item.setFlags(Qt.NoItemFlags)
            self.city_list.clear()
            self.city_list.addItem(item)
            self._cities = []
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cities = data.get("cities", [])
            self._populate_city_list(self._cities)
        except Exception as e:
            self._log("ERROR", f"[اتوماسیون] خطا در بارگذاری شهرها: {e}")

    def _load_categories(self, filepath: Path):
        if not filepath.exists():
            item = QListWidgetItem(f"⚠️ فایل دسته‌بندی‌ها ({filepath.name}) پیدا نشد!")
            item.setFlags(Qt.NoItemFlags)
            self.category_list.clear()
            self.category_list.addItem(item)
            self._categories = []
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._categories = data.get("categories", [])
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
            name = city.get("display_name") or city.get("name", "")
            dist_cnt = city.get("districts_count")
            dist_str = f" ({dist_cnt} محله)" if dist_cnt else ""
            text = f"{name}{dist_str}"
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
            cat_type = cat.get("type", "main")

            if cat_type == "sub" and category:
                display_text = f"  └── {name}  [{category}]"
            else:
                display_text = f"📁 {name}"

            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, slug)
            self.category_list.addItem(item)
        self.category_list.setCurrentRow(0)

    def _filter_cities(self, text: str):
        if not text.strip():
            self._populate_city_list(self._cities)
            return
        filtered = [
            c for c in self._cities
            if text.lower() in c.get("name", "").lower()
            or text.lower() in c.get("slug", "").lower()
            or text.lower() in c.get("display_name", "").lower()
            or text.lower() in c.get("province_name", "").lower()
        ]
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
                cat_type = cat.get("type", "main")
                display_text = f"  └── {name}  [{category}]" if cat_type == "sub" and category else f"📁 {name}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, slug)
                self.category_list.addItem(item)
            return
        filtered = [
            cat for cat in self._categories
            if text.lower() in cat.get("name", "").lower()
            or text.lower() in cat.get("slug", "").lower()
            or text.lower() in cat.get("category", "").lower()
        ]
        for cat in filtered:
            name = cat.get("name", "")
            category = cat.get("category", "")
            slug = cat.get("slug", "")
            cat_type = cat.get("type", "main")
            display_text = f"  └── {name}  [{category}]" if cat_type == "sub" and category else f"📁 {name}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, slug)
            self.category_list.addItem(item)

    def _clear_category(self):
        self.category_list.setCurrentRow(0)

    def _update_selection_info(self):
        plat = self.get_selected_platform()
        selected_phone = self.get_selected_phone()
        plat_name = "دیوار" if plat == "divar" else "شیپور"

        selected_cities = self.city_list.selectedItems()
        city_count = len(selected_cities)
        self.selected_cities_count.setText(f"{city_count} شهر")

        self.start_btn.setEnabled(selected_phone is not None)
        self.start_btn.setText(f"🚀 شروع - باز کردن {plat_name}")

        selected_cats = self.category_list.selectedItems()
        if selected_cats:
            cat_slug = selected_cats[0].data(Qt.UserRole)
            if cat_slug:
                cat_name = selected_cats[0].text().replace("📁", "").replace("└──", "").strip()
                self.selected_category_label.setText(cat_name[:20])
            else:
                self.selected_category_label.setText("همه دسته‌ها")
        else:
            self.selected_category_label.setText("همه دسته‌ها")

        self._update_url_display()

    def _update_url_display(self):
        plat = self.get_selected_platform()
        selected_phone = self.get_selected_phone()
        plat_name = "دیوار" if plat == "divar" else "شیپور"

        if not selected_phone:
            self.url_display.setPlainText(f"⚠️ لطفاً ابتدا یک حساب کاربری {plat_name} از منوی بالا انتخاب کنید.")
            return

        selected_cities = self.city_list.selectedItems()
        cities_data = [item.data(Qt.UserRole) for item in selected_cities if item.data(Qt.UserRole)]
        cities_names = [c.get("name", "") for c in cities_data if isinstance(c, dict)]

        selected_cats = self.category_list.selectedItems()
        category_slug = None
        if selected_cats:
            category_slug = selected_cats[0].data(Qt.UserRole)

        # ساخت URL مخصوص دیوار یا شیپور
        if plat == "sheypoor":
            url = build_sheypoor_url(cities_data, category_slug)
        else:
            url = build_divar_url(cities_data, category_slug)

        city_info = f"🏙️ شهرها ({len(cities_names)}): {', '.join(cities_names)}" if cities_names else "🏙️ همه شهرها (سراسر ایران)"
        self.url_display.setPlainText(
            f"📌 پلتفرم: {plat_name}\n"
            f"📱 حساب انتخاب‌شده: {selected_phone}\n"
            f"🌐 لینک فیلترشده: {url}\n"
            f"{city_info}"
        )

    # ------------------------------------------------------------------
    # اجرای اتوماسیون
    # ------------------------------------------------------------------
    def _on_start(self):
        plat = self.get_selected_platform()
        selected_phone = self.get_selected_phone()
        plat_name = "دیوار" if plat == "divar" else "شیپور"

        if not selected_phone:
            QMessageBox.information(self, "انتخاب حساب", f"لطفاً ابتدا یک حساب کاربری {plat_name} انتخاب کنید.")
            return

        selected_cities = self.city_list.selectedItems()
        cities_data = [item.data(Qt.UserRole) for item in selected_cities if item.data(Qt.UserRole)]
        cities_names = [c.get("name", "") for c in cities_data if isinstance(c, dict)]

        selected_cats = self.category_list.selectedItems()
        category_slug = None
        category_name = "همه دسته‌ها"
        if selected_cats:
            category_slug = selected_cats[0].data(Qt.UserRole)
            if category_slug:
                category_name = selected_cats[0].text().replace("📁", "").replace("└──", "").strip()

        if plat == "sheypoor":
            url = build_sheypoor_url(cities_data, category_slug)
        else:
            url = build_divar_url(cities_data, category_slug)

        self._log("INFO", f"[اتوماسیون] شروع اجرای مرورگر {plat_name} برای شماره {selected_phone}")

        self.start_btn.setEnabled(False)
        self.start_btn.setText(f"⏳ در حال باز کردن {plat_name} ({selected_phone})...")

        worker = AutomationBrowserWorker(
            platform=plat,
            url=url,
            cities_names=cities_names,
            category_name=category_name,
            phone=selected_phone,
        )
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
        self.start_btn.setText("🚀 شروع - باز کردن مرورگر")
        self._current_worker = None
        QMessageBox.critical(self, "خطا", f"خطا:\n{error}")

    @Slot(str)
    def _on_finished(self, url: str):
        self._log("INFO", f"[اتوماسیون] مرورگر بسته شد: {url}")
        self.start_btn.setEnabled(True)
        self.start_btn.setText("🚀 شروع - باز کردن مرورگر")
        self._current_worker = None
        self._reload_phone_numbers()

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
