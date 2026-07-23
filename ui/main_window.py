# -*- coding: utf-8 -*-
"""
MainWindow - پنجره اصلی برنامه با چیدمان مدرن.

چیدمان (نسخه ۳):
- سایدبار ناوبری «جمع‌شونده» سمت راست با آیکون‌های SVG برداری
- هدر پویا با دکمهٔ منو (☰) برای جمع/باز کردن سایدبار
- فونت وزیرمتن + دو تم تیره/روشن
- ناحیهٔ محتوای اصلی با QStackedWidget

بخش‌ها: 🏠 دیوار | 📢 شیپور | 🤖 اتوماسیون | 📋 لاگ‌ها
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Slot, Signal, QObject, QSettings, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logger_manager import setup_logging, register_ui_callback
from modules.login import LoginManager as DivarLoginManager
from modules.sheypoor import LoginManager as SheypoorLoginManager

from ui.platform_tab import PlatformTab
from ui.logs_tab import LogsTab
from ui.automation_tab import AutomationTab
from ui.schedule_tab import ScheduleTab
from ui import icons
from ui.theme import (
    apply_theme,
    colors,
    load_saved_theme,
    toggle_theme,
    is_dark,
    THEME_DARK,
)

# عرض سایدبار در دو حالت
SIDEBAR_EXPANDED = 250
SIDEBAR_COLLAPSED = 84

# تعریف بخش‌ها: (کلید، نام آیکون، برچسب، عنوان هدر، زیرعنوان هدر)
NAV_ITEMS = [
    ("divar",      "home",      "دیوار",      "دیوار",       "مدیریت ورود و Session حساب دیوار"),
    ("sheypoor",   "megaphone", "شیپور",      "شیپور",       "مدیریت ورود و Session حساب شیپور"),
    ("automation", "robot",     "اتوماسیون",  "اتوماسیون",   "انتخاب شهر و دسته‌بندی و باز کردن دیوار"),
    ("logs",       "logs",      "لاگ‌ها",      "لاگ‌های سیستم", "تمام رویدادها و خطاهای برنامه"),
    ("schedules",  "clock",     "زمانبندی‌ها", "زمانبندی‌های فعال", "نمایش و پایش تمام زمانبندی‌های خودکار"),
]


class _LogBridge(QObject):
    """پل thread-safe برای انتقال لاگ‌ها از worker thread به UI thread."""
    log_received = Signal(str, str)


class MainWindow(QMainWindow):
    """پنجره اصلی برنامه با چیدمان سایدبار جمع‌شونده + هدر."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Divar & Sheypoor Manager")
        self.setMinimumSize(720, 540)
        self.resize(1100, 760)

        self._log_bridge = _LogBridge()
        self._nav_buttons: list[QPushButton] = []
        self._active_index = 0
        self._collapsed = self._load_collapsed_state()

        self._setup_ui()
        self._setup_logging()
        self._refresh_icons()
        self._apply_sidebar_state()
        self._on_nav(0)  # بخش پیش‌فرض: دیوار

    # ------------------------------------------------------------------
    # ساخت رابط کاربری
    # ------------------------------------------------------------------
    def _setup_ui(self):
        central = QWidget()
        central.setLayoutDirection(Qt.RightToLeft)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content_area(), stretch=1)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        """ساخت سایدبار ناوبری جمع‌شونده."""
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(SIDEBAR_EXPANDED)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(6)

        # --- برند برنامه ---
        self.brand_title = QLabel("دیوار منیجر")
        self.brand_title.setObjectName("appTitle")
        layout.addWidget(self.brand_title)

        self.accent_bar = QLabel()
        self.accent_bar.setObjectName("brandAccent")
        self.accent_bar.setFixedHeight(5)
        self.accent_bar.setFixedWidth(40)
        layout.addWidget(self.accent_bar)

        self.brand_sub = QLabel("مدیریت هوشمند دیوار و شیپور")
        self.brand_sub.setObjectName("appSubtitle")
        layout.addWidget(self.brand_sub)

        layout.addSpacing(18)

        # --- برچسب منو ---
        self.nav_label = QLabel("منوی اصلی")
        self.nav_label.setObjectName("navSectionLabel")
        layout.addWidget(self.nav_label)
        layout.addSpacing(4)

        # --- دکمه‌های ناوبری ---
        for idx, (_key, icon_name, label, _t, _s) in enumerate(NAV_ITEMS):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(22, 22))
            btn.setToolTip(label)
            btn.clicked.connect(lambda _=False, i=idx: self._on_nav(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # --- کنترل‌های پایین سایدبار ---
        self.btn_theme = QPushButton("تم")
        self.btn_theme.setObjectName("ghostBtn")
        self.btn_theme.setCursor(Qt.PointingHandCursor)
        self.btn_theme.setIconSize(QSize(20, 20))
        self.btn_theme.clicked.connect(self._on_toggle_theme)
        layout.addWidget(self.btn_theme)

        self.btn_close_browser = QPushButton("بستن مرورگر")
        self.btn_close_browser.setObjectName("dangerBtn")
        self.btn_close_browser.setCursor(Qt.PointingHandCursor)
        self.btn_close_browser.setIconSize(QSize(20, 20))
        self.btn_close_browser.clicked.connect(self._close_all_browsers)
        layout.addWidget(self.btn_close_browser)

        return self.sidebar

    def _build_content_area(self) -> QWidget:
        """ساخت ناحیهٔ محتوا: هدر (با دکمهٔ منو) + QStackedWidget."""
        content = QWidget()
        content.setObjectName("contentArea")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- هدر پویا ---
        self.header_bar = QFrame()
        self.header_bar.setObjectName("headerBar")
        self.header_bar.setFixedHeight(78)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(24, 12, 30, 12)
        header_layout.setSpacing(16)

        # دکمهٔ جمع/باز کردن سایدبار
        self.btn_menu = QPushButton()
        self.btn_menu.setObjectName("sidebarToggle")
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.setIconSize(QSize(24, 24))
        self.btn_menu.setToolTip("جمع/باز کردن منو")
        self.btn_menu.clicked.connect(self._toggle_sidebar)
        header_layout.addWidget(self.btn_menu, alignment=Qt.AlignVCenter)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        self.header_title = QLabel("")
        self.header_title.setObjectName("headerTitle")
        header_text.addWidget(self.header_title)
        self.header_subtitle = QLabel("")
        self.header_subtitle.setObjectName("headerSubtitle")
        header_text.addWidget(self.header_subtitle)
        header_layout.addLayout(header_text, stretch=1)

        layout.addWidget(self.header_bar)

        # --- صفحات محتوا ---
        self.stack = QStackedWidget()

        self.divar_tab = PlatformTab(
            platform_name="دیوار", platform_key="divar", color="#A62626",
            code_length=6, login_manager_factory=self._create_divar_manager,
        )
        self.divar_tab.log_message.connect(self._on_log)
        self.stack.addWidget(self.divar_tab)

        self.sheypoor_tab = PlatformTab(
            platform_name="شیپور", platform_key="sheypoor", color="#3568d4",
            code_length=4, login_manager_factory=self._create_sheypoor_manager,
        )
        self.sheypoor_tab.log_message.connect(self._on_log)
        self.stack.addWidget(self.sheypoor_tab)

        self.automation_tab = AutomationTab()
        self.automation_tab.log_message.connect(self._on_log)
        self.stack.addWidget(self.automation_tab)

        self.logs_tab = LogsTab()
        self.stack.addWidget(self.logs_tab)

        self.schedule_tab = ScheduleTab()
        self.stack.addWidget(self.schedule_tab)

        self.automation_tab.schedules_changed.connect(self.schedule_tab.update_schedules)

        layout.addWidget(self.stack, stretch=1)

        return content

    # ------------------------------------------------------------------
    # آیکون‌ها
    # ------------------------------------------------------------------
    def _set_button_icon(self, btn: QPushButton, icon_name: str, color: str,
                         size: int = 22, emoji_fallback_label: str | None = None):
        """تنظیم آیکون SVG روی دکمه؛ در نبود SVG از ایموجی استفاده می‌شود."""
        qicon = icons.icon(icon_name, color, size)
        if qicon is not None:
            btn.setIcon(qicon)
        elif emoji_fallback_label is not None:
            btn.setIcon(QIcon())
            if emoji_fallback_label and not btn.text().startswith(icons.emoji(icon_name)):
                btn.setText(f"{icons.emoji(icon_name)}  {emoji_fallback_label}")

    def _refresh_icons(self):
        """به‌روزرسانی رنگ/آیکون همهٔ دکمه‌ها بر اساس تم و بخش فعال."""
        c = colors()
        muted = c["text_muted"]
        accent = "#A62626"

        self._set_button_icon(self.btn_menu, "menu", c["text"], 24)

        for i, btn in enumerate(self._nav_buttons):
            icon_name = NAV_ITEMS[i][1]
            color = accent if i == self._active_index else muted
            self._set_button_icon(btn, icon_name, color, 22, NAV_ITEMS[i][2])

        theme_icon_name = "sun" if is_dark() else "moon"
        self._set_button_icon(self.btn_theme, theme_icon_name, muted, 20, "تم")

        self._set_button_icon(self.btn_close_browser, "close", "#ffffff", 20, "بستن مرورگر")

    # ------------------------------------------------------------------
    # ناوبری
    # ------------------------------------------------------------------
    def _on_nav(self, index: int):
        """تعویض بخش فعال و به‌روزرسانی هدر و استایل/آیکون دکمه‌ها."""
        self._active_index = index
        self.stack.setCurrentIndex(index)

        _key, _icon, _label, title, subtitle = NAV_ITEMS[index]
        self.header_title.setText(title)
        self.header_subtitle.setText(subtitle)

        for i, btn in enumerate(self._nav_buttons):
            btn.setObjectName("navBtnActive" if i == index else "navBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._refresh_icons()

    # ------------------------------------------------------------------
    # جمع/باز کردن سایدبار
    # ------------------------------------------------------------------
    def _load_collapsed_state(self) -> bool:
        try:
            settings = QSettings("DivarManager", "DivarManager")
            return bool(settings.value("ui/sidebar_collapsed", False))
        except Exception:
            return False

    def _save_collapsed_state(self):
        try:
            settings = QSettings("DivarManager", "DivarManager")
            settings.setValue("ui/sidebar_collapsed", self._collapsed)
        except Exception:
            pass

    def _toggle_sidebar(self):
        self._collapsed = not self._collapsed
        self._apply_sidebar_state()
        self._save_collapsed_state()

    def _apply_sidebar_state(self):
        """اعمال حالت جمع/باز سایدبار روی عرض و متن ویجت‌ها."""
        if self._collapsed:
            self.sidebar.setFixedWidth(SIDEBAR_COLLAPSED)
            self.brand_sub.hide()
            self.accent_bar.hide()
            self.nav_label.hide()
            self.brand_title.setText("دم")
            self.brand_title.setAlignment(Qt.AlignCenter)
            for i, btn in enumerate(self._nav_buttons):
                btn.setText("")
                btn.setToolTip(NAV_ITEMS[i][2])
            self.btn_theme.setText("")
            self.btn_theme.setToolTip("تغییر تم")
            self.btn_close_browser.setText("")
            self.btn_close_browser.setToolTip("بستن مرورگر")
        else:
            self.sidebar.setFixedWidth(SIDEBAR_EXPANDED)
            self.brand_sub.show()
            self.accent_bar.show()
            self.nav_label.show()
            self.brand_title.setText("دیوار منیجر")
            self.brand_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for i, btn in enumerate(self._nav_buttons):
                btn.setText(NAV_ITEMS[i][2])
                btn.setToolTip(NAV_ITEMS[i][2])
            self.btn_theme.setText("تغییر تم")
            self.btn_close_browser.setText("بستن مرورگر")

        self._refresh_icons()

    # ------------------------------------------------------------------
    # لاگ
    # ------------------------------------------------------------------
    def _setup_logging(self):
        setup_logging()
        self._log_bridge.log_received.connect(self.logs_tab.append_log)
        register_ui_callback(self._ui_log_callback)
        self.logs_tab.append_log("INFO", "✅ برنامه با موفقیت شروع شد")
        self.logs_tab.append_log("INFO", "🔄 در حال بررسی Sessionهای ذخیره‌شده...")

    def _ui_log_callback(self, level: str, message: str):
        self._log_bridge.log_received.emit(level, message)

    @Slot(str, str)
    def _on_log(self, level: str, message: str):
        self.logs_tab.append_log(level, message)

    # ------------------------------------------------------------------
    # سوییچ تم
    # ------------------------------------------------------------------
    def _on_toggle_theme(self):
        """سوییچ زنده بین تم تیره و روشن."""
        app = QApplication.instance()
        new_theme = toggle_theme(app)
        try:
            self._on_nav(self._active_index)
            self._refresh_icons()
            self._apply_sidebar_state()
            self.divar_tab.restyle()
            self.sheypoor_tab.restyle()
            self.automation_tab.restyle()
            self.logs_tab.restyle()
            self.schedule_tab.restyle()
        except Exception:
            pass
        try:
            self.logs_tab.append_log(
                "INFO",
                f"🎨 تم برنامه تغییر کرد: {'تیره 🌙' if new_theme == 'dark' else 'روشن ☀️'}",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # فکتوری‌های Login
    # ------------------------------------------------------------------
    def _create_divar_manager(self, browser_manager, session_manager, code_provider):
        return DivarLoginManager(
            browser_manager=browser_manager,
            session_manager=session_manager,
            code_provider=code_provider,
        )

    def _create_sheypoor_manager(self, browser_manager, session_manager, code_provider):
        return SheypoorLoginManager(
            browser_manager=browser_manager,
            session_manager=session_manager,
            code_provider=code_provider,
        )

    # ------------------------------------------------------------------
    # بستن مرورگرها
    # ------------------------------------------------------------------
    def _close_all_browsers(self):
        """بستن مرورگرهای تمام تب‌ها به صورت هوشمند."""
        closed_count = 0

        if hasattr(self.divar_tab, "is_browser_open") and self.divar_tab.is_browser_open():
            self.divar_tab._on_close_browser_clicked()
            closed_count += 1

        if hasattr(self.sheypoor_tab, "is_browser_open") and self.sheypoor_tab.is_browser_open():
            self.sheypoor_tab._on_close_browser_clicked()
            closed_count += 1

        if hasattr(self.automation_tab, "is_browser_open") and self.automation_tab.is_browser_open():
            self.automation_tab._close_browser()
            closed_count += 1

        if closed_count == 0:
            QMessageBox.information(
                self,
                "بستن مرورگر",
                "ℹ️ هیچ مرورگر بازی پیدا نشد.",
            )
            self.logs_tab.append_log("INFO", "ℹ️ هیچ مرورگری برای بستن باز نبود.")
        else:
            self.logs_tab.append_log("INFO", f"🔴 درخواست بستن {closed_count} مرورگر باز ارسال شد.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("DivarManager")
    app.setOrganizationName("DivarManager")

    load_saved_theme()
    apply_theme(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
