# -*- coding: utf-8 -*-
"""
theme.py - موتور تم مرکزی پروژه Divar Manager.

این ماژول تمام استایل‌دهی برنامه را به‌صورت متمرکز مدیریت می‌کند:
- دو تم «تیره» و «روشن» با توکن‌های رنگی مجزا
- رنگ اصلی (Accent) قرمز دیوار حفظ شده است
- امکان سوییچ زندهٔ تم بدون راه‌اندازی مجدد برنامه
- ذخیرهٔ انتخاب کاربر بین اجراها (QSettings)

روش کار: به‌جای setStyleSheet داخل هر ویجت، از objectNameها استفاده می‌کنیم
و یک StyleSheet سراسری (QSS) همه‌چیز را کنترل می‌کند. به این ترتیب با یک
فراخوانی app.setStyleSheet() کل برنامه به‌روز می‌شود و سوییچ تم واقعی است.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# نام تم‌ها
# ---------------------------------------------------------------------------
THEME_DARK = "dark"
THEME_LIGHT = "light"

_SETTING_KEY = "ui/theme"

# مسیر فونت‌های همراه برنامه (وزیرمتن)
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# نام فونت اصلی (پس از بارگذاری). اگر موجود نبود، fallback استفاده می‌شود.
APP_FONT_FAMILY = "Vazirmatn"
_FALLBACK_FONT_FAMILY = "Segoe UI"

_fonts_loaded = False

# ---------------------------------------------------------------------------
# توکن‌های رنگی هر تم
# ---------------------------------------------------------------------------
# رنگ برند دیوار (در هر دو تم ثابت می‌ماند - طبق درخواست کاربر)
ACCENT_DIVAR = "#A62626"
ACCENT_DIVAR_HOVER = "#c0392b"
ACCENT_DIVAR_PRESSED = "#8f1f1f"

ACCENT_SHEYPOOR = "#3568d4"
ACCENT_SHEYPOOR_HOVER = "#2a55b3"

_THEMES: Dict[str, Dict[str, str]] = {
    THEME_DARK: {
        "window_bg":   "#1b1d2a",   # پس‌زمینهٔ اصلی پنجره
        "surface":     "#242738",   # کارت‌ها / پنل‌ها / تب انتخاب‌شده
        "surface_alt": "#2c3044",   # ورودی‌ها و آیتم‌ها
        "surface_hover": "#333852", # هاور آیتم‌ها
        "border":      "#3a3f5a",   # خطوط مرزی
        "border_soft": "#2f3348",
        "text":        "#e7e9f3",   # متن اصلی
        "text_muted":  "#a2a8c4",   # متن کم‌رنگ
        "text_faint":  "#6d7296",   # متن بسیار کم‌رنگ
        "selection_bg": ACCENT_DIVAR,
        "selection_fg": "#ffffff",
        "scrollbar":   "#2c3044",
        "scroll_handle": "#4a5072",
        "scroll_handle_hover": "#5c6390",
        "danger":      "#e05555",
        "danger_hover": "#c84343",
        "success":     "#33b074",
        "success_hover": "#2a9461",
        "link":        "#7aa2ff",
        "shadow":      "#000000",
        "sidebar_bg":  "#151722",
        "nav_active_bg": "#332226",
        "header_bg":   "#1b1d2a",
    },
    THEME_LIGHT: {
        "window_bg":   "#f3f4f9",
        "surface":     "#ffffff",
        "surface_alt": "#f7f8fc",
        "surface_hover": "#eceef6",
        "border":      "#dfe2ee",
        "border_soft": "#e9ebf4",
        "text":        "#20242f",
        "text_muted":  "#5b6272",
        "text_faint":  "#8b91a3",
        "selection_bg": ACCENT_DIVAR,
        "selection_fg": "#ffffff",
        "scrollbar":   "#eceef6",
        "scroll_handle": "#c3c8db",
        "scroll_handle_hover": "#aab0c9",
        "danger":      "#dc3545",
        "danger_hover": "#c82333",
        "success":     "#28a745",
        "success_hover": "#218838",
        "link":        "#3568d4",
        "shadow":      "#c9ccdb",
        "sidebar_bg":  "#e9ebf4",
        "nav_active_bg": "#fbeaea",
        "header_bg":   "#f3f4f9",
    },
}

_current_theme: str = THEME_DARK


# ---------------------------------------------------------------------------
# API عمومی
# ---------------------------------------------------------------------------
def colors(theme: str | None = None) -> Dict[str, str]:
    """توکن‌های رنگی تم فعلی (یا تم مشخص‌شده) را برمی‌گرداند."""
    return _THEMES[theme or _current_theme]


def current_theme() -> str:
    return _current_theme


def is_dark() -> bool:
    return _current_theme == THEME_DARK


def load_saved_theme() -> str:
    """تم ذخیره‌شدهٔ کاربر را می‌خواند (پیش‌فرض: تیره)."""
    global _current_theme
    try:
        settings = QSettings("DivarManager", "DivarManager")
        saved = settings.value(_SETTING_KEY, THEME_DARK)
        _current_theme = saved if saved in _THEMES else THEME_DARK
    except Exception:
        _current_theme = THEME_DARK
    return _current_theme


def _save_theme(theme: str) -> None:
    try:
        settings = QSettings("DivarManager", "DivarManager")
        settings.setValue(_SETTING_KEY, theme)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ساخت StyleSheet سراسری
# ---------------------------------------------------------------------------
def build_stylesheet(theme: str | None = None) -> str:
    """QSS سراسری و مدرن را برای تم داده‌شده می‌سازد."""
    c = colors(theme)

    return f"""
/* ============================================================
   Divar Manager - Global Theme ({theme or _current_theme})
   ============================================================ */

* {{
    font-family: 'Vazirmatn', 'Segoe UI', 'Tahoma', sans-serif;
}}

/* ---------- پنجره و ویجت‌های پایه ---------- */
QMainWindow, QDialog {{
    background-color: {c['window_bg']};
}}
QWidget {{
    background-color: {c['window_bg']};
    color: {c['text']};
    font-size: 13px;
}}

/* ---------- برچسب‌ها ---------- */
QLabel {{
    background: transparent;
    color: {c['text']};
}}
QLabel#titleLabel {{
    font-size: 22px;
    font-weight: 700;
    color: {c['text']};
}}
QLabel#subtitleLabel {{
    font-size: 13px;
    color: {c['text_muted']};
}}
QLabel#mutedLabel {{
    color: {c['text_muted']};
    font-size: 12px;
}}
QLabel#hintLabel {{
    color: {c['text_faint']};
    font-size: 11px;
    font-style: italic;
}}
QLabel#statusLabel {{
    color: {c['text_muted']};
    font-size: 11px;
}}

/* ---------- فیلدهای ورودی ---------- */
QLineEdit {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 10px;
    padding: 10px 14px;
    selection-background-color: {c['selection_bg']};
    selection-color: {c['selection_fg']};
}}
QLineEdit:focus {{
    border: 2px solid {ACCENT_DIVAR};
}}
QLineEdit:disabled {{
    color: {c['text_faint']};
    background-color: {c['surface']};
}}
QLineEdit#codeInput {{
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 10px;
    padding: 16px;
}}

/* ---------- دکمهٔ پیش‌فرض ---------- */
QPushButton {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 9px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {c['surface_hover']};
    border-color: {c['scroll_handle']};
}}
QPushButton:pressed {{
    background-color: {c['border']};
}}
QPushButton:disabled {{
    color: {c['text_faint']};
    background-color: {c['surface']};
    border-color: {c['border_soft']};
}}

/* ---------- دکمهٔ اصلی دیوار (قرمز برند) ---------- */
QPushButton#primaryDivar {{
    background-color: {ACCENT_DIVAR};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 12px 20px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#primaryDivar:hover {{
    background-color: {ACCENT_DIVAR_HOVER};
}}
QPushButton#primaryDivar:pressed {{
    background-color: {ACCENT_DIVAR_PRESSED};
}}
QPushButton#primaryDivar:disabled {{
    background-color: {c['border']};
    color: {c['text_faint']};
}}

/* ---------- دکمهٔ اصلی شیپور (آبی برند) ---------- */
QPushButton#primarySheypoor {{
    background-color: {ACCENT_SHEYPOOR};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 12px 20px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#primarySheypoor:hover {{
    background-color: {ACCENT_SHEYPOOR_HOVER};
}}
QPushButton#primarySheypoor:disabled {{
    background-color: {c['border']};
    color: {c['text_faint']};
}}

/* ---------- دکمهٔ خطر (قرمز) ---------- */
QPushButton#dangerBtn {{
    background-color: {c['danger']};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-weight: 700;
}}
QPushButton#dangerBtn:hover {{
    background-color: {c['danger_hover']};
}}
QPushButton#dangerBtn:disabled {{
    background-color: {c['border']};
    color: {c['text_faint']};
}}

/* ---------- دکمهٔ موفقیت (سبز) ---------- */
QPushButton#successBtn {{
    background-color: {c['success']};
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 700;
}}
QPushButton#successBtn:hover {{
    background-color: {c['success_hover']};
}}

/* ---------- دکمهٔ خاکستری/ثانویه ---------- */
QPushButton#ghostBtn {{
    background: transparent;
    color: {c['text_muted']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 8px 16px;
}}
QPushButton#ghostBtn:hover {{
    background-color: {c['surface_hover']};
    color: {c['text']};
}}

/* ---------- دکمهٔ متنی/لینک ---------- */
QPushButton#linkBtn {{
    background: transparent;
    color: {c['text_muted']};
    border: none;
    padding: 8px;
}}
QPushButton#linkBtn:hover {{
    color: {c['text']};
}}
QPushButton#dangerLinkBtn {{
    background: transparent;
    color: {c['danger']};
    border: none;
    padding: 10px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#dangerLinkBtn:hover {{
    color: {c['danger_hover']};
    text-decoration: underline;
}}

/* ---------- کارت / فریم ---------- */
QFrame#card {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 14px;
}}

/* ---------- جعبهٔ وضعیت ---------- */
QTextEdit#statusBox, QLabel#statusBox {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 14px;
    font-size: 12px;
}}
QLabel#statusBoxValid {{
    background-color: { '#1e3327' if (theme or _current_theme) == THEME_DARK else '#e7f6ec' };
    color: { '#8fe3b0' if (theme or _current_theme) == THEME_DARK else '#1d6b34' };
    border: 1px solid {c['success']};
    border-radius: 12px;
    padding: 14px;
    font-size: 12px;
}}
QLabel#statusBoxInvalid {{
    background-color: { '#3a2424' if (theme or _current_theme) == THEME_DARK else '#fdecec' };
    color: { '#f0a6a6' if (theme or _current_theme) == THEME_DARK else '#a03030' };
    border: 1px solid {c['danger']};
    border-radius: 12px;
    padding: 14px;
    font-size: 12px;
}}

/* ---------- GroupBox ---------- */
QGroupBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    margin-top: 16px;
    padding-top: 12px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top right;
    right: 14px;
    padding: 0 8px;
    color: {c['text']};
}}

/* ---------- لیست‌ها ---------- */
QListWidget {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 9px 12px;
    border-radius: 8px;
    margin: 2px 0;
    border: 1px solid transparent;
}}
QListWidget::item:hover {{
    background-color: {c['surface_hover']};
}}
QListWidget::item:selected {{
    background-color: {ACCENT_DIVAR};
    color: #ffffff;
}}

/* ---------- TextEdit عمومی ---------- */
QTextEdit, QPlainTextEdit {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 10px;
    selection-background-color: {c['selection_bg']};
    selection-color: {c['selection_fg']};
}}

/* ---------- لاگ (کنسول) ---------- */
QTextEdit#logConsole {{
    background-color: { '#14161f' if (theme or _current_theme) == THEME_DARK else '#1e1e1e' };
    color: #d4d4d4;
    border: 1px solid {c['border']};
    border-radius: 12px;
    padding: 12px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}}

/* ---------- تب‌ها ---------- */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    background: {c['surface']};
    border-radius: 12px;
    top: -1px;
}}
QTabBar::tab {{
    background: {c['window_bg']};
    color: {c['text_muted']};
    padding: 13px 28px;
    margin-left: 3px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    font-size: 13px;
    font-weight: 700;
}}
QTabBar::tab:selected {{
    background: {c['surface']};
    color: {c['text']};
    border-bottom: 3px solid {ACCENT_DIVAR};
}}
QTabBar::tab:hover:!selected {{
    background: {c['surface_alt']};
    color: {c['text']};
}}

/* ---------- نوار ابزار ---------- */
QToolBar {{
    background-color: {c['window_bg']};
    border: none;
    spacing: 8px;
    padding: 6px;
}}

/* ============================================================
   چیدمان جدید: سایدبار ناوبری + هدر
   ============================================================ */

/* ---------- سایدبار ---------- */
QFrame#sidebar {{
    background-color: {c['sidebar_bg']};
    border: none;
    border-left: 1px solid {c['border_soft']};
}}

/* برند / لوگوی برنامه */
QLabel#appTitle {{
    color: {c['text']};
    font-size: 19px;
    font-weight: 800;
}}
QLabel#appSubtitle {{
    color: {c['text_faint']};
    font-size: 11px;
}}
QLabel#brandAccent {{
    background-color: {ACCENT_DIVAR};
    border-radius: 6px;
    max-width: 40px;
    max-height: 5px;
}}
QLabel#navSectionLabel {{
    color: {c['text_faint']};
    font-size: 11px;
    font-weight: 700;
    padding: 0 8px;
}}

/* ---------- دکمهٔ جمع/باز کردن سایدبار ---------- */
QPushButton#sidebarToggle {{
    background: transparent;
    color: {c['text_muted']};
    border: none;
    border-radius: 9px;
    padding: 8px;
}}
QPushButton#sidebarToggle:hover {{
    background-color: {c['surface_hover']};
    color: {c['text']};
}}

/* ---------- دکمه‌های ناوبری ---------- */
QPushButton#navBtn {{
    background: transparent;
    color: {c['text_muted']};
    border: none;
    border-radius: 11px;
    padding: 13px 16px;
    text-align: right;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#navBtn:hover {{
    background-color: {c['surface_hover']};
    color: {c['text']};
}}
QPushButton#navBtnActive {{
    background-color: {c['nav_active_bg']};
    color: {c['text']};
    border: none;
    border-left: 3px solid {ACCENT_DIVAR};
    border-radius: 11px;
    padding: 13px 16px;
    text-align: right;
    font-size: 14px;
    font-weight: 800;
}}

/* ---------- هدر بخش ---------- */
QFrame#headerBar {{
    background-color: {c['header_bg']};
    border: none;
    border-bottom: 1px solid {c['border_soft']};
}}
QLabel#headerTitle {{
    color: {c['text']};
    font-size: 20px;
    font-weight: 800;
}}
QLabel#headerSubtitle {{
    color: {c['text_muted']};
    font-size: 12px;
}}

/* ---------- ناحیهٔ محتوا ---------- */
QWidget#contentArea {{
    background-color: {c['window_bg']};
}}

/* ---------- Splitter ---------- */
QSplitter::handle {{
    background-color: {c['border_soft']};
    height: 3px;
}}
QSplitter::handle:hover {{
    background-color: {ACCENT_DIVAR};
}}

/* ---------- ScrollBar ---------- */
QScrollBar:vertical {{
    background: {c['scrollbar']};
    width: 12px;
    margin: 0;
    border-radius: 6px;
}}
QScrollBar::handle:vertical {{
    background: {c['scroll_handle']};
    min-height: 30px;
    border-radius: 6px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['scroll_handle_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {c['scrollbar']};
    height: 12px;
    border-radius: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {c['scroll_handle']};
    min-width: 30px;
    border-radius: 6px;
    margin: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---------- ComboBox ---------- */
QComboBox {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 10px;
    padding: 8px 12px;
}}
QComboBox:focus {{ border: 2px solid {ACCENT_DIVAR}; }}
QComboBox QAbstractItemView {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    selection-background-color: {ACCENT_DIVAR};
    selection-color: #ffffff;
}}

/* ---------- CheckBox ---------- */
QCheckBox {{ spacing: 8px; color: {c['text']}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 2px solid {c['border']};
    border-radius: 5px;
    background: {c['surface_alt']};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT_DIVAR};
    border-color: {ACCENT_DIVAR};
}}

/* ---------- MessageBox ---------- */
QMessageBox {{
    background-color: {c['surface']};
}}
QMessageBox QLabel {{
    color: {c['text']};
    font-size: 13px;
}}

/* ---------- ToolTip ---------- */
QToolTip {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 6px;
}}
"""


# ---------------------------------------------------------------------------
# بارگذاری فونت‌ها
# ---------------------------------------------------------------------------
def load_app_fonts() -> str:
    """
    فونت‌های وزیرمتن همراه برنامه را ثبت می‌کند.

    Returns: نام فونت خانوادگی قابل استفاده (وزیرمتن یا fallback).
    """
    global _fonts_loaded
    if _fonts_loaded:
        return APP_FONT_FAMILY

    try:
        if _FONTS_DIR.exists():
            registered = False
            for ttf in sorted(_FONTS_DIR.glob("*.ttf")):
                font_id = QFontDatabase.addApplicationFont(str(ttf))
                if font_id != -1:
                    registered = True
            if registered:
                _fonts_loaded = True
                return APP_FONT_FAMILY
    except Exception:
        pass

    _fonts_loaded = True
    return _FALLBACK_FONT_FAMILY


# ---------------------------------------------------------------------------
# اعمال تم روی QApplication
# ---------------------------------------------------------------------------
def apply_theme(app: QApplication, theme: str | None = None) -> str:
    """
    تم را روی کل برنامه اعمال می‌کند.

    Returns: نام تم اعمال‌شده.
    """
    global _current_theme
    theme = theme or _current_theme
    if theme not in _THEMES:
        theme = THEME_DARK
    _current_theme = theme

    app.setStyleSheet(build_stylesheet(theme))

    # فونت سراسری مدرن (وزیرمتن در صورت Verfügbarkeit)
    family = load_app_fonts()
    font = QFont(family, 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    _save_theme(theme)
    return theme


def toggle_theme(app: QApplication) -> str:
    """بین تم تیره و روشن سوییچ می‌کند و تم جدید را برمی‌گرداند."""
    new_theme = THEME_LIGHT if _current_theme == THEME_DARK else THEME_DARK
    return apply_theme(app, new_theme)


def theme_icon_label() -> str:
    """متن/ایموجی دکمهٔ سوییچ تم بر اساس تم فعلی."""
    return "☀️ حالت روشن" if _current_theme == THEME_DARK else "🌙 حالت تیره"
