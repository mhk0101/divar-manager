from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path


FILES: dict[str, str] = {
    "requirements.txt": r'''
PySide6>=6.6,<7
playwright>=1.42,<2
''',

    ".gitignore": r'''
.venv/
__pycache__/
*.pyc
*.pyo
*.log
.env
.idea/
.vscode/
data/logs/*
!data/logs/.gitkeep
data/sessions/*.json
data/sessions/backups/*.json
!data/sessions/.gitkeep
!data/sessions/backups/.gitkeep
''',

    "README.md": r'''
# Divar Desktop - Login Module

این پروژه فعلاً فقط شامل Login Module است.

Stack:
- Python 3.11
- PySide6
- Playwright

برای اجرای دستی:
1. نصب dependencyها: `pip install -r requirements.txt`
2. نصب مرورگر Playwright: `python -m playwright install chromium`
3. اجرای برنامه: `python run.py`

Login URL از env قابل تنظیم است:
- `DIVAR_LOGIN_URL`
- مقدار پیش‌فرض: `https://divar.ir`

Session از این منابع ذخیره می‌شود:
- Cookies از Playwright storage_state
- Local Storage از Playwright storage_state
- Session Storage از window.sessionStorage برای originهای بازشده

نکته:
برای تشخیص قطعی Login موفق، در مرحله بعد باید المنت یا API نهایی موفقیت ورود ارائه شود.
''',

    "docs/LOGIN_MODULE.md": r'''
# Login Module Documentation

## محدوده این مرحله

در این مرحله فقط ماژول Login پیاده‌سازی شده است.

پیاده‌سازی نشده:
- دیتابیس آگهی‌ها
- crawler
- استخراج آگهی
- مدیریت وضعیت آگهی
- فیلتر شهر/دسته‌بندی
- عملیات بعد از Login

## Selector Policy

هیچ Selector حدسی استفاده نشده است.

Selectorهای استفاده‌شده فقط بر اساس اطلاعات ارسال‌شده هستند:

1. گزینه ورود:
   - text exact: `ورود به حساب کاربری`

2. ورودی شماره موبایل:
   - `input[name="phone"][type="tel"][autocomplete="tel-national"]`

3. دکمه بعدی:
   - role button
   - name exact: `بعدی`

4. گروه کد تأیید:
   - role group
   - name exact: `کد تأیید`

5. ورودی‌های کد تأیید:
   - aria-label exact:
     - `رقم ۱`
     - `رقم ۲`
     - `رقم ۳`
     - `رقم ۴`
     - `رقم ۵`
     - `رقم ۶`

6. دکمه ورود:
   - role button
   - name exact: `ورود`

## Session Source

Session از ترکیب زیر ذخیره می‌شود:

### Cookies
از:
`browser_context.storage_state()["cookies"]`

### Local Storage
از:
`browser_context.storage_state()["origins"][...]["localStorage"]`

### Session Storage
چون Playwright Session Storage را داخل storage_state ذخیره نمی‌کند، جداگانه از هر Page و هر origin با JavaScript خوانده می‌شود:
`window.sessionStorage`

## Session Load

برای Load:

1. Cookies و Local Storage هنگام ساخت BrowserContext با `storage_state` تزریق می‌شوند.
2. Session Storage با `context.add_init_script` قبل از لود صفحه برای origin مربوطه بازگردانی می‌شود.

## Session Compare and Replace

در هر Login موفق:

1. Session فعلی از BrowserContext استخراج می‌شود.
2. Payload شامل Cookies + LocalStorage + SessionStorage normalize می‌شود.
3. SHA256 hash ساخته می‌شود.
4. با hash فایل قبلی مقایسه می‌شود.
5. اگر تغییر کرده باشد:
   - فایل قبلی backup می‌شود.
   - فایل جدید جایگزین می‌شود.
6. اگر تغییر نکرده باشد:
   - فایل دوباره با metadata جدید نوشته می‌شود.

## Login Success Detection

با اطلاعات فعلی، Login موفق قطعی قابل تشخیص نیست چون هنوز المنت یا response بعد از ورود ارسال نشده است.

تشخیص فعلی:
- گروه کد تأیید دیگر visible نباشد.
- داده‌های storage/cookie مربوط به divar.ir وجود داشته باشد.

برای نهایی‌سازی این بخش، یکی از این موارد لازم است:
- المنت پایدار بعد از ورود موفق
- API response مربوط به تأیید کد
- نام cookie/localStorage/sessionStorage مربوط به auth
''',

    "run.py": r'''
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.logging_config import configure_logging
from app.core.paths import ensure_app_directories
from app.main_window import MainWindow


def main() -> int:
    ensure_app_directories()
    configure_logging()

    app = QApplication(sys.argv)
    app.setApplicationName("Divar Desktop - Login Module")
    app.setLayoutDirection(Qt.RightToLeft)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
''',

    "app/__init__.py": r'''
__version__ = "0.1.0"
''',

    "app/main_window.py": r'''
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from app.modules.login.ui import LoginWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Divar Desktop - Login Module")
        self.resize(760, 560)

        self.login_widget = LoginWidget(self)
        self.setCentralWidget(self.login_widget)
''',

    "app/core/__init__.py": r'''
''',

    "app/core/paths.py": r'''
from __future__ import annotations

from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent

DATA_DIR = PROJECT_ROOT / "data"
SESSION_DIR = DATA_DIR / "sessions"
SESSION_BACKUP_DIR = SESSION_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"

SESSION_FILE = SESSION_DIR / "divar_session.json"


def ensure_app_directories() -> None:
    for path in (DATA_DIR, SESSION_DIR, SESSION_BACKUP_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
''',

    "app/core/settings.py": r'''
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import SESSION_FILE


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


@dataclass(frozen=True)
class LoginSettings:
    login_url: str = os.getenv("DIVAR_LOGIN_URL", "https://divar.ir")
    headless: bool = _bool_env("DIVAR_HEADLESS", False)
    timeout_ms: int = int(os.getenv("DIVAR_TIMEOUT_MS", "30000"))
    post_login_wait_ms: int = int(os.getenv("DIVAR_POST_LOGIN_WAIT_MS", "2500"))
    session_file: Path = SESSION_FILE
    viewport_width: int = 1280
    viewport_height: int = 900
''',

    "app/core/logging_config.py": r'''
from __future__ import annotations

import logging

from app.core.paths import LOG_DIR, ensure_app_directories


def configure_logging() -> None:
    ensure_app_directories()

    log_file = LOG_DIR / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
''',

    "app/infrastructure/__init__.py": r'''
''',

    "app/infrastructure/session/__init__.py": r'''
from app.infrastructure.session.session_manager import (
    SessionCompareResult,
    SessionManager,
    SessionSaveResult,
)

__all__ = [
    "SessionManager",
    "SessionSaveResult",
    "SessionCompareResult",
]
''',

    "app/infrastructure/session/session_manager.py": r'''
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.paths import SESSION_BACKUP_DIR, SESSION_FILE

logger = logging.getLogger(__name__)


SESSION_SCHEMA_VERSION = 1
SESSION_PROVIDER = "divar"


@dataclass(frozen=True)
class SessionCompareResult:
    old_hash: str | None
    new_hash: str
    changed: bool


@dataclass(frozen=True)
class SessionSaveResult:
    path: Path
    session_hash: str
    previous_hash: str | None
    changed: bool
    saved_at: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class SessionManager:
    def __init__(
        self,
        session_file: Path = SESSION_FILE,
        backup_dir: Path = SESSION_BACKUP_DIR,
    ) -> None:
        self.session_file = Path(session_file)
        self.backup_dir = Path(backup_dir)
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.session_file.exists()

    def load_document(self) -> dict[str, Any] | None:
        if not self.session_file.exists():
            return None

        try:
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"فایل Session خراب است: {self.session_file}") from exc

    def load_payload(self) -> dict[str, Any] | None:
        document = self.load_document()
        if not document:
            return None

        payload = document.get("payload")
        if not isinstance(payload, dict):
            return None

        return self.normalize_payload(payload)

    def describe_existing(self) -> str:
        document = self.load_document()
        if not document:
            return "Session ذخیره‌شده وجود ندارد."

        session_hash = str(document.get("session_hash") or "")
        short_hash = session_hash[:12] if session_hash else "بدون hash"
        updated_at = document.get("updated_at", "-")
        provider = document.get("provider", "-")

        return f"Session موجود است | provider: {provider} | updated_at: {updated_at} | hash: {short_hash}"

    def create_context(self, browser: Any, **context_options: Any) -> Any:
        payload = self.load_payload()

        if payload:
            storage_state = payload.get("storage_state") or {}
            if storage_state.get("cookies") or storage_state.get("origins"):
                context_options["storage_state"] = storage_state

        context = browser.new_context(**context_options)

        if payload:
            self.apply_session_storage_to_context(context, payload)

        return context

    def apply_session_storage_to_context(self, context: Any, payload: dict[str, Any]) -> None:
        session_storage = payload.get("session_storage") or {}
        if not session_storage:
            return

        encoded = json.dumps(session_storage, ensure_ascii=False)

        script = f"""
(() => {{
    const storageByOrigin = {encoded};
    const values = storageByOrigin[window.location.origin];

    if (!values) {{
        return;
    }}

    for (const [key, value] of Object.entries(values)) {{
        try {{
            if (value === null || typeof value === "undefined") {{
                continue;
            }}
            window.sessionStorage.setItem(key, String(value));
        }} catch (error) {{}}
    }}
}})();
"""

        context.add_init_script(script=script)

    def capture_from_context(self, context: Any) -> dict[str, Any]:
        try:
            storage_state = context.storage_state()
        except Exception as exc:
            logger.warning("Could not capture storage_state: %s", exc)
            storage_state = {"cookies": [], "origins": []}

        session_storage: dict[str, dict[str, str]] = {}

        for page in list(context.pages):
            try:
                if not page.url or page.url == "about:blank":
                    continue

                origin = page.evaluate("""() => window.location.origin""")

                if not origin or origin == "null":
                    continue

                if origin in session_storage:
                    continue

                items = page.evaluate(
                    """() => {
                        const data = {};
                        for (let i = 0; i < window.sessionStorage.length; i++) {
                            const key = window.sessionStorage.key(i);
                            data[key] = window.sessionStorage.getItem(key);
                        }
                        return data;
                    }"""
                )

                if isinstance(items, dict):
                    session_storage[origin] = items
                else:
                    session_storage[origin] = {}

            except Exception as exc:
                logger.debug("Could not capture sessionStorage for a page: %s", exc)

        return self.normalize_payload(
            {
                "storage_state": storage_state,
                "session_storage": session_storage,
            }
        )

    def compare_with_existing(self, payload: dict[str, Any]) -> SessionCompareResult:
        new_hash = self.compute_hash(payload)
        existing = self.load_document()
        old_hash = existing.get("session_hash") if existing else None

        return SessionCompareResult(
            old_hash=old_hash,
            new_hash=new_hash,
            changed=old_hash != new_hash,
        )

    def save(self, payload: dict[str, Any]) -> SessionSaveResult:
        normalized_payload = self.normalize_payload(payload)
        new_hash = self.compute_hash(normalized_payload)

        existing = self.load_document()
        old_hash = existing.get("session_hash") if existing else None
        changed = old_hash != new_hash

        if existing and changed and self.session_file.exists():
            self._backup_existing(old_hash)

        now = _utc_now_iso()

        document = {
            "schema_version": SESSION_SCHEMA_VERSION,
            "provider": SESSION_PROVIDER,
            "updated_at": now,
            "session_hash": new_hash,
            "previous_hash": old_hash,
            "last_compare": {
                "old_hash": old_hash,
                "new_hash": new_hash,
                "changed": changed,
            },
            "sources": {
                "cookies": "browser_context.storage_state().cookies",
                "local_storage": "browser_context.storage_state().origins.localStorage",
                "session_storage": "window.sessionStorage per origin",
            },
            "payload": normalized_payload,
        }

        self._atomic_write(document)

        return SessionSaveResult(
            path=self.session_file,
            session_hash=new_hash,
            previous_hash=old_hash,
            changed=changed,
            saved_at=now,
        )

    def _backup_existing(self, old_hash: str | None) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = old_hash[:12] if old_hash else "unknown"
        backup_path = self.backup_dir / f"{self.session_file.stem}.{timestamp}.{suffix}.json"
        shutil.copy2(self.session_file, backup_path)
        logger.info("Previous session backed up: %s", backup_path)

    def _atomic_write(self, document: dict[str, Any]) -> None:
        tmp_path = self.session_file.with_name(f"{self.session_file.name}.tmp")
        tmp_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(self.session_file)

    @classmethod
    def compute_hash(cls, payload: dict[str, Any]) -> str:
        normalized = cls.normalize_payload(payload)
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def normalize_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        storage_state = payload.get("storage_state") or {}

        cookies: list[dict[str, Any]] = []
        for cookie in storage_state.get("cookies", []) or []:
            if isinstance(cookie, dict):
                cookies.append({str(key): cookie[key] for key in sorted(cookie.keys())})

        cookies.sort(
            key=lambda item: (
                str(item.get("domain", "")),
                str(item.get("path", "")),
                str(item.get("name", "")),
            )
        )

        origins: list[dict[str, Any]] = []
        for origin_data in storage_state.get("origins", []) or []:
            if not isinstance(origin_data, dict):
                continue

            normalized_origin: dict[str, Any] = {}

            for key, value in origin_data.items():
                if key == "localStorage":
                    local_storage_items: list[dict[str, Any]] = []

                    for item in value or []:
                        if isinstance(item, dict):
                            local_storage_items.append(
                                {str(item_key): item[item_key] for item_key in sorted(item.keys())}
                            )

                    local_storage_items.sort(key=lambda item: str(item.get("name", "")))
                    normalized_origin[key] = local_storage_items
                else:
                    normalized_origin[key] = value

            origins.append(normalized_origin)

        origins.sort(key=lambda item: str(item.get("origin", "")))

        raw_session_storage = payload.get("session_storage") or {}
        session_storage: dict[str, dict[str, Any]] = {}

        if isinstance(raw_session_storage, dict):
            for origin, values in raw_session_storage.items():
                if not isinstance(values, dict):
                    continue
                session_storage[str(origin)] = {
                    str(key): values[key]
                    for key in sorted(values.keys())
                }

        return {
            "storage_state": {
                "cookies": cookies,
                "origins": origins,
            },
            "session_storage": session_storage,
        }

    @staticmethod
    def has_divar_storage_material(payload: dict[str, Any]) -> bool:
        normalized = SessionManager.normalize_payload(payload)
        storage_state = normalized.get("storage_state") or {}

        for cookie in storage_state.get("cookies", []) or []:
            domain = str(cookie.get("domain", "")).lstrip(".")
            if domain == "divar.ir" or domain.endswith(".divar.ir"):
                return True

        for origin_data in storage_state.get("origins", []) or []:
            origin = str(origin_data.get("origin", ""))
            if "divar.ir" in origin and origin_data.get("localStorage"):
                return True

        for origin, values in (normalized.get("session_storage") or {}).items():
            if "divar.ir" in str(origin) and values:
                return True

        return False
''',

    "app/modules/__init__.py": r'''
''',

    "app/modules/login/__init__.py": r'''
''',

    "app/modules/login/selectors.py": r'''
from __future__ import annotations


LOGIN_ACCOUNT_TEXT = "ورود به حساب کاربری"

PHONE_INPUT_SELECTOR = 'input[name="phone"][type="tel"][autocomplete="tel-national"]'
PHONE_INPUT_PLACEHOLDER = "۰۹۱۲ ۱۲۳ ۴۵۶۷"

NEXT_BUTTON_TEXT = "بعدی"

VERIFICATION_GROUP_ARIA_LABEL = "کد تأیید"

VERIFICATION_DIGIT_ARIA_LABELS = [
    "رقم ۱",
    "رقم ۲",
    "رقم ۳",
    "رقم ۴",
    "رقم ۵",
    "رقم ۶",
]

LOGIN_BUTTON_TEXT = "ورود"

OPEN_INITIATE_ENDPOINT = "https://api.divar.ir/v8/auth/open-initiate-page"
''',

    "app/modules/login/models.py": r'''
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class LoginStatus(str, Enum):
    IDLE = "idle"
    OPENING = "opening"
    PHONE_SUBMITTED = "phone_submitted"
    CODE_REQUIRED = "code_required"
    AUTHENTICATING = "authenticating"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LoginResult:
    success: bool
    status: LoginStatus
    message: str
    session_file: str | None = None
    session_hash: str | None = None
    previous_hash: str | None = None
    session_changed: bool | None = None
    storage_changed_during_login: bool | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data
''',

    "app/modules/login/utils.py": r'''
from __future__ import annotations

import re


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_digits(value: str) -> str:
    return value.translate(_DIGIT_TRANSLATION)


def normalize_phone(phone: str) -> str:
    normalized = normalize_digits(phone or "")
    digits = re.sub(r"\D+", "", normalized)

    if digits.startswith("0098"):
        digits = digits[2:]

    if digits.startswith("98") and len(digits) == 12 and digits[2] == "9":
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits

    if not re.fullmatch(r"09\d{9}", digits):
        raise ValueError("شماره موبایل باید ۱۱ رقم و با 09 شروع شود.")

    return digits


def normalize_code(code: str) -> str:
    normalized = normalize_digits(code or "")
    digits = re.sub(r"\D+", "", normalized)

    if not re.fullmatch(r"\d{6}", digits):
        raise ValueError("کد تأیید باید دقیقاً ۶ رقم باشد.")

    return digits
''',

    "app/modules/login/login_manager.py": r'''
from __future__ import annotations

import logging
from typing import Any, Callable

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from app.core.settings import LoginSettings
from app.infrastructure.session.session_manager import SessionManager
from app.modules.login.models import LoginResult, LoginStatus
from app.modules.login.selectors import (
    LOGIN_ACCOUNT_TEXT,
    LOGIN_BUTTON_TEXT,
    NEXT_BUTTON_TEXT,
    OPEN_INITIATE_ENDPOINT,
    PHONE_INPUT_SELECTOR,
    VERIFICATION_DIGIT_ARIA_LABELS,
    VERIFICATION_GROUP_ARIA_LABEL,
)
from app.modules.login.utils import normalize_code, normalize_phone

logger = logging.getLogger(__name__)


class LoginFlowError(RuntimeError):
    pass


class LoginManager:
    def __init__(
        self,
        settings: LoginSettings | None = None,
        session_manager: SessionManager | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings or LoginSettings()
        self.session_manager = session_manager or SessionManager(self.settings.session_file)
        self.status_callback = status_callback or (lambda message: None)

        self.playwright: Any | None = None
        self.browser: Any | None = None
        self.context: Any | None = None
        self.page: Any | None = None

        self._pre_auth_payload: dict[str, Any] | None = None

    def start_login(self, phone: str) -> None:
        phone = normalize_phone(phone)

        self._status("در حال آماده‌سازی مرورگر...")
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.settings.headless,
        )

        context_options = {
            "viewport": {
                "width": self.settings.viewport_width,
                "height": self.settings.viewport_height,
            },
            "locale": "fa-IR",
        }

        if self.session_manager.exists():
            self._status("Session قبلی پیدا شد و در BrowserContext بارگذاری می‌شود...")
        else:
            self._status("Session قبلی وجود ندارد. Context جدید ساخته می‌شود...")

        self.context = self.session_manager.create_context(
            self.browser,
            **context_options,
        )
        self.context.set_default_timeout(self.settings.timeout_ms)

        self.page = self.context.new_page()

        self._status(f"در حال باز کردن صفحه ورود: {self.settings.login_url}")
        self.page.goto(
            self.settings.login_url,
            wait_until="domcontentloaded",
            timeout=self.settings.timeout_ms,
        )

        self._click_login_account_option()
        self._fill_phone_and_go_next(phone)
        self._wait_for_code_inputs()

        self._pre_auth_payload = self.session_manager.capture_from_context(self.context)

        self._status("کد تأیید درخواست شد. لطفاً کد ۶ رقمی را در برنامه وارد کنید.")

    def submit_code(self, code: str) -> LoginResult:
        if not self.page or not self.context:
            raise LoginFlowError("فرآیند Login شروع نشده است.")

        code = normalize_code(code)

        self._status("در حال وارد کردن کد تأیید...")

        for label, digit in zip(VERIFICATION_DIGIT_ARIA_LABELS, code, strict=True):
            locator = self.page.get_by_label(label, exact=True).first
            locator.wait_for(state="visible", timeout=self.settings.timeout_ms)
            locator.fill(digit)

        self._status("در حال کلیک روی دکمه ورود...")
        login_button = self.page.get_by_role("button", name=LOGIN_BUTTON_TEXT, exact=True)
        self._click_first_visible(login_button, "دکمه ورود")

        try:
            self.page.wait_for_load_state(
                "networkidle",
                timeout=self.settings.post_login_wait_ms,
            )
        except PlaywrightTimeoutError:
            pass

        self.page.wait_for_timeout(self.settings.post_login_wait_ms)

        code_group_visible = self._is_code_group_visible()

        payload = self.session_manager.capture_from_context(self.context)
        after_hash = self.session_manager.compute_hash(payload)

        pre_hash = None
        if self._pre_auth_payload is not None:
            pre_hash = self.session_manager.compute_hash(self._pre_auth_payload)

        storage_changed_during_login = None
        if pre_hash is not None:
            storage_changed_during_login = pre_hash != after_hash

        has_divar_material = self.session_manager.has_divar_storage_material(payload)

        if not code_group_visible and has_divar_material:
            save_result = self.session_manager.save(payload)

            if save_result.changed:
                message = "ورود موفق بود. Session جدید ذخیره و جایگزین Session قبلی شد."
            else:
                message = "ورود موفق بود. Session با فایل قبلی یکسان بود و metadata به‌روزرسانی شد."

            self._status(message)

            return LoginResult(
                success=True,
                status=LoginStatus.SUCCESS,
                message=message,
                session_file=str(save_result.path),
                session_hash=save_result.session_hash,
                previous_hash=save_result.previous_hash,
                session_changed=save_result.changed,
                storage_changed_during_login=storage_changed_during_login,
            )

        if code_group_visible:
            message = (
                "ورود تأیید نشد یا کد واردشده معتبر نبود. "
                "صفحه کد تأیید همچنان فعال است. Session جایگزین نشد."
            )
            self._status(message)

            return LoginResult(
                success=False,
                status=LoginStatus.FAILED,
                message=message,
                session_file=None,
                session_hash=after_hash,
                previous_hash=pre_hash,
                session_changed=None,
                storage_changed_during_login=storage_changed_during_login,
            )

        message = (
            "وضعیت ورود با اطلاعات فعلی قطعی نیست. "
            "برای تشخیص دقیق، المنت یا API موفقیت ورود را ارسال کنید. "
            "Session جایگزین نشد."
        )
        self._status(message)

        return LoginResult(
            success=False,
            status=LoginStatus.UNKNOWN,
            message=message,
            session_file=None,
            session_hash=after_hash,
            previous_hash=pre_hash,
            session_changed=None,
            storage_changed_during_login=storage_changed_during_login,
        )

    def close(self) -> None:
        self._status("در حال بستن منابع مرورگر...")

        if self.context is not None:
            try:
                self.context.close()
            except Exception as exc:
                logger.debug("Could not close context: %s", exc)
            self.context = None

        if self.browser is not None:
            try:
                self.browser.close()
            except Exception as exc:
                logger.debug("Could not close browser: %s", exc)
            self.browser = None

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception as exc:
                logger.debug("Could not stop Playwright: %s", exc)
            self.playwright = None

        self.page = None

    def _click_login_account_option(self) -> None:
        if not self.page:
            raise LoginFlowError("Page آماده نیست.")

        self._status('در حال انتخاب گزینه "ورود به حساب کاربری"...')
        locator = self.page.get_by_text(LOGIN_ACCOUNT_TEXT, exact=True)
        self._click_first_visible(locator, "گزینه ورود به حساب کاربری")

    def _fill_phone_and_go_next(self, phone: str) -> None:
        if not self.page:
            raise LoginFlowError("Page آماده نیست.")

        self._status("در حال وارد کردن شماره موبایل...")
        phone_input = self.page.locator(PHONE_INPUT_SELECTOR).first
        phone_input.wait_for(state="visible", timeout=self.settings.timeout_ms)
        phone_input.fill(phone)

        next_button = self.page.get_by_role("button", name=NEXT_BUTTON_TEXT, exact=True)

        self._status("در حال ارسال شماره و انتظار برای پاسخ API...")

        try:
            with self.page.expect_response(
                self._matches_open_initiate_endpoint,
                timeout=self.settings.timeout_ms,
            ) as response_info:
                self._click_first_visible(next_button, "دکمه بعدی")

            response = response_info.value

            if not response.ok:
                raise LoginFlowError(
                    f"API ارسال شماره موبایل موفق نبود. status={response.status}"
                )

            self._validate_open_initiate_response(response, phone)

        except PlaywrightTimeoutError:
            self._status(
                "هشدار: پاسخ API open-initiate-page در زمان تعیین‌شده دریافت نشد. "
                "اگر صفحه کد تأیید نمایش داده شده باشد، ادامه می‌دهیم."
            )

    def _wait_for_code_inputs(self) -> None:
        if not self.page:
            raise LoginFlowError("Page آماده نیست.")

        self._status("در انتظار نمایش ورودی‌های کد تأیید...")

        group = self.page.get_by_role(
            "group",
            name=VERIFICATION_GROUP_ARIA_LABEL,
            exact=True,
        ).first
        group.wait_for(state="visible", timeout=self.settings.timeout_ms)

        for label in VERIFICATION_DIGIT_ARIA_LABELS:
            self.page.get_by_label(label, exact=True).first.wait_for(
                state="visible",
                timeout=self.settings.timeout_ms,
            )

    def _validate_open_initiate_response(self, response: Any, phone: str) -> None:
        try:
            data = response.json()
        except Exception:
            self._status("پاسخ API ارسال شماره JSON قابل خواندن نبود، اما status موفق است.")
            return

        response_phone = (
            data.get("data", {})
            .get("data", {})
            .get("phone", {})
            .get("str", {})
            .get("value")
        )

        if not response_phone:
            return

        try:
            normalized_response_phone = normalize_phone(str(response_phone))
        except ValueError:
            self._status("هشدار: شماره برگشتی API قابل normalize نبود.")
            return

        if normalized_response_phone != phone:
            self._status("هشدار: شماره برگشتی API با شماره واردشده متفاوت است.")

    def _matches_open_initiate_endpoint(self, response: Any) -> bool:
        clean_url = response.url.split("?", 1)[0].rstrip("/")
        expected_url = OPEN_INITIATE_ENDPOINT.rstrip("/")
        return clean_url == expected_url

    def _is_code_group_visible(self) -> bool:
        if not self.page:
            return False

        try:
            group = self.page.get_by_role(
                "group",
                name=VERIFICATION_GROUP_ARIA_LABEL,
                exact=True,
            ).first
            return bool(group.is_visible())
        except Exception:
            return False

    def _click_first_visible(self, locator: Any, description: str) -> None:
        try:
            count = locator.count()

            for index in range(min(count, 20)):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        candidate.click(timeout=self.settings.timeout_ms)
                        return
                except PlaywrightError:
                    continue

            locator.first.wait_for(state="visible", timeout=self.settings.timeout_ms)
            locator.first.click(timeout=self.settings.timeout_ms)

        except PlaywrightError as exc:
            raise LoginFlowError(f"{description} قابل مشاهده یا قابل کلیک نیست.") from exc

    def _status(self, message: str) -> None:
        logger.info(message)
        self.status_callback(message)
''',

    "app/modules/login/worker.py": r'''
from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QObject, Signal, Slot

from app.core.settings import LoginSettings
from app.infrastructure.session.session_manager import SessionManager
from app.modules.login.login_manager import LoginManager
from app.modules.login.models import LoginStatus

logger = logging.getLogger(__name__)


class LoginWorker(QObject):
    status_changed = Signal(str)
    code_required = Signal()
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._manager: LoginManager | None = None

    @Slot(str, bool)
    def start_login(self, phone: str, headless: bool) -> None:
        if self._manager is not None:
            self.failed.emit("یک فرآیند ورود فعال است.")
            return

        try:
            settings = replace(LoginSettings(), headless=headless)
            session_manager = SessionManager(settings.session_file)

            self._manager = LoginManager(
                settings=settings,
                session_manager=session_manager,
                status_callback=self.status_changed.emit,
            )

            self._manager.start_login(phone)
            self.code_required.emit()

        except Exception as exc:
            logger.exception("Login start failed")
            self._cleanup()
            self.failed.emit(str(exc))

    @Slot(str)
    def submit_code(self, code: str) -> None:
        if self._manager is None:
            self.failed.emit("فرآیند ورود فعال نیست.")
            return

        try:
            result = self._manager.submit_code(code)
            self.finished.emit(result.to_dict())

            if result.success or result.status != LoginStatus.FAILED:
                self._cleanup()

        except Exception as exc:
            logger.exception("Login code submit failed")
            self._cleanup()
            self.failed.emit(str(exc))

    @Slot()
    def cancel(self) -> None:
        self._cleanup()
        self.status_changed.emit("فرآیند ورود لغو شد.")

    def _cleanup(self) -> None:
        if self._manager is not None:
            try:
                self._manager.close()
            except Exception as exc:
                logger.debug("Could not cleanup LoginManager: %s", exc)
            self._manager = None
''',

    "app/modules/login/ui.py": r'''
from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.settings import LoginSettings
from app.infrastructure.session.session_manager import SessionManager
from app.modules.login.selectors import PHONE_INPUT_PLACEHOLDER
from app.modules.login.utils import normalize_code, normalize_phone
from app.modules.login.worker import LoginWorker


class LoginWidget(QWidget):
    start_requested = Signal(str, bool)
    code_submitted = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.settings = LoginSettings()
        self.session_manager = SessionManager(self.settings.session_file)

        self.worker_thread = QThread(self)
        self.worker = LoginWorker()
        self.worker.moveToThread(self.worker_thread)

        self._build_ui()
        self._connect_signals()

        self.worker_thread.start()

        self._refresh_session_label()
        self._set_idle()

    def _build_ui(self) -> None:
        self.setLayoutDirection(Qt.RightToLeft)

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(12)

        title = QLabel("ماژول ورود دیوار")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("TitleLabel")
        root_layout.addWidget(title)

        phone_group = QGroupBox("مرحله ۱: شماره موبایل")
        phone_layout = QFormLayout(phone_group)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText(PHONE_INPUT_PLACEHOLDER)
        self.phone_input.setClearButtonEnabled(True)

        self.headless_checkbox = QCheckBox("اجرای مرورگر به صورت Headless")
        self.headless_checkbox.setChecked(self.settings.headless)

        self.start_button = QPushButton("شروع ورود")
        self.cancel_button = QPushButton("لغو فرآیند")
        self.cancel_button.setEnabled(False)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.cancel_button)

        phone_layout.addRow("شماره موبایل:", self.phone_input)
        phone_layout.addRow("", self.headless_checkbox)
        phone_layout.addRow("", buttons_layout)

        root_layout.addWidget(phone_group)

        code_group = QGroupBox("مرحله ۲: کد تأیید")
        code_layout = QFormLayout(code_group)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("کد ۶ رقمی")
        self.code_input.setMaxLength(6)
        self.code_input.setClearButtonEnabled(True)

        self.code_button = QPushButton("ثبت کد و ورود")

        code_layout.addRow("کد تأیید:", self.code_input)
        code_layout.addRow("", self.code_button)

        root_layout.addWidget(code_group)

        session_group = QGroupBox("Session")
        session_layout = QVBoxLayout(session_group)

        self.session_label = QLabel()
        self.session_label.setWordWrap(True)

        self.refresh_session_button = QPushButton("بازخوانی وضعیت Session")

        session_layout.addWidget(self.session_label)
        session_layout.addWidget(self.refresh_session_button)

        root_layout.addWidget(session_group)

        status_group = QGroupBox("وضعیت عملیات")
        status_layout = QVBoxLayout(status_group)

        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(140)

        status_layout.addWidget(self.status_box)

        root_layout.addWidget(status_group, stretch=1)

        self.setStyleSheet(
            """
            QWidget {
                font-size: 13px;
            }

            QLabel#TitleLabel {
                font-size: 20px;
                font-weight: bold;
                padding: 10px;
            }

            QGroupBox {
                font-weight: bold;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                margin-top: 10px;
                padding: 10px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                right: 12px;
                padding: 0 5px;
            }

            QLineEdit {
                padding: 7px;
                border: 1px solid #c8c8c8;
                border-radius: 6px;
            }

            QPushButton {
                padding: 8px 12px;
                border-radius: 6px;
            }

            QTextEdit {
                border: 1px solid #c8c8c8;
                border-radius: 6px;
                padding: 6px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._on_start_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.code_button.clicked.connect(self._on_code_clicked)
        self.refresh_session_button.clicked.connect(self._refresh_session_label)

        self.phone_input.returnPressed.connect(self._on_start_clicked)
        self.code_input.returnPressed.connect(self._on_code_clicked)

        self.start_requested.connect(self.worker.start_login)
        self.code_submitted.connect(self.worker.submit_code)
        self.cancel_requested.connect(self.worker.cancel)

        self.worker.status_changed.connect(self._append_status)
        self.worker.code_required.connect(self._on_code_required)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)

        self.worker_thread.finished.connect(self.worker.deleteLater)

    def _on_start_clicked(self) -> None:
        try:
            phone = normalize_phone(self.phone_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "شماره نامعتبر", str(exc))
            return

        self.status_box.clear()
        self._append_status("شروع فرآیند ورود...")
        self._set_active()
        self.start_requested.emit(phone, self.headless_checkbox.isChecked())

    def _on_cancel_clicked(self) -> None:
        self.cancel_requested.emit()
        self._append_status("درخواست لغو ارسال شد.")
        self._set_idle()

    def _on_code_required(self) -> None:
        self._append_status("کد تأیید آماده دریافت است.")
        self.code_input.setEnabled(True)
        self.code_button.setEnabled(True)
        self.code_input.clear()
        self.code_input.setFocus()

    def _on_code_clicked(self) -> None:
        try:
            code = normalize_code(self.code_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "کد نامعتبر", str(exc))
            return

        self._append_status("کد برای بررسی ارسال شد...")
        self.code_input.setEnabled(False)
        self.code_button.setEnabled(False)
        self.code_submitted.emit(code)

    def _on_finished(self, result: dict) -> None:
        message = result.get("message", "")
        status = result.get("status", "")

        if message:
            self._append_status(message)

        session_file = result.get("session_file")
        if session_file:
            self._append_status(f"فایل Session: {session_file}")

        if result.get("success"):
            QMessageBox.information(self, "Login موفق", message or "ورود موفق بود.")
            self._set_idle()
            self._refresh_session_label()
            return

        if status == "failed":
            QMessageBox.warning(
                self,
                "Login تأیید نشد",
                (message or "ورود تأیید نشد.") + "\nمی‌توانید کد جدید وارد کنید یا فرآیند را لغو کنید.",
            )
            self.code_input.clear()
            self.code_input.setEnabled(True)
            self.code_button.setEnabled(True)
            self.code_input.setFocus()
            return

        QMessageBox.warning(self, "وضعیت نامشخص", message or "وضعیت ورود مشخص نیست.")
        self._set_idle()
        self._refresh_session_label()

    def _on_failed(self, message: str) -> None:
        self._append_status(f"خطا: {message}")
        QMessageBox.critical(self, "خطا", message)
        self._set_idle()
        self._refresh_session_label()

    def _append_status(self, message: str) -> None:
        self.status_box.append(message)

    def _refresh_session_label(self) -> None:
        try:
            self.session_label.setText(self.session_manager.describe_existing())
        except Exception as exc:
            self.session_label.setText(f"خطا در خواندن Session: {exc}")

    def _set_active(self) -> None:
        self.phone_input.setEnabled(False)
        self.headless_checkbox.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.code_input.setEnabled(False)
        self.code_button.setEnabled(False)

    def _set_idle(self) -> None:
        self.phone_input.setEnabled(True)
        self.headless_checkbox.setEnabled(True)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.code_input.setEnabled(False)
        self.code_button.setEnabled(False)
        self.code_input.clear()

    def closeEvent(self, event) -> None:
        try:
            self.cancel_requested.emit()
            self.worker_thread.quit()
            self.worker_thread.wait(5000)
        finally:
            super().closeEvent(event)
''',

    "data/sessions/.gitkeep": r'''
''',

    "data/sessions/backups/.gitkeep": r'''
''',

    "data/logs/.gitkeep": r'''
''',
}


def write_project_files(project_dir: Path, force: bool) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)

    for relative_path, content in FILES.items():
        path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists() and not force:
            continue

        normalized_content = textwrap.dedent(content).lstrip("\n")
        path.write_text(normalized_content, encoding="utf-8")

    print(f"Project files created at: {project_dir}")


def venv_python(project_dir: Path) -> Path:
    if os.name == "nt":
        return project_dir / ".venv" / "Scripts" / "python.exe"
    return project_dir / ".venv" / "bin" / "python"


def run_command(command: list[str | Path], cwd: Path) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"\n$ {printable}")
    subprocess.check_call([str(part) for part in command], cwd=str(cwd))


def install_dependencies(project_dir: Path) -> Path:
    venv_dir = project_dir / ".venv"
    py = venv_python(project_dir)

    if not py.exists():
        run_command([sys.executable, "-m", "venv", venv_dir], cwd=project_dir)

    run_command([py, "-m", "pip", "install", "--upgrade", "pip"], cwd=project_dir)
    run_command([py, "-m", "pip", "install", "-r", "requirements.txt"], cwd=project_dir)
    run_command([py, "-m", "playwright", "install", "chromium"], cwd=project_dir)

    return py


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-dir",
        default="divar_login_module_project",
        help="Target project directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Do not create venv or install dependencies",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Only create project files",
    )

    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()

    write_project_files(project_dir, force=args.force)

    if args.no_install:
        py = venv_python(project_dir)
        if not py.exists():
            py = Path(sys.executable)
    else:
        py = install_dependencies(project_dir)

    if not args.no_run:
        run_command([py, "run.py"], cwd=project_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())