"""
LoggerManager - مدیریت لاگ‌های سراسری پروژه.

تمام لاگ‌ها هم به فایل و هم به UI ارسال می‌شوند.
UI می‌تواند با ثبت یک handler، لاگ‌ها را در تب لاگ نمایش دهد.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from config.settings import PROJECT_ROOT


LOGS_DIR: Path = PROJECT_ROOT / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class UILogHandler(logging.Handler):
    """Handler که لاگ‌ها را از طریق یک callback به UI ارسال می‌کند."""

    def __init__(self, callback: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self._callback = callback
        self.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S"))

    def set_callback(self, callback: Callable[[str, str], None]):
        self._callback = callback

    def emit(self, record: logging.LogRecord):
        if self._callback is None:
            return
        try:
            msg = self.format(record)
            self._callback(record.levelname, msg)
        except Exception:
            self.handleError(record)


# Handler سراسری UI
_ui_handler = UILogHandler()


def setup_logging(level: int = logging.INFO) -> None:
    """پیکربندی logging سراسری پروژه."""
    root = logging.getLogger()
    if root.handlers:
        return  # فقط یک بار

    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(console)

    # File handler
    log_file = LOGS_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
    root.addHandler(file_handler)

    # UI handler
    root.addHandler(_ui_handler)


def register_ui_callback(callback: Callable[[str, str], None]) -> None:
    """ثبت callback برای ارسال لاگ‌ها به UI."""
    _ui_handler.set_callback(callback)
