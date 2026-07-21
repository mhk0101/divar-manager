"""
LogsTab - تب نمایش لاگ‌های سراسری پروژه.

ویژگی‌ها:
- قابلیت پاک‌سازی خودکار هر ۲۴ ساعت
- دکمه فعال/غیرفعال‌سازی پاک‌سازی ۲۴ ساعته لاگ‌ها با ذخیره تنظیمات در QSettings
- امکان پاک‌سازی دستی متون کنسول لاگ
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Slot, QTimer, QSettings
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

AUTO_CLEAR_INTERVAL_MS = 24 * 60 * 60 * 1000  # ۲۴ ساعت بر حسب میلی‌ثانیه


class LogsTab(QWidget):
    """تب لاگ‌ها با قابلیت پاک‌سازی خودکار ۲۴ ساعته و تنظیم دکمه فعال/غیرفعال."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_count = 0

        # تایمر پاک‌سازی ۲۴ ساعته
        self._auto_clear_timer = QTimer(self)
        self._auto_clear_timer.setInterval(AUTO_CLEAR_INTERVAL_MS)
        self._auto_clear_timer.timeout.connect(self._on_auto_clear_timeout)

        self._setup_ui()
        self._load_auto_clear_setting()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        # هدر و کنترل‌ها
        header = QHBoxLayout()
        title = QLabel("📋 لاگ‌های سیستم")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)

        header.addStretch()

        # دکمه فعال/غیرفعال‌سازی پاک‌سازی خودکار ۲۴ ساعته
        self.toggle_auto_clear_btn = QPushButton()
        self.toggle_auto_clear_btn.setMinimumHeight(40)
        self.toggle_auto_clear_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_auto_clear_btn.clicked.connect(self._toggle_auto_clear)
        header.addWidget(self.toggle_auto_clear_btn)

        # دکمه پاک‌سازی دستی
        self.clear_btn = QPushButton("🗑️ پاک کردن دستی")
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(self.clear_btn)

        layout.addLayout(header)

        # توضیح
        description = QLabel("تمام رویدادهای سیستم، وضعیت کوکی‌ها و خطاهای برنامه در این بخش ثبت می‌گردند.")
        description.setObjectName("hintLabel")
        layout.addWidget(description)

        # Text area برای لاگ‌ها
        self.log_text = QTextEdit()
        self.log_text.setObjectName("logConsole")
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Footer
        footer = QHBoxLayout()
        self.count_label = QLabel("تعداد لاگ‌ها: 0")
        self.count_label.setObjectName("mutedLabel")
        footer.addWidget(self.count_label)
        footer.addStretch()

        self.time_label = QLabel("")
        self.time_label.setObjectName("mutedLabel")
        footer.addWidget(self.time_label)

        layout.addLayout(footer)
        self._update_time()

    def _load_auto_clear_setting(self):
        """بارگذاری تنظیم فعال/غیرفعال از QSettings (پیش‌فرض: فعال)."""
        try:
            settings = QSettings("DivarManager", "DivarManager")
            enabled = bool(settings.value("logs/auto_clear_24h", True, type=bool))
        except Exception:
            enabled = True

        self._set_auto_clear_state(enabled)

    def _save_auto_clear_setting(self, enabled: bool):
        try:
            settings = QSettings("DivarManager", "DivarManager")
            settings.setValue("logs/auto_clear_24h", enabled)
        except Exception:
            pass

    def _set_auto_clear_state(self, enabled: bool):
        self._auto_clear_enabled = enabled
        if enabled:
            self.toggle_auto_clear_btn.setText("🟢 پاک‌سازی خودکار ۲۴ ساعته: فعال")
            self.toggle_auto_clear_btn.setObjectName("successBtn")
            self.toggle_auto_clear_btn.setToolTip("کلیک کنید تا پاک‌سازی خودکار ۲۴ ساعته غیرفعال شود")
            if not self._auto_clear_timer.isActive():
                self._auto_clear_timer.start()
        else:
            self.toggle_auto_clear_btn.setText("🔴 پاک‌سازی خودکار ۲۴ ساعته: غیرفعال")
            self.toggle_auto_clear_btn.setObjectName("ghostBtn")
            self.toggle_auto_clear_btn.setToolTip("کلیک کنید تا پاک‌سازی خودکار ۲۴ ساعته فعال شود")
            self._auto_clear_timer.stop()

        self.toggle_auto_clear_btn.style().unpolish(self.toggle_auto_clear_btn)
        self.toggle_auto_clear_btn.style().polish(self.toggle_auto_clear_btn)

    def _toggle_auto_clear(self):
        new_state = not self._auto_clear_enabled
        self._set_auto_clear_state(new_state)
        self._save_auto_clear_setting(new_state)
        status_msg = "فعال 🟢" if new_state else "غیرفعال 🔴"
        self.append_log("INFO", f"⚙️ سیستم پاک‌سازی خودکار ۲۴ ساعته لاگ‌ها تغییر کرد: {status_msg}")

    def _on_auto_clear_timeout(self):
        """اجرای پاک‌سازی خودکار در موعد ۲۴ ساعت."""
        self.log_text.clear()
        self._log_count = 0
        self.count_label.setText("تعداد لاگ‌ها: 0")
        self.append_log("INFO", "🧹 پاک‌سازی خودکار لاگ‌ها پس از ۲۴ ساعت انجام گردید.")

    def restyle(self):
        """با تغییر تم، استایل‌ها از QSS سراسری بازخوانی می‌شوند."""
        try:
            self.log_text.style().unpolish(self.log_text)
            self.log_text.style().polish(self.log_text)
            self.toggle_auto_clear_btn.style().unpolish(self.toggle_auto_clear_btn)
            self.toggle_auto_clear_btn.style().polish(self.toggle_auto_clear_btn)
        except Exception:
            pass

    def _update_time(self):
        now = datetime.now()
        time_str = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        self.time_label.setText(f"آخرین به‌روزرسانی: {time_str}")

    def _clear_logs(self):
        self.log_text.clear()
        self._log_count = 0
        self.count_label.setText("تعداد لاگ‌ها: 0")

    @Slot(str, str)
    def append_log(self, level: str, message: str):
        """افزودن یک لاگ جدید."""
        color_map = {
            "DEBUG": "#888888",
            "INFO": "#4ec9b0",
            "WARNING": "#dcdcaa",
            "ERROR": "#f48771",
            "CRITICAL": "#ff0000",
        }
        color = color_map.get(level, "#d4d4d4")

        html = f'<span style="color: {color};">[{level}]</span> {message}'
        self.log_text.append(html)

        self._log_count += 1
        self.count_label.setText(f"تعداد لاگ‌ها: {self._log_count}")
        self._update_time()

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
