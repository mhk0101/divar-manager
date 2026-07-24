"""
ScheduleTab — تب نمایش و کنترل تمام زمانبندی‌ها.

امکانات:
- نمایش چندین زمانبندی همزمان برای شماره‌ها و پلتفرم‌های مختلف
- نمایش چرخه اجرای زمانبندی‌ها
- توقف/ادامه، لغو و حذف هر زمانبندی به‌صورت جداگانه
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from PySide6.QtCore import Qt, QTimer, Signal
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
    """تب نمایش و مدیریت زمانبندی‌ها."""

    schedule_action = Signal(str, str)  # schedule_id, action: stop/resume/cancel/delete

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

        hint = QLabel(
            "تمام زمانبندی‌های ثبت‌شده برای دیوار و شیپور در اینجا نمایش داده می‌شوند. "
            "هر زمانبندی در هر چرخه فقط یک‌بار اجرا می‌شود؛ وقتی همه زمانبندی‌ها تمام شدند، چرخه بعدی از ابتدا شروع می‌شود."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        group = QGroupBox("📋 زمانبندی‌ها")
        gl = QVBoxLayout(group)
        gl.setContentsMargins(14, 14, 14, 14)
        gl.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "شناسه", "پلتفرم", "شماره تلفن", "شهر(ها)", "دسته‌بندی",
            "اجرا بعد از", "چرخه", "اجرای بعدی", "وضعیت", "عملیات"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(340)
        gl.addWidget(self.table)

        bar = QHBoxLayout()
        self.count_lbl = QLabel("تعداد زمانبندی‌ها: ۰")
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
        self._schedules = schedules or []
        self._refresh_display()

    def _status_text(self, s: Dict) -> str:
        status = s.get("status")
        if s.get("status_text"):
            return s.get("status_text")
        if status == "running" or s.get("in_progress"):
            return "🟢 در حال اجرا"
        if status == "waiting":
            return "⏳ در انتظار"
        if status == "paused":
            return "⏸️ متوقف‌شده"
        if status == "completed":
            return "✅ انجام‌شده در این چرخه"
        if status == "cancelled":
            return "🚫 لغوشده"
        if status == "error":
            return "🔴 خطا"
        return str(status or "—")

    def _next_run_text(self, s: Dict, now: datetime) -> str:
        status = s.get("status")
        remaining = max(0, int(s.get("remaining_seconds", 0) or 0))
        next_run = s.get("next_run")
        if status == "paused":
            return f"متوقف ({remaining // 60}دقیقه باقی‌مانده)"
        if status in ("completed", "cancelled", "error"):
            return "—"
        if isinstance(next_run, datetime):
            next_str = next_run.strftime("%H:%M:%S")
        else:
            next_str = datetime.fromtimestamp(now.timestamp() + remaining).strftime("%H:%M:%S")
        return f"{next_str}  ({remaining // 60}دقیقه {remaining % 60}ثانیه)"

    def _make_actions_widget(self, s: Dict) -> QWidget:
        sid = s.get("id", "")
        status = s.get("status")

        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        if status == "paused":
            btn_stop_resume = QPushButton("▶️ ادامه")
            btn_stop_resume.setObjectName("successBtn")
            btn_stop_resume.clicked.connect(lambda _=False, x=sid: self.schedule_action.emit(x, "resume"))
        else:
            btn_stop_resume = QPushButton("⏸️ توقف")
            btn_stop_resume.setObjectName("ghostBtn")
            btn_stop_resume.clicked.connect(lambda _=False, x=sid: self.schedule_action.emit(x, "stop"))
            btn_stop_resume.setEnabled(status in ("waiting", "running"))
        btn_stop_resume.setMinimumHeight(30)
        btn_stop_resume.setCursor(Qt.PointingHandCursor)
        row.addWidget(btn_stop_resume)

        btn_cancel = QPushButton("🚫 لغو")
        btn_cancel.setObjectName("dangerBtn")
        btn_cancel.setMinimumHeight(30)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(lambda _=False, x=sid: self.schedule_action.emit(x, "cancel"))
        btn_cancel.setEnabled(status not in ("cancelled",))
        row.addWidget(btn_cancel)

        btn_delete = QPushButton("🗑️ حذف")
        btn_delete.setObjectName("dangerBtn")
        btn_delete.setMinimumHeight(30)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(lambda _=False, x=sid: self.schedule_action.emit(x, "delete"))
        row.addWidget(btn_delete)

        return box

    def _refresh_display(self):
        now = datetime.now()
        self.table.setRowCount(0)

        for s in self._schedules:
            row = self.table.rowCount()
            self.table.insertRow(row)

            plat = "🔴 دیوار" if s.get("platform") == "divar" else "🔵 شیپور"
            phone = s.get("phone", "")
            cities = s.get("cities", "همه شهرها")
            category = s.get("category", "همه دسته‌ها")
            interval = int(s.get("interval_minutes", 0) or 0)
            cycle = int(s.get("cycle", 1) or 1)
            sid = str(s.get("id", ""))

            items = [
                QTableWidgetItem(sid[:8] if sid else "—"),
                QTableWidgetItem(plat),
                QTableWidgetItem(phone),
                QTableWidgetItem(cities),
                QTableWidgetItem(category),
                QTableWidgetItem(f"بعد از {interval}دقیقه"),
                QTableWidgetItem(str(cycle)),
                QTableWidgetItem(self._next_run_text(s, now)),
                QTableWidgetItem(self._status_text(s)),
            ]

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

            self.table.setCellWidget(row, 9, self._make_actions_widget(s))

        active_count = sum(1 for s in self._schedules if s.get("status") not in ("cancelled",))
        self.count_lbl.setText(f"تعداد زمانبندی‌ها: {len(self._schedules)} | فعال/قابل مدیریت: {active_count}")

    def restyle(self):
        try:
            self.table.style().unpolish(self.table)
            self.table.style().polish(self.table)
        except Exception:
            pass
