"""
AutomationTab - تب اتوماسیون پیشرفته دیوار و شیپور به همراه استخراج هوشمند شماره تماس، پوشه‌بندی اکسل و ارسال هم‌زمان چت.

ویژگی‌های جدید:
- پشتیبانی ۲ طرفه کامل از استخراج شماره و چت خودکار در **شیپور** و **دیوار**
- ورود به آگهی شیپور، کلیک روی «تماس با ۰۹۱۲...» و استخراج شماره کامل
- ارسال خودکار پیام به چت شیپور با آدرس https://www.sheypoor.com/session/myChats?listingId={id}
- همگام‌سازی ۱ به ۱ استخراج شماره با ارسال چت برای همان آگهی‌ها
- ذخیره و پوشه‌بندی اتوماتیک شماره‌ها در فایل‌های اکسل بر اساس استان/شهر، دسته‌بندی و پیش‌شماره (0912، 0917، 0933)
- اسکرول کامل روی کل صفحه (QScrollArea)
- بروزرسانی و استخراج زنده کوکی‌ها از داخل مرورگر فعال (راهکار ۱)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QThreadPool, QObject, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
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
from modules.ad_extractor import AdExtractor, organize_and_save_phone_excel, save_extracted_ads

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
    """ساخت URL دقیق شیپور طبق الگوی رسمی سایت."""
    cat_part = f"/{category_slug}" if category_slug else ""

    if not cities_data:
        return f"https://www.sheypoor.com/s/iran{cat_part}"

    if len(cities_data) == 1:
        city_slug = cities_data[0].get("slug") or "iran"
        return f"https://www.sheypoor.com/s/{city_slug}{cat_part}"

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
    ads_extracted = Signal(list)


# ---------------------------------------------------------------------------
# Worker پس‌زمینه برای تمدید خودکار
# ---------------------------------------------------------------------------
class BackgroundPeriodicRefresherWorker(QRunnable):
    """بررسی و جایگزینی خودکار کوکی‌ها هنگامی که مرورگر اصلی باز نیست."""

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
# Worker برای اجرای اتوماسیون، استخراج شماره تماس و ارسال پیام چت
# ---------------------------------------------------------------------------
class AutomationBrowserWorker(QRunnable):
    """باز کردن مرورگر، استخراج آگهی‌ها، استخراج شماره تماس و ارسال پیام در چت."""

    def __init__(
        self,
        platform: str,
        url: str,
        cities_names: List[str],
        category_name: str,
        phone: str,
        interval_minutes: int = 60,
        max_pages: int = 3,
        chat_message: Optional[str] = None,
        max_chats: int = 10,
        extract_phone: bool = True,
        max_phones: int = 10,
        sync_phone_chat: bool = True,
    ):
        super().__init__()
        self.platform = platform
        self.url = url
        self.cities_names = cities_names
        self.category_name = category_name
        self.phone = phone
        self.interval_minutes = interval_minutes
        self.max_pages = max_pages
        self.chat_message = chat_message
        self.max_chats = max_chats
        self.extract_phone = extract_phone
        self.max_phones = max_phones
        self.sync_phone_chat = sync_phone_chat
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

                    # ✨ ۱. استخراج آگهی‌های جدید (با وقفه ۳ ثانیه‌ای بین اسکرول‌ها)
                    self.signals.status_changed.emit(
                        f"🔍 در حال استخراج آگهی‌ها در {self.max_pages} صفحه (وقفه ۳ ثانیه‌ای بین اسکرول‌ها)..."
                    )
                    extractor = AdExtractor(self.platform, bm.page)
                    extracted_ads = await extractor.scrape_multiple_pages(
                        max_pages=self.max_pages,
                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[استخراج] {msg}"),
                    )

                    # ارسال فوری نتایج اولیه به جدول UI
                    if extracted_ads:
                        self.signals.ads_extracted.emit(list(extracted_ads))
                        save_extracted_ads(extracted_ads, self.platform, self.phone)
                    else:
                        self.signals.status_changed.emit("ℹ️ هیچ آگهی جدیدی پیدا نشد (آگهی‌های قبلی تکراری بودند).")

                    loc_title = ", ".join(self.cities_names) if self.cities_names else "سراسر_ایران"

                    # ✨ ۲. سناریوی هم‌زمان (Sync): استخراج شماره تماس دقیقا برای همان آگهی‌هایی که چت فرستاده می‌شود
                    if self.sync_phone_chat and self.chat_message and self.chat_message.strip() and extracted_ads:
                        unmessaged_ads = [ad for ad in extracted_ads if ad.get("token") and ad.get("token") not in extractor.messaged_tokens]
                        target_ads = unmessaged_ads[:self.max_chats]

                        if not unmessaged_ads:
                            self.signals.status_changed.emit(
                                f"ℹ️ تمام آگهی‌های استخراج‌شده قبلاً پیام چت دریافت کرده‌اند؛ آگهی جدیدی باقی نمانده است."
                            )
                        else:
                            self.signals.status_changed.emit(
                                f"💬🔗 همگام‌سازی فعال: استخراج شماره تماس و ارسال چت هم‌زمان برای {len(target_ads)} آگهی {plat_name}..."
                            )
                            for idx, ad in enumerate(target_ads, 1):
                                token = ad.get("token")
                                ad_url = ad.get("url")

                                # الف) استخراج شماره تماس برای این آگهی
                                if self.platform == "divar":
                                    p_num, has_chat = await extractor.extract_divar_phone_number(
                                        token=token,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[همگام {idx}/{len(target_ads)}] {msg}"),
                                    )
                                else:
                                    p_num, has_chat = await extractor.extract_sheypoor_phone_number(
                                        url=ad_url,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[همگام {idx}/{len(target_ads)}] {msg}"),
                                    )

                                ad["phone_number"] = p_num if p_num else "ناموجود/مخفی"

                                if p_num and p_num.startswith("09") and len(p_num) == 11:
                                    excel_saved = organize_and_save_phone_excel(
                                        phone_number=p_num,
                                        title=ad.get("title", ""),
                                        location_name=loc_title,
                                        category_name=self.category_name,
                                        platform=self.platform,
                                        url=ad.get("url", ""),
                                    )
                                    self.signals.status_changed.emit(
                                        f"💾 شماره {p_num} در اکسل {excel_saved.name} ذخیره گردید."
                                    )

                                # ب) ارسال پیام در چت همان آگهی
                                self.signals.status_changed.emit(
                                    f"💬 [{idx}/{len(target_ads)}] در حال ارسال پیام به چت فروشنده {plat_name}: «{ad.get('title')}»..."
                                )
                                if self.platform == "divar":
                                    sent_ok = await extractor.send_divar_chat_message(
                                        token=token,
                                        message_text=self.chat_message,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[چت دیوار] {msg}"),
                                    )
                                else:
                                    sent_ok = await extractor.send_sheypoor_chat_message(
                                        listing_id=token,
                                        message_text=self.chat_message,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[چت شیپور] {msg}"),
                                    )

                                ad["chat_sent"] = sent_ok

                                # بروزرسانی آنی جدول UI
                                self.signals.ads_extracted.emit(list(extracted_ads))
                                save_extracted_ads(extracted_ads, self.platform, self.phone)

                    # ✨ ۳. سناریوی مستقل (غیرهمگام): استخراج شماره مجزا و ارسال چت مجزا
                    else:
                        if self.extract_phone and self.max_phones > 0 and extracted_ads:
                            target_phone_ads = extracted_ads[:self.max_phones]
                            self.signals.status_changed.emit(
                                f"📞 در حال استخراج شماره تماس {len(target_phone_ads)} آگهی {plat_name} (سقف: {self.max_phones} شماره)..."
                            )

                            for idx, ad in enumerate(target_phone_ads, 1):
                                token = ad.get("token")
                                ad_url = ad.get("url")

                                if self.platform == "divar":
                                    p_num, has_chat = await extractor.extract_divar_phone_number(
                                        token=token,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[شماره تماس {idx}/{len(target_phone_ads)}] {msg}"),
                                    )
                                else:
                                    p_num, has_chat = await extractor.extract_sheypoor_phone_number(
                                        url=ad_url,
                                        progress_callback=lambda msg: self.signals.status_changed.emit(f"[شماره تماس {idx}/{len(target_phone_ads)}] {msg}"),
                                    )

                                ad["phone_number"] = p_num if p_num else "ناموجود/مخفی"

                                if p_num and p_num.startswith("09") and len(p_num) == 11:
                                    excel_saved = organize_and_save_phone_excel(
                                        phone_number=p_num,
                                        title=ad.get("title", ""),
                                        location_name=loc_title,
                                        category_name=self.category_name,
                                        platform=self.platform,
                                        url=ad.get("url", ""),
                                    )
                                    self.signals.status_changed.emit(
                                        f"💾 شماره {p_num} در اکسل {excel_saved.name} ذخیره شد."
                                    )

                                self.signals.ads_extracted.emit(list(extracted_ads))
                                save_extracted_ads(extracted_ads, self.platform, self.phone)

                        if self.chat_message and self.chat_message.strip() and extracted_ads:
                            unmessaged_ads = [ad for ad in extracted_ads if ad.get("token") and ad.get("token") not in extractor.messaged_tokens]
                            target_ads = unmessaged_ads[:self.max_chats]

                            if not unmessaged_ads:
                                self.signals.status_changed.emit(
                                    f"ℹ️ تمام آگهی‌های استخراج‌شده قبلاً پیام دریافت کرده‌اند؛ هیچ پیام تکراری ارسال نشد."
                                )
                            else:
                                self.signals.status_changed.emit(
                                    f"💬 شروع ارسال پیام چت به {len(target_ads)} آگهی جدید {plat_name} (سقف تنظیمی: {self.max_chats} چت)..."
                                )
                                for idx, ad in enumerate(target_ads, 1):
                                    token = ad.get("token")

                                    self.signals.status_changed.emit(
                                        f"💬 [{idx}/{len(target_ads)}] در حال ارسال پیام به فروشنده {plat_name}: «{ad.get('title')}»..."
                                    )
                                    if self.platform == "divar":
                                        sent_ok = await extractor.send_divar_chat_message(
                                            token=token,
                                            message_text=self.chat_message,
                                            progress_callback=lambda msg: self.signals.status_changed.emit(f"[چت دیوار] {msg}"),
                                        )
                                    else:
                                        sent_ok = await extractor.send_sheypoor_chat_message(
                                            listing_id=token,
                                            message_text=self.chat_message,
                                            progress_callback=lambda msg: self.signals.status_changed.emit(f"[چت شیپور] {msg}"),
                                        )

                                    ad["chat_sent"] = sent_ok

                                    self.signals.ads_extracted.emit(list(extracted_ads))
                                    save_extracted_ads(extracted_ads, self.platform, self.phone)

                    details = f"شهرها: {', '.join(self.cities_names)}\nدسته‌بندی: {self.category_name}\n" if self.cities_names else ""
                    self.signals.status_changed.emit(
                        f"✅ فرآیند استخراج و اتوماسیون {plat_name} با موفقیت انجام شد!\n"
                        f"تعداد آگهی‌های استخراج‌شده: {len(extracted_ads)}\n"
                        f"URL: {self.url}\n{details}\n"
                        f"🟢 (راهکار ۱ فعال) کوکی‌ها به صورت زنده از همین مرورگر بروزرسانی خواهند شد."
                    )

                    # ✨ راهکار ۱: بروزرسانی زنده کوکی‌ها از داخل پنجره فعال
                    live_saver_task = None
                    if self.interval_minutes > 0:
                        async def _live_cookie_saver_loop():
                            while True:
                                try:
                                    await asyncio.sleep(self.interval_minutes * 60)
                                    if bm.page.is_closed():
                                        break

                                    live_state = await sm.capture_storage_state(bm.context)
                                    existing = sm.load(self.phone)
                                    has_changes = existing is None or existing.storage_state.has_changes(live_state)

                                    if has_changes:
                                        await sm.save_from_context(
                                            context=bm.context,
                                            phone=self.phone,
                                            metadata={"live_in_browser_capture": True, "url": bm.page.url},
                                            storage_state=live_state,
                                        )
                                        self.signals.status_changed.emit(
                                            f"🔄 (راهکار ۱) کوکی‌ها و توکن‌های نشست زنده [{plat_name}] شماره {self.phone} مستقیماً از مرورگر فعال استخراج و جایگزین شدند."
                                        )
                                except asyncio.CancelledError:
                                    break
                                except Exception as err:
                                    logger.debug("Live in-browser capture error: %s", err)
                                    break

                        live_saver_task = asyncio.create_task(_live_cookie_saver_loop())

                    try:
                        await bm.page.wait_for_event("close", timeout=0)
                    except Exception:
                        pass
                    finally:
                        if live_saver_task and not live_saver_task.done():
                            live_saver_task.cancel()

                self.signals.finished.emit(self.url)

            loop.run_until_complete(_run())

        except Exception as e:
            self.signals.error_occurred.emit(f"خطا: {e}")
        finally:
            self._is_active = False
            loop.close()


# ---------------------------------------------------------------------------
# تب اتوماسیون (با لایه QScrollArea برای اسکرول کامل صفحه)
# ---------------------------------------------------------------------------
class AutomationTab(QWidget):
    """تب اتوماسیون - مدیریت اتوماتیک حساب‌ها، استخراج شماره تماس و ارسال چت."""

    log_message = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cities: List[dict] = []
        self._categories: List[dict] = []
        self._extracted_ads: List[dict] = []
        self._current_worker: Optional[AutomationBrowserWorker] = None

        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._run_periodic_check)

        self._setup_ui()
        self._on_platform_changed()
        self._on_interval_changed()

    def _setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("🤖 اتوماسیون، استخراج آگهی و ارسال چت خودکار")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        hint = QLabel(
            "پلتفرم، شهرها، دسته‌بندی و تعداد صفحات استخراج را مشخص کنید. "
            "برنامه شماره تماس فروشندگان را استخراج کرده و پیام سفارشی را در چت ارسال می‌نماید."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ===== بخش اول: تنظیمات پلتفرم، حساب، تعداد صفحات و زمان‌بندی =====
        settings_group = QGroupBox("⚙️ تنظیمات پلتفرم، حساب کاربری و استخراج آگهی‌ها")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setSpacing(12)
        settings_layout.setContentsMargins(14, 14, 14, 14)

        # --- ۱. انتخاب پلتفرم ---
        plat_col = QVBoxLayout()
        plat_col.setSpacing(4)
        plat_lbl = QLabel("📌 پلتفرم:")
        plat_lbl.setObjectName("subtitleLabel")
        plat_col.addWidget(plat_lbl)

        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumHeight(40)
        self.platform_combo.addItem("🔴 دیوار (Divar)", "divar")
        self.platform_combo.addItem("🔵 شیپور (Sheypoor)", "sheypoor")
        self.platform_combo.currentIndexChanged.connect(self._on_platform_changed)
        plat_col.addWidget(self.platform_combo)
        settings_layout.addLayout(plat_col, stretch=1)

        # --- ۲. انتخاب شماره تلفن ---
        phone_col = QVBoxLayout()
        phone_col.setSpacing(4)
        phone_label = QLabel("📱 حساب کاربری:")
        phone_label.setObjectName("subtitleLabel")
        phone_col.addWidget(phone_label)

        phone_row = QHBoxLayout()
        phone_row.setSpacing(4)
        self.phone_combo = QComboBox()
        self.phone_combo.setMinimumHeight(40)
        self.phone_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.phone_combo.currentIndexChanged.connect(self._update_selection_info)
        phone_row.addWidget(self.phone_combo, stretch=1)

        self.refresh_phones_btn = QPushButton("🔃")
        self.refresh_phones_btn.setObjectName("ghostBtn")
        self.refresh_phones_btn.setToolTip("به‌روزرسانی لیست شماره‌ها")
        self.refresh_phones_btn.setMinimumHeight(40)
        self.refresh_phones_btn.setFixedWidth(40)
        self.refresh_phones_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_phones_btn.clicked.connect(self._reload_phone_numbers)
        phone_row.addWidget(self.refresh_phones_btn)

        phone_col.addLayout(phone_row)
        settings_layout.addLayout(phone_col, stretch=2)

        # --- ۳. ورودی تعداد صفحات استخراج ---
        pages_col = QVBoxLayout()
        pages_col.setSpacing(4)
        pages_label = QLabel("📄 تعداد صفحات استخراج:")
        pages_label.setObjectName("subtitleLabel")
        pages_col.addWidget(pages_label)

        self.pages_spinbox = QSpinBox()
        self.pages_spinbox.setMinimumHeight(40)
        self.pages_spinbox.setRange(1, 50)
        self.pages_spinbox.setValue(3)
        self.pages_spinbox.setSuffix(" صفحه")
        self.pages_spinbox.setToolTip("تعداد صفحاتی که باید اسکرول و آگهی‌های آن استخراج شوند")
        pages_col.addWidget(self.pages_spinbox)
        settings_layout.addLayout(pages_col, stretch=1)

        # --- ۴. تنظیم بازه خودکار سفارشی کوکی‌ها ---
        interval_col = QVBoxLayout()
        interval_col.setSpacing(4)
        interval_label = QLabel("⏱️ زمان بروزرسانی کوکی:")
        interval_label.setObjectName("subtitleLabel")
        interval_col.addWidget(interval_label)

        interval_row = QHBoxLayout()
        interval_row.setSpacing(4)

        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setMinimumHeight(40)
        self.interval_spinbox.setRange(0, 10080)
        self.interval_spinbox.setValue(60)
        self.interval_spinbox.setSuffix(" دک")
        self.interval_spinbox.setToolTip("۰ = غیرفعال | عدد دلخواه دقیقه")
        self.interval_spinbox.valueChanged.connect(self._on_interval_changed)
        interval_row.addWidget(self.interval_spinbox, stretch=1)

        btn_1 = QPushButton("۱دک")
        btn_1.setObjectName("ghostBtn")
        btn_1.setMinimumHeight(40)
        btn_1.clicked.connect(lambda: self.interval_spinbox.setValue(1))
        interval_row.addWidget(btn_1)

        btn_60 = QPushButton("۶۰دک")
        btn_60.setObjectName("ghostBtn")
        btn_60.setMinimumHeight(40)
        btn_60.clicked.connect(lambda: self.interval_spinbox.setValue(60))
        interval_row.addWidget(btn_60)

        btn_off = QPushButton("❌")
        btn_off.setObjectName("dangerBtn")
        btn_off.setMinimumHeight(40)
        btn_off.setToolTip("غیرفعال‌سازی بررسی کوکی‌ها")
        btn_off.clicked.connect(lambda: self.interval_spinbox.setValue(0))
        interval_row.addWidget(btn_off)

        interval_col.addLayout(interval_row)
        settings_layout.addLayout(interval_col, stretch=2)

        layout.addWidget(settings_group)

        # ===== بخش دوم: شهرها و دسته‌بندی کشیده از نظر طولی (Spacious & Tall Height) =====
        top_splitter = QSplitter(Qt.Horizontal)
        self.top_splitter = top_splitter
        top_splitter.setMinimumHeight(380)

        # ----- بخش شهرها -----
        cities_group = QGroupBox("🏙️ انتخاب شهرها")
        self.cities_group = cities_group
        cities_layout = QVBoxLayout(cities_group)
        cities_layout.setSpacing(8)
        cities_layout.setContentsMargins(12, 12, 12, 12)

        city_search_row = QHBoxLayout()
        self.city_search = QLineEdit()
        self.city_search.setMinimumHeight(38)
        self.city_search.setPlaceholderText("🔍 جستجوی شهر... (مثال: تهران، اسلامشهر)")
        self.city_search.textChanged.connect(self._filter_cities)
        city_search_row.addWidget(self.city_search, stretch=1)

        self.selected_cities_count = QLabel("0 شهر")
        self.selected_cities_count.setObjectName("mutedLabel")
        city_search_row.addWidget(self.selected_cities_count)
        cities_layout.addLayout(city_search_row)

        self.city_list = QListWidget()
        self.city_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.city_list.setMinimumHeight(280)
        self.city_list.itemSelectionChanged.connect(self._update_selection_info)
        cities_layout.addWidget(self.city_list, stretch=1)

        city_btn_row = QHBoxLayout()
        self.select_all_cities_btn = QPushButton("✅ انتخاب همه")
        self.select_all_cities_btn.setObjectName("successBtn")
        self.select_all_cities_btn.setMinimumHeight(36)
        self.select_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_cities_btn.clicked.connect(lambda: self.city_list.selectAll())
        city_btn_row.addWidget(self.select_all_cities_btn)

        self.deselect_all_cities_btn = QPushButton("❌ حذف انتخاب")
        self.deselect_all_cities_btn.setObjectName("dangerBtn")
        self.deselect_all_cities_btn.setMinimumHeight(36)
        self.deselect_all_cities_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_cities_btn.clicked.connect(lambda: self.city_list.clearSelection())
        city_btn_row.addWidget(self.deselect_all_cities_btn)
        cities_layout.addLayout(city_btn_row)
        top_splitter.addWidget(cities_group)

        # ----- بخش دسته‌بندی‌ها -----
        cat_group = QGroupBox("📂 انتخاب دسته‌بندی و زیردسته‌ها")
        self.cat_group = cat_group
        cat_layout = QVBoxLayout(cat_group)
        cat_layout.setSpacing(8)
        cat_layout.setContentsMargins(12, 12, 12, 12)

        cat_search_row = QHBoxLayout()
        self.category_search = QLineEdit()
        self.category_search.setMinimumHeight(38)
        self.category_search.setPlaceholderText("🔍 جستجوی دسته‌بندی و زیردسته...")
        self.category_search.textChanged.connect(self._filter_categories)
        cat_search_row.addWidget(self.category_search, stretch=1)

        self.selected_category_label = QLabel("همه دسته‌ها")
        self.selected_category_label.setObjectName("mutedLabel")
        cat_search_row.addWidget(self.selected_category_label)
        cat_layout.addLayout(cat_search_row)

        self.category_list = QListWidget()
        self.category_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.category_list.setMinimumHeight(280)
        self.category_list.itemSelectionChanged.connect(self._update_selection_info)
        cat_layout.addWidget(self.category_list, stretch=1)

        cat_btn_row = QHBoxLayout()
        self.clear_category_btn = QPushButton("❌ حذف فیلتر دسته‌بندی")
        self.clear_category_btn.setObjectName("ghostBtn")
        self.clear_category_btn.setMinimumHeight(36)
        self.clear_category_btn.setCursor(Qt.PointingHandCursor)
        self.clear_category_btn.clicked.connect(self._clear_category)
        cat_btn_row.addWidget(self.clear_category_btn)
        cat_layout.addLayout(cat_btn_row)
        top_splitter.addWidget(cat_group)

        top_splitter.setSizes([500, 500])
        layout.addWidget(top_splitter)

        # ===== بخش سوم: استخراج شماره تماس و ارسال پیام در چت =====
        options_group = QGroupBox("📞 استخراج شماره تماس و 💬 ارسال پیام خودکار (دیوار و شیپور)")
        self.options_group = options_group
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(10)
        options_layout.setContentsMargins(14, 14, 14, 14)

        # ✨ گزینه‌ی همگام‌سازی استخراج شماره دقیقاً برای آگهی‌های پیام چت
        self.sync_phone_chat_checkbox = QCheckBox("🔗 استخراج هم‌زمان شماره تماس برای همان آگهی‌هایی که پیام چت فرستاده می‌شود (پیش‌فرض)")
        self.sync_phone_chat_checkbox.setObjectName("titleLabel")
        self.sync_phone_chat_checkbox.setCursor(Qt.PointingHandCursor)
        self.sync_phone_chat_checkbox.setChecked(True)
        options_layout.addWidget(self.sync_phone_chat_checkbox)

        # --- ۱. تنظیمات استخراج شماره تماس جداگانه ---
        phone_top_row = QHBoxLayout()
        phone_top_row.setSpacing(10)

        self.extract_phone_checkbox = QCheckBox("📞 استخراج مجزا شماره تماس سایر آگهی‌ها")
        self.extract_phone_checkbox.setObjectName("subtitleLabel")
        self.extract_phone_checkbox.setCursor(Qt.PointingHandCursor)
        self.extract_phone_checkbox.setChecked(True)
        phone_top_row.addWidget(self.extract_phone_checkbox, stretch=1)

        max_phones_lbl = QLabel("📞 سقف استخراج شماره مجزا:")
        max_phones_lbl.setObjectName("subtitleLabel")
        phone_top_row.addWidget(max_phones_lbl)

        self.max_phones_spinbox = QSpinBox()
        self.max_phones_spinbox.setMinimumHeight(38)
        self.max_phones_spinbox.setRange(0, 1000)
        self.max_phones_spinbox.setValue(10)          # پیش‌فرض ۱۰ شماره
        self.max_phones_spinbox.setSuffix(" شماره")
        self.max_phones_spinbox.setToolTip("۰ = عدم استخراج شماره مجزا | یا تعیین عدد دلخواه")
        phone_top_row.addWidget(self.max_phones_spinbox)

        btn_p5 = QPushButton("۵ شماره")
        btn_p5.setObjectName("ghostBtn")
        btn_p5.setMinimumHeight(38)
        btn_p5.clicked.connect(lambda: self.max_phones_spinbox.setValue(5))
        phone_top_row.addWidget(btn_p5)

        btn_p10 = QPushButton("۱۰ شماره")
        btn_p10.setObjectName("ghostBtn")
        btn_p10.setMinimumHeight(38)
        btn_p10.clicked.connect(lambda: self.max_phones_spinbox.setValue(10))
        phone_top_row.addWidget(btn_p10)

        btn_p_off = QPushButton("❌ غیرفعال")
        btn_p_off.setObjectName("dangerBtn")
        btn_p_off.setMinimumHeight(38)
        btn_p_off.clicked.connect(lambda: self.max_phones_spinbox.setValue(0))
        phone_top_row.addWidget(btn_p_off)

        options_layout.addLayout(phone_top_row)

        # --- ۲. تنظیمات ارسال چت خودکار ---
        chat_top_row = QHBoxLayout()
        chat_top_row.setSpacing(10)

        self.chat_enable_checkbox = QCheckBox("✉️ ارسال خودکار پیام به چت فروشندگان پس از استخراج آگهی‌ها")
        self.chat_enable_checkbox.setObjectName("subtitleLabel")
        self.chat_enable_checkbox.setCursor(Qt.PointingHandCursor)
        self.chat_enable_checkbox.setChecked(True)
        chat_top_row.addWidget(self.chat_enable_checkbox, stretch=1)

        max_chats_lbl = QLabel("✉️ حداکثر تعداد پیام ارسالی:")
        max_chats_lbl.setObjectName("subtitleLabel")
        chat_top_row.addWidget(max_chats_lbl)

        self.max_chats_spinbox = QSpinBox()
        self.max_chats_spinbox.setMinimumHeight(38)
        self.max_chats_spinbox.setRange(1, 30)       # محدوده بین ۱ تا ۳۰ پیام
        self.max_chats_spinbox.setValue(10)          # پیش‌فرض ۱۰ پیام
        self.max_chats_spinbox.setSuffix(" چت")
        self.max_chats_spinbox.setToolTip("حداقل ۱ و حداکثر ۳۰ چت در هر نوبت نادیده گرفتن چت‌های تکراری")
        chat_top_row.addWidget(self.max_chats_spinbox)

        options_layout.addLayout(chat_top_row)

        self.chat_message_input = QTextEdit()
        self.chat_message_input.setMinimumHeight(80)
        self.chat_message_input.setMaximumHeight(120)
        self.chat_message_input.setPlaceholderText("متن پیام سفارشی خود را جهت ارسال در چت وارد کنید (مثال: سلام، آگهی شما را دیدم، آیا موجود است؟)")
        options_layout.addWidget(self.chat_message_input)

        layout.addWidget(options_group)

        # ===== بخش چهارم: اطلاعات و اجرای اتوماسیون =====
        info_group = QGroupBox("📋 اطلاعات و اجرای مرورگر")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)

        self.url_display = QTextEdit()
        self.url_display.setReadOnly(True)
        self.url_display.setMaximumHeight(80)
        self.url_display.setPlaceholderText("اطلاعات پلتفرم و لینک...")
        info_layout.addWidget(self.url_display)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.start_btn = QPushButton("🚀 شروع - باز کردن مرورگر و استخراج آگهی‌ها")
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

        # ===== بخش پنجم: جدول نمایش آگهی‌های استخراج‌شده =====
        results_group = QGroupBox("📊 آگهی‌های استخراج‌شده (غیرتکراری)")
        results_layout = QVBoxLayout(results_group)
        results_layout.setSpacing(10)
        results_layout.setContentsMargins(14, 14, 14, 14)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(["#", "عنوان آگهی", "شماره تماس", "لینک مستقیم آگهی", "وضعیت چت", "زمان استخراج"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.results_table.setMinimumHeight(260)
        results_layout.addWidget(self.results_table)

        results_bar = QHBoxLayout()
        self.ads_count_lbl = QLabel("تعداد آگهی‌های یافت‌شده: ۰")
        self.ads_count_lbl.setObjectName("subtitleLabel")
        results_bar.addWidget(self.ads_count_lbl)

        results_bar.addStretch()

        self.copy_all_btn = QPushButton("📋 کپی تمام لینک‌ها")
        self.copy_all_btn.setObjectName("successBtn")
        self.copy_all_btn.setMinimumHeight(38)
        self.copy_all_btn.setCursor(Qt.PointingHandCursor)
        self.copy_all_btn.clicked.connect(self._copy_all_links)
        results_bar.addWidget(self.copy_all_btn)

        self.clear_table_btn = QPushButton("🗑️ پاکسازی جدول")
        self.clear_table_btn.setObjectName("ghostBtn")
        self.clear_table_btn.setMinimumHeight(38)
        self.clear_table_btn.setCursor(Qt.PointingHandCursor)
        self.clear_table_btn.clicked.connect(self._clear_results_table)
        results_bar.addWidget(self.clear_table_btn)

        results_layout.addLayout(results_bar)
        layout.addWidget(results_group)

        scroll_area.setWidget(container)
        outer_layout.addWidget(scroll_area)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    def restyle(self):
        for w in (self.city_list, self.category_list, self.url_display,
                  self.city_search, self.category_search, self.phone_combo,
                  self.interval_spinbox, self.platform_combo, self.pages_spinbox,
                  self.max_chats_spinbox, self.max_phones_spinbox, self.results_table,
                  self.chat_message_input, self.sync_phone_chat_checkbox):
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
                self.top_splitter.setSizes([320, 320])
            elif w >= 680 and self.top_splitter.orientation() != Qt.Horizontal:
                self.top_splitter.setOrientation(Qt.Horizontal)
                self.top_splitter.setSizes([500, 500])
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

    def _on_interval_changed(self):
        minutes = self.interval_spinbox.value()
        if minutes > 0:
            ms = minutes * 60 * 1000
            self._auto_timer.setInterval(ms)
            if not self._auto_timer.isActive():
                self._auto_timer.start()
            self._log("INFO", f"[اتوماسیون] بررسی خودکار پس‌زمینه کوکی‌ها روی هر {minutes} دقیقه تنظیم شد")
        else:
            self._auto_timer.stop()
            self._log("INFO", "[اتوماسیون] بررسی خودکار پس‌زمینه کوکی‌ها غیرفعال گردید (مقدار ۰ دقیقه)")

    def _run_periodic_check(self):
        if self.is_browser_open():
            return

        minutes = self.interval_spinbox.value()
        self._log("INFO", f"[اتوماسیون] شروع بررسی خودکار پس‌زمینه کوکی‌ها (دوره {minutes} دقیقه‌ای)...")
        plat = self.get_selected_platform()
        phone = self.get_selected_phone()

        worker = BackgroundPeriodicRefresherWorker(platform=plat, phone=phone)
        worker.signals.status_changed.connect(self._on_status_changed)
        QThreadPool.globalInstance().start(worker)

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
        self.start_btn.setText(f"🚀 شروع - باز کردن {plat_name} و استخراج آگهی‌ها")

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

        if plat == "sheypoor":
            url = build_sheypoor_url(cities_data, category_slug)
        else:
            url = build_divar_url(cities_data, category_slug)

        pages = self.pages_spinbox.value()
        max_c = self.max_chats_spinbox.value()
        max_p = self.max_phones_spinbox.value()
        sync_active = self.sync_phone_chat_checkbox.isChecked()

        chat_status = f"فعال 🟢 (حداکثر {max_c} چت)" if self.chat_enable_checkbox.isChecked() else "غیرفعال"
        if sync_active and self.chat_enable_checkbox.isChecked():
            phone_status = f"همگام با چت 🔗 (همان {max_c} آگهی)"
        else:
            phone_status = f"فعال 🟢 (حداکثر {max_p} شماره)" if (self.extract_phone_checkbox.isChecked() and max_p > 0) else "غیرفعال"

        city_info = f"🏙️ شهرها ({len(cities_names)}): {', '.join(cities_names)}" if cities_names else "🏙️ همه شهرها (سراسر ایران)"
        self.url_display.setPlainText(
            f"📌 پلتفرم: {plat_name}  |  📄 صفحات: {pages} صفحه  |  📞 استخراج شماره: {phone_status}  |  💬 چت: {chat_status}\n"
            f"📱 حساب انتخاب‌شده: {selected_phone}\n"
            f"🌐 لینک فیلترشده: {url}\n"
            f"{city_info}"
        )

    # ------------------------------------------------------------------
    # پردازش آگهی‌های استخراج‌شده و نمایش آنی و زنده در جدول
    # ------------------------------------------------------------------
    @Slot(list)
    def _on_ads_extracted(self, ads: List[dict]):
        self._extracted_ads = ads
        self.results_table.setRowCount(0)
        self.results_table.setRowCount(len(self._extracted_ads))

        for row, ad in enumerate(self._extracted_ads):
            item_idx = QTableWidgetItem(str(row + 1))
            item_idx.setTextAlignment(Qt.AlignCenter)

            item_title = QTableWidgetItem(ad.get("title", ""))

            p_val = ad.get("phone_number", "در حال استخراج...")
            item_phone = QTableWidgetItem(p_val)
            item_phone.setTextAlignment(Qt.AlignCenter)
            if p_val and p_val not in ("استخراج‌نشده", "در حال استخراج...", "ناموجود/مخفی", "فقط چت (شماره مخفی)", "ثبت‌نشده در شیپور", "تماس ناشناس (بدون شماره)"):
                item_phone.setForeground(Qt.darkGreen)
            elif "مخفی" in p_val or "فقط چت" in p_val or "ناشناس" in p_val:
                item_phone.setForeground(Qt.darkYellow)

            item_url = QTableWidgetItem(ad.get("url", ""))
            item_url.setForeground(Qt.blue)

            chat_status_str = "ارسال شد 💬" if ad.get("chat_sent") else "ارسال نشده"
            item_chat = QTableWidgetItem(chat_status_str)
            item_chat.setTextAlignment(Qt.AlignCenter)

            item_time = QTableWidgetItem(ad.get("extracted_at", ""))
            item_time.setTextAlignment(Qt.AlignCenter)

            self.results_table.setItem(row, 0, item_idx)
            self.results_table.setItem(row, 1, item_title)
            self.results_table.setItem(row, 2, item_phone)
            self.results_table.setItem(row, 3, item_url)
            self.results_table.setItem(row, 4, item_chat)
            self.results_table.setItem(row, 5, item_time)

        self.ads_count_lbl.setText(f"تعداد آگهی‌های یافت‌شده: {len(self._extracted_ads)}")

    def _copy_all_links(self):
        if not self._extracted_ads:
            QMessageBox.information(self, "کپی لینک‌ها", "هیچ آگهی در جدول برای کپی وجود ندارد.")
            return

        urls = [ad.get("url", "") for ad in self._extracted_ads if ad.get("url")]
        if urls:
            clipboard = QGuiApplication.clipboard()
            clipboard.setText("\n".join(urls))
            QMessageBox.information(
                self,
                "کپی لینک‌ها",
                f"✅ تعداد {len(urls)} لینک آگهی با موفقیت در Clipboard کپی شد!",
            )

    def _clear_results_table(self):
        self.results_table.setRowCount(0)
        self._extracted_ads = []
        self.ads_count_lbl.setText("تعداد آگهی‌های یافت‌شده: ۰")

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

        interval_mins = self.interval_spinbox.value()
        max_p = self.pages_spinbox.value()
        max_c = self.max_chats_spinbox.value()
        max_ph = self.max_phones_spinbox.value() if self.extract_phone_checkbox.isChecked() else 0
        sync_phone_chat = self.sync_phone_chat_checkbox.isChecked()

        # چت متنی
        chat_msg = None
        if self.chat_enable_checkbox.isChecked():
            chat_msg = self.chat_message_input.toPlainText().strip()
            if not chat_msg:
                QMessageBox.warning(self, "متن چت خالی است", "لطفاً متن پیام چت را وارد کنید یا گزینه‌ی ارسال پیام را غیرفعال کنید.")
                return

        self._log(
            "INFO",
            f"[اتوماسیون] شروع اجرای مرورگر {plat_name} برای شماره {selected_phone} (همگام‌سازی استخراج شماره با چت: {'فعال' if sync_phone_chat else 'غیرفعال'})"
        )

        self.start_btn.setEnabled(False)
        self.start_btn.setText(f"⏳ در حال استخراج و اجرای {plat_name}...")

        worker = AutomationBrowserWorker(
            platform=plat,
            url=url,
            cities_names=cities_names,
            category_name=category_name,
            phone=selected_phone,
            interval_minutes=interval_mins,
            max_pages=max_p,
            chat_message=chat_msg,
            max_chats=max_c,
            extract_phone=(max_ph > 0 or sync_phone_chat),
            max_phones=max_ph,
            sync_phone_chat=sync_phone_chat,
        )
        worker.signals.status_changed.connect(self._on_status_changed)
        worker.signals.error_occurred.connect(self._on_error)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.ads_extracted.connect(self._on_ads_extracted)
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
        return self._current_worker is not None and self._current_worker.is_browser_running()

    def _close_browser(self):
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
