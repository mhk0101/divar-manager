# -*- coding: utf-8 -*-
"""
icons.py - تولید آیکون‌های SVG برداری و crisp برای رابط کاربری.

به‌جای ایموجی (که در پلتفرم‌های مختلف متفاوت رندر می‌شود)، از آیکون‌های
SVG مونوکروم استفاده می‌کنیم که با رنگ دلخواه (متناسب با تم) رندر می‌شوند.

اگر ماژول QtSvg در دسترس نبود، به‌صورت خودکار به ایموجی fallback می‌شود.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

try:
    from PySide6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:  # pragma: no cover
    QSvgRenderer = None
    _HAS_SVG = False


# ---------------------------------------------------------------------------
# قالب‌های SVG (مونوکروم، stroke-based، رنگ با __COLOR__ جایگذاری می‌شود)
# ---------------------------------------------------------------------------
_SVG = {
    # خانه - دیوار
    "home": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>
        <path d="M9.5 21v-6h5v6"/></svg>''',

    # بلندگو - شیپور
    "megaphone": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 11v2a1 1 0 0 0 1 1h2l3.5 4.5a1 1 0 0 0 1.8-.6V6.1a1 1 0 0 0-1.8-.6L6 10H4a1 1 0 0 0-1 1Z"/>
        <path d="M15 8.5a4 4 0 0 1 0 7"/><path d="M18 6a8 8 0 0 1 0 12"/></svg>''',

    # ربات/چرخ‌دنده - اتوماسیون
    "robot": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="4" y="8" width="16" height="11" rx="2.5"/>
        <path d="M12 8V4.5"/><circle cx="12" cy="3.5" r="1.3"/>
        <circle cx="9" cy="13" r="1.2"/><circle cx="15" cy="13" r="1.2"/>
        <path d="M9 16.5h6"/><path d="M2 12v3"/><path d="M22 12v3"/></svg>''',

    # لیست/سند - لاگ‌ها
    "logs": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="4" y="3" width="16" height="18" rx="2.5"/>
        <path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/></svg>''',

    # خورشید - تم روشن
    "sun": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4.2"/>
        <path d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"/></svg>''',

    # ماه - تم تیره
    "moon": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 13.2A8 8 0 1 1 10.8 4a6.5 6.5 0 0 0 9.2 9.2Z"/></svg>''',

    # ضربدر در دایره - بستن
    "close": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/></svg>''',

    # منو / همبرگر
    "menu": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 6h16M4 12h16M4 18h16"/></svg>''',

    # فلش دوتایی (جمع/باز کردن سایدبار)
    "collapse": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 6 4 12l5 6"/><path d="M15 6l5 6-5 6"/></svg>''',

    # ورود / لاگین
    "login": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
        <path d="M10 12H3"/><path d="m6 8-4 4 4 4"/></svg>''',

    # جستجو
    "search": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg>''',

    # ساعت - زمانبندی
    "clock": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>''',

    # راهنما
    "help": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
        stroke="__COLOR__" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/><path d="M9.4 9a3 3 0 1 1 5.2 2c-.9.8-1.6 1.3-1.9 2.4"/>
        <path d="M12 17h.01"/></svg>''',
}

# ایموجی fallback برای وقتی QtSvg موجود نیست
_EMOJI_FALLBACK = {
    "home": "🏠", "megaphone": "📢", "robot": "🤖", "logs": "📋",
    "sun": "☀️", "moon": "🌙", "close": "🔴", "menu": "☰",
    "collapse": "⇔", "login": "🔐", "search": "🔍", "clock": "⏰",
    "help": "📘",
}


def has_svg() -> bool:
    return _HAS_SVG


@lru_cache(maxsize=256)
def _render_pixmap(name: str, color: str, size: int) -> Optional[QPixmap]:
    """رندر یک آیکون SVG به QPixmap با رنگ و اندازهٔ مشخص."""
    if not _HAS_SVG or name not in _SVG:
        return None
    try:
        svg_bytes = _SVG[name].replace("__COLOR__", color).encode("utf-8")
        renderer = QSvgRenderer(svg_bytes)
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pm
    except Exception:
        return None


def icon(name: str, color: str = "#a2a8c4", size: int = 22) -> Optional[QIcon]:
    """
    ساخت QIcon برای آیکون داده‌شده با رنگ مشخص.

    اگر SVG در دسترس نبود، None برمی‌گرداند (تا از ایموجی استفاده شود).
    """
    pm = _render_pixmap(name, color, size)
    if pm is None:
        return None
    return QIcon(pm)


def emoji(name: str) -> str:
    """ایموجی متناظر (برای fallback یا استفادهٔ متنی)."""
    return _EMOJI_FALLBACK.get(name, "")
