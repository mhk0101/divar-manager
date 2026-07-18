"""
اسکریپت خودکار تعمیر کامل + اجرا
این اسکریپت تمام مشکلات ایمپورت را برطرف می‌کند و برنامه را اجرا می‌کند.
"""

import os
import shutil
import subprocess
from datetime import datetime
from urllib.request import urlopen
from urllib.error import URLError

# ====================== تنظیمات ======================
PROJECT_ROOT = r"D:\Divar_Gui_New\Version_new_pyside"
BACKUP_DIR = os.path.join(PROJECT_ROOT, "backups")

# فایل‌های مشکل‌دار
SHEYPOOR_MODELS = os.path.join(PROJECT_ROOT, "modules", "sheypoor", "login", "models.py")
SHEYPOOR_INIT = os.path.join(PROJECT_ROOT, "modules", "sheypoor", "login", "__init__.py")
DIVAR_LOGIN_MANAGER = os.path.join(PROJECT_ROOT, "modules", "login", "login_manager.py")

CLEAN_URLS = {
    "divar_login": "https://raw.githubusercontent.com/mhk0101/divar-manager/main/modules/login/login_manager.py",
}

MAIN_SCRIPT = os.path.join(PROJECT_ROOT, "ui", "main.py")
PYTHON_EXE = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
# =====================================================


def backup_file(path):
    if not os.path.exists(path):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = os.path.basename(path)
    backup_path = os.path.join(BACKUP_DIR, f"{name}.bak_{ts}")
    shutil.copy2(path, backup_path)
    print(f"[OK] بکاپ: {backup_path}")
    return backup_path


def download(url):
    try:
        with urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        print(f"[ERROR] دانلود ناموفق: {e}")
        return None


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] نوشته شد: {path}")


def fix_sheypoor_models():
    """تعمیر models.py شیپور (اضافه کردن LoginRequest)"""
    print("\n=== تعمیر models.py شیپور ===")
    backup_file(SHEYPOOR_MODELS)

    content = '''"""
مدل‌های داده‌ی ماژول Login شیپور.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator
import re


class LoginState(str, Enum):
    IDLE = "idle"
    OPENING_LOGIN_PAGE = "opening_login_page"
    ENTERING_PHONE = "entering_phone"
    WAITING_FOR_CODE = "waiting_for_code"
    ENTERING_CODE = "entering_code"
    SUBMITTING_CODE = "submitting_code"
    SUCCESS = "success"
    FAILED = "failed"


class LoginRequest(BaseModel):
    phone: str
    code: Optional[str] = None


class LoginResult:
    __slots__ = ("success", "state", "phone", "session_path", "error", "_diagnostic")

    def __init__(self, success: bool, state: LoginState, phone: Optional[str] = None,
                 session_path: Optional[str] = None, error: Optional[str] = None):
        self.success = success
        self.state = state
        self.phone = phone
        self.session_path = session_path
        self.error = error
        self._diagnostic = None

    def __str__(self):
        if self.success:
            return f"[OK] Login successful for {self.phone}. Session saved at: {self.session_path}"
        return f"[FAIL] Login failed at state={self.state.value}: {self.error}"

    @property
    def diagnostic(self):
        return self._diagnostic


_IRANIAN_MOBILE_RE = re.compile(r"^(?:\\+98|0)?9\\d{9}$")


def normalize_phone(raw: str) -> str:
    fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    cleaned = raw.translate(fa_to_en).strip()
    cleaned = re.sub(r"\\s+", "", cleaned)
    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    elif cleaned.startswith("9") and len(cleaned) == 10:
        cleaned = "0" + cleaned
    if not _IRANIAN_MOBILE_RE.match(cleaned) or not cleaned.startswith("09"):
        raise ValueError(f"Invalid Iranian mobile number: {raw!r}")
    return cleaned


class PhoneInput(BaseModel):
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("phone must be a string")
        return normalize_phone(v)


class OTPInput(BaseModel):
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("OTP must be a string")
        fa_to_en = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        cleaned = v.translate(fa_to_en).strip()
        if not re.fullmatch(r"\\d{4}", cleaned):
            raise ValueError(f"Verification code must be exactly 4 digits, got: {v!r}")
        return cleaned
'''
    write_file(SHEYPOOR_MODELS, content)
    print("[OK] LoginRequest اضافه شد")


def fix_divar_login_manager():
    """جایگزینی فایل login_manager.py دیوار"""
    print("\n=== تعمیر login_manager.py دیوار ===")
    backup_file(DIVAR_LOGIN_MANAGER)

    content = download(CLEAN_URLS["divar_login"])
    if content:
        write_file(DIVAR_LOGIN_MANAGER, content)
        print("[OK] فایل تمیز دیوار جایگزین شد")
    else:
        print("[WARNING] دانلود نشد - از نسخه محلی استفاده می‌شود")


def run_app():
    print("\n🚀 در حال اجرای برنامه...")
    cmd = [PYTHON_EXE, MAIN_SCRIPT]
    print(f"[RUN] {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] برنامه با کد {e.returncode} خارج شد")
    except KeyboardInterrupt:
        print("\n⏹️ متوقف شد")


def main():
    print("=" * 60)
    print("🔧 تعمیر خودکار کامل + اجرا")
    print("=" * 60)

    fix_sheypoor_models()
    fix_divar_login_manager()

    print("\n✅ تمام تعمیرات انجام شد!")
    run_app()


if __name__ == "__main__":
    main()