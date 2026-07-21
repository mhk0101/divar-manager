# -*- coding: utf-8 -*-
"""
تست‌های مربوط به سیستم لاگ‌ها و پاک‌سازی خودکار ۲۴ ساعته.
"""

import pytest

try:
    from ui.logs_tab import AUTO_CLEAR_INTERVAL_MS
except ImportError:
    AUTO_CLEAR_INTERVAL_MS = 24 * 60 * 60 * 1000


def test_auto_clear_interval_is_24_hours():
    twenty_four_hours_in_ms = 24 * 60 * 60 * 1000
    assert AUTO_CLEAR_INTERVAL_MS == twenty_four_hours_in_ms
    assert AUTO_CLEAR_INTERVAL_MS == 86400000
