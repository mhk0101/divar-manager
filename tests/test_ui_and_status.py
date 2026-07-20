# -*- coding: utf-8 -*-
"""
تست‌های مربوط به فرمت‌دهی وضعیت و کوکی‌ها.
"""

import pytest

from core.session_models import SessionRecord, SessionStatus, StorageState


def format_status_persian_test(status_str: str) -> str:
    s = str(status_str).lower()
    if s == "valid":
        return "🟢 معتبر"
    elif s == "invalid":
        return "🔴 نامعتبر"
    elif s == "expired":
        return "🟠 منقضی شده"
    elif s == "needs_refresh":
        return "🟡 نیاز به بروزرسانی"
    return "⚪ بررسی‌نشده / نامشخص"


def test_format_status_persian():
    assert format_status_persian_test("valid") == "🟢 معتبر"
    assert format_status_persian_test("invalid") == "🔴 نامعتبر"
    assert format_status_persian_test("expired") == "🟠 منقضی شده"
    assert format_status_persian_test("needs_refresh") == "🟡 نیاز به بروزرسانی"
    assert format_status_persian_test("unknown") == "⚪ بررسی‌نشده / نامشخص"
    assert format_status_persian_test("anything_else") == "⚪ بررسی‌نشده / نامشخص"


def test_cookie_counting():
    cookies = [
        {"name": "token", "value": "xyz", "domain": "divar.ir", "path": "/"},
        {"name": "session", "value": "123", "domain": "divar.ir", "path": "/"},
    ]
    state = StorageState.from_playwright({"cookies": cookies, "origins": []})
    record = SessionRecord(
        id=1,
        platform="divar",
        phone="09123456789",
        storage_state=state,
        access_token=None,
        refresh_token=None,
        status=SessionStatus.VALID,
        metadata={},
    )
    assert len(record.storage_state.cookies) == 2
