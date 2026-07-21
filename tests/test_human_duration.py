# -*- coding: utf-8 -*-
"""
تست‌های تبدیل زمان باقی‌مانده توکن به فرمت خوانای انسانی (دقیقه، ساعت، روز، هفته).
"""

from core.token_refresher import format_human_readable_duration


def test_format_human_readable_duration():
    assert format_human_readable_duration(45) == "45 ثانیه"
    assert format_human_readable_duration(180) == "3 دقیقه"

    dur = format_human_readable_duration(10639)
    assert "2 ساعت" in dur and "57 دقیقه" in dur

    dur_days = format_human_readable_duration(259200)
    assert "3 روز" in dur_days

    dur_weeks = format_human_readable_duration(1209600)
    assert "2 هفته" in dur_weeks
