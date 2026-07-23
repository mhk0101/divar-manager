"""
ScheduleTab — تب نمایش تمام زمانبندی‌های فعال.

یک جدول کامل از همه زمانبندی‌ها را نشان می‌دهد:
- پلتفرم، شماره تلفن، شهرها، دسته‌بندی، فاصله تکرار، زمان اجرای بعدی، وضعیت
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ScheduleTab(QWidget):
    """تب نمایش زمانبندی‌های فعال."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._schedules: List[Dict] = []
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_display)
        self._refresh_timer.start()

        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("⏰ مدیریت زمانبندی‌ها")
        title.setObjectName("titleLabel")
        tf = QFont()
        tf.setPointSize(20)
        tf.setBold(True)
        title.setFont(tf)
        layout.addWidget(title)

        hint = QLabel("تمام زمانبندی‌های فعال برای شماره‌های مختلف در اینجا نمایش داده می‌شوند.")
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        group = QGroupBox("📋 زمانبندی‌های فعال")
        gl = QVBoxLayout(group)
        gl.setContentsMargins(14, 14, 14, 14)
        gl.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "پلتفرم", "شماره تلفن", "شهر(ها)", "دسته‌بندی",
            "تکرار هر", "اجرای بعدی", "وضعیت"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(300)
        gl.addWidget(self.table)

        bar = QHBoxLayout()
        self.count_lbl = QLabel("تعداد زمانبندی‌های فعال: ۰")
        self.count_lbl.setObjectName("subtitleLabel")
        bar.addWidget(self.count_lbl)
        bar.addStretch()
        gl.addLayout(bar)

        layout.addWidget(group)
        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def update_schedules(self, schedules: List[Dict]):
        """بروزرسانی لیست زمانبندی‌ها از تب اتوماسیون."""
        self._schedules = schedules
        self._refresh_display()

    def _refresh_display(self):
        now = datetime.now()
        self.table.setRowCount(0)
        active_count = 0

        for s in self._schedules:
            if not s.get("running"):
                continue
            active_count += 1
            row = self.table.rowCount()
            self.table.insertRow(row)

            plat = "🔴 دیوار" if s.get("platform") == "divar" else "🔵 شیپور"
            phone = s.get("phone", "")
            cities = s.get("cities", "همه شهرها")
            category = s.get("category", "همه دسته‌ها")
            interval = s.get("interval_minutes", 0)
            remaining = s.get("remaining_seconds", 0)

            next_time = now.timestamp() + remaining
            next_dt = datetime.fromtimestamp(next_time)
            next_str = next_dt.strftime("%H:%M:%S")

            status = s.get("status", "")
            in_progress = s.get("in_progress", False)

            items = [
                QTableWidgetItem(plat),
                QTableWidgetItem(phone),
                QTableWidgetItem(cities),
                QTableWidgetItem(category),
                QTableWidgetItem(f"هر {interval}دقیقه"),
                QTableWidgetItem(f"{next_str}  ({remaining // 60}دقیقه)"),
                QTableWidgetItem("🟢 در حال اجرا" if in_progress else "⏳ در انتظار"),
            ]

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

        self.count_lbl.setText(f"تعداد زمانبندی‌های فعال: {active_count}")

    def restyle(self):
        try:
            self.table.style().unpolish(self.table)
            self.table.style().polish(self.table)
        except Exception:
            pass
