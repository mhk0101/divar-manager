# -*- coding: utf-8 -*-
"""
تست‌های واقعی (نه Mock) روی SessionDB / SessionManager / core.retry.

این تست‌ها مستقیماً از کلاس‌های واقعی پروژه استفاده می‌کنند (نه شبیه‌سازی)
و با یک دیتابیس SQLite موقت (tmp_path) اجرا می‌شوند تا دیتابیس اصلی
دست‌نخورده بماند.

اجرا:
    pytest tests/test_session_scenarios.py -v
"""

from __future__ import annotations

import asyncio

import pytest

from core.session_db import SessionDB
from core.session_models import SessionRecord, SessionStatus, StorageState
from core.retry import (
    retry_call,
    with_timeout,
    OperationTimeoutError,
    NetworkError,
)


def _make_record(platform: str, phone: str) -> SessionRecord:
    """ساخت یک SessionRecord واقعی برای تست."""
    storage_state = StorageState.from_playwright({"cookies": [], "origins": []})
    return SessionRecord(
        id=None,
        platform=platform,
        phone=phone,
        storage_state=storage_state,
        access_token=None,
        refresh_token=None,
        status=SessionStatus.VALID,
        metadata={},
    )


# ---------------------------------------------------------------------
# سناریو ۱: افزودن شماره جدید بدون خراب کردن Session قدیمی
# ---------------------------------------------------------------------
def test_adding_new_phone_keeps_old_session(tmp_path):
    """
    بعد از ذخیره شماره دوم، هر دو رکورد باید جداگانه در دیتابیس باقی بمانند
    و list_all/get هر دو را به‌درستی برگرداند.
    """
    db_path = tmp_path / "test_sessions.db"
    db = SessionDB(db_path=db_path)

    rec1 = _make_record("sheypoor", "09120000001")
    rec2 = _make_record("sheypoor", "09120000002")

    saved1 = db.save(rec1)
    saved2 = db.save(rec2)

    assert saved1.id is not None
    assert saved2.id is not None
    assert saved1.id != saved2.id

    all_sessions = db.list_all("sheypoor")
    phones = {s.phone for s in all_sessions}
    assert phones == {"09120000001", "09120000002"}

    # هرکدام باید مستقل قابل بازیابی باشند
    fetched1 = db.get("sheypoor", "09120000001")
    fetched2 = db.get("sheypoor", "09120000002")
    assert fetched1 is not None and fetched1.phone == "09120000001"
    assert fetched2 is not None and fetched2.phone == "09120000002"

    # حذف یکی نباید دیگری را خراب کند
    db.delete_by_key("sheypoor", "09120000001")
    remaining = db.list_all("sheypoor")
    assert len(remaining) == 1
    assert remaining[0].phone == "09120000002"


def test_multiple_platforms_are_isolated(tmp_path):
    """Sessionهای دیوار و شیپور با شماره یکسان نباید با هم تداخل کنند."""
    db_path = tmp_path / "test_sessions2.db"
    db = SessionDB(db_path=db_path)

    rec_divar = _make_record("divar", "09121111111")
    rec_sheypoor = _make_record("sheypoor", "09121111111")

    db.save(rec_divar)
    db.save(rec_sheypoor)

    divar_sessions = db.list_all("divar")
    sheypoor_sessions = db.list_all("sheypoor")

    assert len(divar_sessions) == 1
    assert len(sheypoor_sessions) == 1
    assert divar_sessions[0].platform == "divar"
    assert sheypoor_sessions[0].platform == "sheypoor"


# ---------------------------------------------------------------------
# سناریو ۲: نشست نامعتبر -> تغییر وضعیت صحیح در DB
# ---------------------------------------------------------------------
def test_invalid_session_status_transition(tmp_path):
    """
    وقتی وضعیت یک Session به INVALID تغییر کند، این تغییر باید در DB
    ذخیره شود و بارگذاری بعدی همان وضعیت را نشان دهد (شبیه‌سازی سناریوی
    کوکی منقضی که validate() آن را INVALID تشخیص می‌دهد).
    """
    db_path = tmp_path / "test_sessions3.db"
    db = SessionDB(db_path=db_path)

    rec = _make_record("sheypoor", "09123334444")
    saved = db.save(rec)
    assert saved.status == SessionStatus.VALID

    ok = db.update_status(saved.id, SessionStatus.INVALID, reason="cookies expired")
    assert ok is True

    reloaded = db.get("sheypoor", "09123334444")
    assert reloaded.status == SessionStatus.INVALID

    history = db.get_history(saved.id)
    assert any("STATUS_CHANGE" in h["action"] for h in history)


# ---------------------------------------------------------------------
# سناریو ۳: قطع اینترنت / Timeout با retry_call واقعی
# ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_network_disconnect_raises_network_like_error():
    """
    شبیه‌سازی قطعی شبکه: تابعی که همیشه با خطای شبکه شکست می‌خورد،
    باید بعد از تمام تلاش‌ها (retry_call) همان خطا را دوباره raise کند.
    """
    call_count = {"n": 0}

    async def failing_call():
        call_count["n"] += 1
        raise Exception("net::ERR_INTERNET_DISCONNECTED")

    with pytest.raises(Exception) as exc_info:
        await retry_call(
            failing_call,
            attempts=3,
            base_delay=0.01,
            timeout=2,
            op_name="test navigation",
        )

    assert call_count["n"] == 3  # دقیقاً ۳ بار تلاش شد
    assert "internet" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_operation_timeout_raises_operation_timeout_error():
    """عملیات کندتر از حد مجاز باید OperationTimeoutError بدهد."""

    async def slow_op():
        await asyncio.sleep(5)
        return "done"

    with pytest.raises(OperationTimeoutError):
        await with_timeout(slow_op(), timeout=0.2, op_name="slow page load")


@pytest.mark.asyncio
async def test_retry_call_succeeds_after_transient_failure():
    """اگر تلاش دوم موفق شود، retry_call باید نتیجه را برگرداند (نه خطا)."""
    attempts_made = {"n": 0}

    async def flaky_call():
        attempts_made["n"] += 1
        if attempts_made["n"] < 2:
            raise Exception("net::ERR_CONNECTION_RESET")
        return "success"

    result = await retry_call(
        flaky_call, attempts=3, base_delay=0.01, timeout=2, op_name="flaky test",
    )
    assert result == "success"
    assert attempts_made["n"] == 2
