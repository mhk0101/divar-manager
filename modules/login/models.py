"""
مدل‌های داده‌ی ماژول Login.

از Pydantic استفاده می‌کنیم تا:
- اعتبارسنجی ورودی‌ها (phone, code) خودکار باشد
- ساختار داده‌ها مستند و type-safe باقی بماند
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator


class LoginState(str, Enum):
    """وضعیت‌های ممکن در طول فرآیند Login."""

    IDLE = "idle"                         # هنوز شروع نشده
    OPENING_LOGIN_PAGE = "opening_login_page"
    CLICKING_ENTRY_BUTTON = "clicking_entry_button"
    ENTERING_PHONE = "entering_phone"
    WAITING_FOR_CODE = "waiting_for_code"      # شماره ارسال شد، منتظر کد
    ENTERING_CODE = "entering_code"
    SUBMITTING_CODE = "submitting_code"
    SUCCESS = "success"
    FAILED = "failed"


class LoginResult:
    """
    خروجی نهایی فرآیند Login.

    از BaseModel pydantic استفاده نمی‌کنیم چون نیاز به فیلد داخلی
    _diagnostic داریم که نمی‌خواهیم serialized شود.
    """

    __slots__ = ("success", "state", "phone", "session_path", "error", "_diagnostic")

    def __init__(
        self,
        success: bool,
        state: LoginState,
        phone: Optional[str] = None,
        session_path: Optional[str] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.state = state
        self.phone = phone
        self.session_path = session_path
        self.error = error
        self._diagnostic = None  # DiagnosticReport (internal)

    def __str__(self) -> str:
        if self.success:
            return (
                f"[OK] Login successful for {self.phone}. "
                f"Session saved at: {self.session_path}"
            )
        return f"[FAIL] Login failed at state={self.state.value}: {self.error}"

    @property
    def diagnostic(self):
        return self._diagnostic


# ---------------------------------------------------------------------------
# اعتبارسنجی ورودی‌ها
# ---------------------------------------------------------------------------
_IRANIAN_MOBILE_RE = re.compile(r"^(?:\+98|0)?9\d{9}$")


def normalize_phone(raw: str) -> str:
    """
    تبدیل ورودی کاربر به فرمت استاندارد ۰۹xxxxxxxxx.

    مثال‌ها:
        +989121234567  ->  09121234567
        9121234567     ->  09121234567
        ۰۹۱۲۱۲۳۴۵۶۷   ->  09121234567  (با کمک translate)
    """
    # تبدیل ارقام فارسی/عربی به انگلیسی
    fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = raw.translate(fa_to_en).strip()
    cleaned = re.sub(r"\s+", "", cleaned)

    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    elif cleaned.startswith("9") and len(cleaned) == 10:
        cleaned = "0" + cleaned

    if not _IRANIAN_MOBILE_RE.match(cleaned) or not cleaned.startswith("09"):
        raise ValueError(f"Invalid Iranian mobile number: {raw!r}")
    return cleaned


def normalize_code(raw: str) -> str:
    """
    تبدیل ورودی کد تأیید به رشته‌ی ۶ رقمی انگلیسی.
    """
    fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = raw.translate(fa_to_en).strip()
    cleaned = re.sub(r"\s+", "", cleaned)

    if not re.fullmatch(r"\d{6}", cleaned):
        raise ValueError(f"Verification code must be exactly 6 digits, got: {raw!r}")
    return cleaned


class PhoneInput(BaseModel):
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("phone must be a string")
        return normalize_phone(v)


class CodeInput(BaseModel):
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("code must be a string")
        return normalize_code(v)
