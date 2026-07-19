"""
LogsTab - تب نمایش لاگ‌های سراسری پروژه.

تمام لاگ‌های ماژول‌های دیوار و شیپور اینجا نمایش داده می‌شوند.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LogsTab(QWidget):
    """تب لاگ‌ها."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        # هدر
        header = QHBoxLayout()
        title = QLabel("📋 لاگ‌های سیستم")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        header.addWidget(title)
        header.addStretch()

        self.clear_btn = QPushButton("🗑️ پاک کردن")
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(self.clear_btn)

        layout.addLayout(header)

        # توضیح
        description = QLabel("تمام رویدادهای سیستم، خطاها و وضعیت‌ها اینجا نمایش داده می‌شوند")
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

        self._log_count = 0
        self._update_time()

    def restyle(self):
        """✨ با تغییر تم، استایل‌ها از QSS سراسری بازخوانی می‌شوند."""
        # objectNameها ثابت‌اند و QSS سراسری خودکار اعمال می‌شود؛
        # این متد فقط برای سازگاری با رابط مشترک تب‌ها وجود دارد.
        self.style().unpolish(self.log_text)
        self.style().polish(self.log_text)

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

        # Scroll به انتها
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)
