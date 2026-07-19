"""
استایل‌های مشترک برای کل برنامه.
تم: مدرن، تمیز، خوانا
"""

# رنگ‌ها
PRIMARY = "#2563eb"        # آبی مدرن
PRIMARY_DARK = "#1e40af"
SUCCESS = "#10b981"        # سبز
DANGER = "#ef4444"         # قرمز
WARNING = "#f59e0b"        # زرد
INFO = "#3b82f6"           # آبی روشن
SECONDARY = "#64748b"      # خاکستری

BG_MAIN = "#f8fafc"        # پس‌زمینه اصلی
BG_CARD = "#ffffff"        # پس‌زمینه کارت
BG_HOVER = "#f1f5f9"       # hover
BORDER = "#e2e8f0"         # border
TEXT_PRIMARY = "#1e293b"   # متن اصلی
TEXT_SECONDARY = "#64748b" # متن کمکی
TEXT_MUTED = "#94a3b8"     # متن کمرنگ

# فونت‌ها
FONT_FAMILY = "'Segoe UI', 'Tahoma', sans-serif"
FONT_SIZE_SM = "12px"
FONT_SIZE_MD = "13px"
FONT_SIZE_LG = "15px"
FONT_SIZE_XL = "18px"
FONT_SIZE_TITLE = "24px"

# فاصله‌ها
SPACING_XS = "4px"
SPACING_SM = "8px"
SPACING_MD = "12px"
SPACING_LG = "16px"
SPACING_XL = "24px"

# Border Radius
RADIUS_SM = "6px"
RADIUS_MD = "8px"
RADIUS_LG = "12px"

# استایل اصلی پنجره
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background-color: {BG_MAIN};
}}
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_MD};
    color: {TEXT_PRIMARY};
}}
QLabel {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_MD};
}}
QLineEdit {{
    padding: 10px 12px;
    border: 2px solid {BORDER};
    border-radius: {RADIUS_MD};
    background-color: {BG_CARD};
    font-size: {FONT_SIZE_MD};
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus {{
    border-color: {PRIMARY};
}}
QLineEdit:disabled {{
    background-color: {BG_HOVER};
    color: {TEXT_MUTED};
}}
QTextEdit {{
    padding: 10px;
    border: 2px solid {BORDER};
    border-radius: {RADIUS_MD};
    background-color: {BG_CARD};
    font-size: {FONT_SIZE_MD};
    color: {TEXT_PRIMARY};
}}
QGroupBox {{
    font-weight: bold;
    font-size: {FONT_SIZE_LG};
    color: {TEXT_PRIMARY};
    border: 2px solid {BORDER};
    border-radius: {RADIUS_LG};
    margin-top: {SPACING_MD};
    padding-top: {SPACING_LG};
    background-color: {BG_CARD};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {TEXT_PRIMARY};
}}
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {BG_HOVER};
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SECONDARY};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {PRIMARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""

# استایل لیست
def list_style(primary_color=PRIMARY):
    return f"""
    QListWidget {{
        border: 2px solid {BORDER};
        border-radius: {RADIUS_MD};
        background: {BG_CARD};
        font-size: {FONT_SIZE_MD};
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 10px 12px;
        margin: 2px 0;
        border-radius: {RADIUS_SM};
        border: 1px solid transparent;
    }}
    QListWidget::item:selected {{
        background-color: {primary_color};
        color: white;
        border: 1px solid {primary_color};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {BG_HOVER};
        border: 1px solid {BORDER};
    }}
    """

# استایل دکمه
def button_style(bg_color, hover_color=None, text_color="white", radius=RADIUS_MD, padding="10px 16px"):
    if hover_color is None:
        hover_color = bg_color
    return f"""
    QPushButton {{
        background-color: {bg_color};
        color: {text_color};
        border: none;
        border-radius: {radius};
        padding: {padding};
        font-weight: 600;
        font-size: {FONT_SIZE_MD};
    }}
    QPushButton:hover {{
        background-color: {hover_color};
    }}
    QPushButton:pressed {{
        background-color: {bg_color};
    }}
    QPushButton:disabled {{
        background-color: {BORDER};
        color: {TEXT_MUTED};
    }}
    """

# دکمه‌های پیش‌فرض
BTN_PRIMARY = button_style(PRIMARY, PRIMARY_DARK)
BTN_SUCCESS = button_style(SUCCESS, "#059669")
BTN_DANGER = button_style(DANGER, "#dc2626")
BTN_WARNING = button_style(WARNING, "#d97706")
BTN_SECONDARY = button_style(SECONDARY, "#475569")
BTN_LARGE = button_style(PRIMARY, PRIMARY_DARK, padding="14px 24px")

# استایل تب‌ها
TABS_STYLE = f"""
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG_CARD};
    border-radius: {RADIUS_MD};
    top: -1px;
}}
QTabBar::tab {{
    background: {BG_HOVER};
    color: {TEXT_SECONDARY};
    padding: 14px 28px;
    margin-right: 4px;
    border-top-left-radius: {RADIUS_MD};
    border-top-right-radius: {RADIUS_MD};
    font-size: {FONT_SIZE_LG};
    font-weight: 600;
    border: 1px solid transparent;
    border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{
    background: {BG_CARD};
    color: {PRIMARY};
    border: 1px solid {BORDER};
    border-bottom: 3px solid {PRIMARY};
}}
QTabBar::tab:hover:!selected {{
    background: {BG_MAIN};
    color: {TEXT_PRIMARY};
}}
"""

# استایل Toolbar
TOOLBAR_STYLE = f"""
QToolBar {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD};
    padding: 6px;
    spacing: 8px;
}}
"""
