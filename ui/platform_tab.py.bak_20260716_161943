"""
PlatformTab - تب عمومی برای Login هر پلتفرم.

ویژگی‌ها:
- بررسی Session ذخیره‌شده در شروع
- اگر Session معتبر بود، استفاده از آن (بدون Login)
- اگر نبود، شروع Login
- بدون timeout برای انتظار کد - کاربر تصمیم می‌گیرد
- دکمه لغو برای انصراف از Login
- مدیریت خطای کامل (کاربر مرورگر را ببندد، شبکه قطع شود و ...)
"""

from __future__ import annotations

import asyncio
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.browser_manager import BrowserManager  # noqa: E402
from core.session_manager import SessionManager  # noqa: E402
from core.session_models import SessionRecord, SessionStatus  # noqa: E402


# ---------------------------------------------------------------------------
# سیگنال‌ها
# ---------------------------------------------------------------------------
class LoginSignals(QObject):
    code_needed = Signal(str)
    login_finished = Signal(object)
    error_occurred = Signal(str)
    status_changed = Signal(str)
    session_status = Signal(str, str)  # status, message


# ---------------------------------------------------------------------------
# Worker برای بررسی Session
# ---------------------------------------------------------------------------
class SessionCheckWorker(QRunnable):
    """بررسی اعتبار Session ذخیره‌شده در یک thread مجزا."""

    def __init__(self, platform: str):
        super().__init__()
        self.platform = platform
        self.signals = LoginSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                sm = SessionManager(platform=self.platform)
                record = sm.load()
                if not record:
                    return None, "NO_SESSION"

                # اگر وضعیت مشخصاً INVALID است
                if record.status == SessionStatus.INVALID:
                    return record, "INVALID"

                # اعتبارسنجی واقعی با باز کردن مرورگر
                self.signals.status_changed.emit("در حال بررسی Session ذخیره‌شده...")
                bm = BrowserManager(session_record=record)
                async with bm:
                    status = await sm.validate(record, bm.page)

                if status == SessionStatus.VALID:
                    return record, "VALID"
                else:
                    return record, status.value

            record, status_key = loop.run_until_complete(_run())
            msg = {
                "NO_SESSION": "هیچ Session ذخیره‌شده‌ای وجود ندارد",
                "VALID": f"Session معتبر یافت شد ({record.phone if record else ''})",
                "INVALID": "Session منقضی شده - نیاز به Login مجدد",
                "EXPIRED": "Session منقضی شده",
                "UNKNOWN": "وضعیت Session قابل تشخیص نیست",
            }.get(status_key, status_key)

            self.signals.session_status.emit(status_key, msg)

        except Exception as e:
            self.signals.error_occurred.emit(f"خطا در بررسی Session: {e}")
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Worker برای Login
# ---------------------------------------------------------------------------
class LoginWorker(QRunnable):
    """اجرای LoginManager در یک thread مجزا."""

    def __init__(
        self,
        phone: str,
        platform_key: str,
        login_manager_factory: Callable,  # تغییر: استفاده از Callable به جای alias
    ):
        super().__init__()
        self.phone = phone
        self._platform_key = platform_key
        self._factory = login_manager_factory
        self.signals = LoginSignals()
        self._code_future: Optional[Future] = None
        self._cancelled = False
        self.setAutoDelete(True)

    def provide_code(self, code: str):
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

    def cancel(self):
        """لغو Login توسط کاربر."""
        self._cancelled = True
        if self._code_future and not self._code_future.done():
            self._code_future.cancel()

    async def _code_provider(self):
        self._code_future = Future()
        self.signals.code_needed.emit(self.phone)
        # بدون timeout - کاربر خودش تصمیم می‌گیرد
        try:
            code = self._code_future.result()
            if self._cancelled:
                raise asyncio.CancelledError("Login cancelled by user")
            return code
        except asyncio.CancelledError:
            raise

    @Slot()
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                session_manager = SessionManager(platform=self._platform_key)
                browser_manager = BrowserManager()

                async with browser_manager:
                    login_manager = self._factory(
                        browser_manager=browser_manager,
                        session_manager=session_manager,
                        code_provider=self._code_provider,
                    )
                    self.signals.status_changed.emit("در حال شروع فرآیند ورود...")
                    return await login_manager.login(self.phone)

            result = loop.run_until_complete(_run())
            self.signals.login_finished.emit(result)
        except asyncio.CancelledError:
            self.signals.status_changed.emit("Login لغو شد")
        except Exception as e:
            self.signals.error_occurred.emit(f"{type(e).__name__}: {e}")
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# صفحه وضعیت Session (صفحه اول)
# ---------------------------------------------------------------------------
class _StatusPage(QWidget):
    """صفحه اول: نمایش وضعیت Session + دکمه شروع Login."""

    start_login = Signal()
    check_session = Signal()
    logout = Signal()

    def __init__(self, platform_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._setup_ui(platform_name)

    def _setup_ui(self, platform_name: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"{platform_name}")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(10)

        # کادر وضعیت
        self.status_box = QLabel("⏳ در حال بررسی Session...")
        self.status_box.setAlignment(Qt.AlignCenter)
        self.status_box.setWordWrap(True)
        self.status_box.setMinimumWidth(400)
        self.status_box.setMaximumWidth(500)
        self.status_box.setMinimumHeight(80)
        self.status_box.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.status_box, alignment=Qt.AlignCenter)

        layout.addSpacing(15)

        # دکمه‌های اصلی
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)

        self.check_btn = QPushButton("🔄 بررسی Session")
        self._style_button(self.check_btn, "#6c757d")
        self.check_btn.clicked.connect(self.check_session.emit)
        btn_layout.addWidget(self.check_btn)

        self.login_btn = QPushButton("🔐 ورود به حساب کاربری")
        self._style_button(self.login_btn, self._color)
        self.login_btn.clicked.connect(self.start_login.emit)
        btn_layout.addWidget(self.login_btn)

        self.logout_btn = QPushButton("🚪 خروج از حساب (حذف Session)")
        self._style_button(self.logout_btn, "#e74c3c")
        self.logout_btn.clicked.connect(self.logout.emit)
        self.logout_btn.setEnabled(False)
        btn_layout.addWidget(self.logout_btn)

        layout.addLayout(btn_layout)
        layout.addSpacing(30)

    def _style_button(self, btn: QPushButton, color: str):
        btn.setMinimumWidth(400)
        btn.setMinimumHeight(45)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        btn.setFont(font)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background-color: #ccc; }}
        """)

    def set_status(self, text: str, is_valid: bool = False):
        self.status_box.setText(text)
        if is_valid:
            self.status_box.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    border: 2px solid #28a745;
                    border-radius: 8px;
                    padding: 15px;
                    font-size: 13px;
                    color: #155724;
                }
            """)
            self.logout_btn.setEnabled(True)
            self.login_btn.setText("🔐 ورود مجدد (جایگزینی Session)")
        else:
            self.status_box.setStyleSheet("""
                QLabel {
                    background-color: #f8f9fa;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    padding: 15px;
                    font-size: 13px;
                }
            """)
            self.logout_btn.setEnabled(False)
            self.login_btn.setText("🔐 ورود به حساب کاربری")

    def set_loading(self, loading: bool):
        self.check_btn.setEnabled(not loading)
        self.login_btn.setEnabled(not loading)
        if loading:
            self.check_btn.setText("⏳ در حال بررسی...")
        else:
            self.check_btn.setText("🔄 بررسی Session")


# ---------------------------------------------------------------------------
# صفحه ورود شماره
# ---------------------------------------------------------------------------
class _PhonePage(QWidget):
    submit_phone = Signal(str)
    go_back = Signal()

    def __init__(self, platform_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._setup_ui(platform_name)

    def _setup_ui(self, platform_name: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"ورود به {platform_name}")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = QLabel("لطفاً شماره موبایل خود را وارد کنید")
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet("color: #666;")
        layout.addWidget(description)

        layout.addSpacing(20)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09121234567")
        self.phone_input.setAlignment(Qt.AlignCenter)
        phone_font = QFont()
        phone_font.setPointSize(14)
        self.phone_input.setFont(phone_font)
        self.phone_input.setMinimumWidth(350)
        self.phone_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.phone_input, alignment=Qt.AlignCenter)

        self.submit_btn = QPushButton("ادامه")
        self._style_button(self.submit_btn, self._color)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        self.back_btn = QPushButton("← بازگشت")
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                padding: 8px;
            }
            QPushButton:hover { color: #333; }
        """)
        self.back_btn.clicked.connect(self.go_back.emit)
        layout.addWidget(self.back_btn, alignment=Qt.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(450)
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        layout.addSpacing(20)

    def _style_button(self, btn: QPushButton, color: str):
        btn.setMinimumWidth(350)
        btn.setMinimumHeight(45)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        btn.setFont(font)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background-color: #ccc; }}
        """)

    def _on_submit(self):
        phone = self.phone_input.text().strip()
        if not phone:
            QMessageBox.warning(self, "خطا", "لطفاً شماره موبایل را وارد کنید")
            return
        self.submit_phone.emit(phone)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_loading(self, loading: bool):
        self.submit_btn.setEnabled(not loading)
        self.phone_input.setEnabled(not loading)
        self.back_btn.setEnabled(not loading)
        self.submit_btn.setText("در حال پردازش..." if loading else "ادامه")

    def reset(self):
        self.phone_input.clear()
        self.status_label.clear()
        self.set_loading(False)


# ---------------------------------------------------------------------------
# صفحه ورود کد
# ---------------------------------------------------------------------------
class _CodePage(QWidget):
    submit_code = Signal(str)
    cancel_login = Signal()

    def __init__(self, platform_name: str, color: str, code_length: int = 6, parent=None):
        super().__init__(parent)
        self._color = color
        self._code_length = code_length
        self._setup_ui(platform_name)

    def _setup_ui(self, platform_name: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"کد تأیید {platform_name}")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.description = QLabel(f"کد {self._code_length} رقمی ارسال شده را وارد کنید")
        self.description.setAlignment(Qt.AlignCenter)
        self.description.setStyleSheet("color: #666;")
        layout.addWidget(self.description)

        # نکته مهم
        hint = QLabel("💡 هر زمان خواستید می‌توانید مرورگر را ببندید و دوباره تلاش کنید")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        hint.setWordWrap(True)
        hint.setMaximumWidth(400)
        layout.addWidget(hint, alignment=Qt.AlignCenter)

        layout.addSpacing(10)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("۰" * self._code_length)
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMaxLength(self._code_length)
        code_font = QFont()
        code_font.setPointSize(24)
        code_font.setBold(True)
        self.code_input.setFont(code_font)
        self.code_input.setMinimumWidth(350)
        self.code_input.setStyleSheet("""
            QLineEdit {
                letter-spacing: 8px;
                padding: 15px;
            }
        """)
        self.code_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.code_input, alignment=Qt.AlignCenter)

        self.submit_btn = QPushButton("ورود")
        self._style_button(self.submit_btn, self._color)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        self.cancel_btn = QPushButton("✖ لغو و بازگشت")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #e74c3c;
                border: none;
                padding: 10px;
                font-size: 12px;
            }
            QPushButton:hover { color: #c0392b; text-decoration: underline; }
        """)
        self.cancel_btn.clicked.connect(self.cancel_login.emit)
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(450)
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        layout.addSpacing(20)

    def _style_button(self, btn: QPushButton, color: str):
        btn.setMinimumWidth(350)
        btn.setMinimumHeight(45)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        btn.setFont(font)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background-color: #ccc; }}
        """)

    def set_phone(self, phone: str):
        self.description.setText(
            f"کد {self._code_length} رقمی ارسال شده به شماره {phone} را وارد کنید"
        )

    def _on_submit(self):
        code = self.code_input.text().strip()
        if len(code) != self._code_length or not code.isdigit():
            QMessageBox.warning(
                self, "خطا",
                f"کد تأیید باید دقیقاً {self._code_length} رقم باشد",
            )
            return
        self.submit_code.emit(code)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_loading(self, loading: bool):
        self.submit_btn.setEnabled(not loading)
        self.code_input.setEnabled(not loading)
        self.cancel_btn.setEnabled(not loading)
        self.submit_btn.setText("در حال ورود..." if loading else "ورود")

    def clear(self):
        self.code_input.clear()
        self.status_label.clear()


# ---------------------------------------------------------------------------
# PlatformTab
# ---------------------------------------------------------------------------
class PlatformTab(QWidget):
    """تب عمومی Login برای یک پلتفرم."""

    log_message = Signal(str, str)  # level, message

    # Page indices
    PAGE_STATUS = 0
    PAGE_PHONE = 1
    PAGE_CODE = 2

    def __init__(
        self,
        platform_name: str,
        platform_key: str,
        color: str,
        code_length: int,
        login_manager_factory: Callable,  # تغییر: استفاده از Callable به جای alias
        parent=None,
    ):
        super().__init__(parent)
        self._platform_name = platform_name
        self._platform_key = platform_key
        self._factory = login_manager_factory
        self._current_worker: Optional[LoginWorker] = None
        self._current_session: Optional[SessionRecord] = None

        self._setup_ui(color, code_length)
        self._connect_signals()

        # بررسی Session در شروع
        self._check_session()

    def _setup_ui(self, color: str, code_length: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)

        self.stack = QStackedWidget()

        self.status_page = _StatusPage(self._platform_name, color)
        self.phone_page = _PhonePage(self._platform_name, color)
        self.code_page = _CodePage(self._platform_name, color, code_length)

        self.stack.addWidget(self.status_page)   # 0
        self.stack.addWidget(self.phone_page)    # 1
        self.stack.addWidget(self.code_page)     # 2

        layout.addWidget(self.stack)

    def _connect_signals(self):
        # Status page
        self.status_page.start_login.connect(self._on_start_login)
        self.status_page.check_session.connect(self._check_session)
        self.status_page.logout.connect(self._on_logout)

        # Phone page
        self.phone_page.submit_phone.connect(self._on_phone_submitted)
        self.phone_page.go_back.connect(self._go_to_status)

        # Code page
        self.code_page.submit_code.connect(self._on_code_submitted)
        self.code_page.cancel_login.connect(self._on_cancel_login)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    # ------------------------------------------------------------------
    # Session Checking
    # ------------------------------------------------------------------
    def _check_session(self):
        """بررسی Session ذخیره‌شده در thread مجزا."""
        self.status_page.set_loading(True)
        self.status_page.set_status("⏳ در حال بررسی Session ذخیره‌شده...")
        self._log("INFO", f"[{self._platform_name}] Checking saved session...")

        worker = SessionCheckWorker(self._platform_key)
        worker.signals.session_status.connect(self._on_session_checked)
        worker.signals.error_occurred.connect(self._on_session_check_error)
        worker.signals.status_changed.connect(self._on_status_changed)
        QThreadPool.globalInstance().start(worker)

    @Slot(str, str)
    def _on_session_checked(self, status_key: str, message: str):
        self.status_page.set_loading(False)
        self._log("INFO", f"[{self._platform_name}] Session check: {status_key} - {message}")

        if status_key == "VALID":
            # Session معتبر است
            sm = SessionManager(platform=self._platform_key)
            record = sm.load()
            if record:
                self._current_session = record
                self.status_page.set_status(
                    f"✅ Session معتبر\n\n"
                    f"شماره: {record.phone}\n"
                    f"آخرین استفاده: {record.last_used_at or 'نامشخص'}\n"
                    f"تعداد کوکی‌ها: {len(record.storage_state.cookies)}",
                    is_valid=True,
                )
                self._log(
                    "INFO",
                    f"[{self._platform_name}] Session ready to use: {record.phone}",
                )
            else:
                self.status_page.set_status(f"ℹ️ {message}")
        elif status_key == "NO_SESSION":
            self.status_page.set_status(
                "ℹ️ هیچ Session ذخیره‌شده‌ای وجود ندارد.\n\n"
                "برای استفاده از برنامه، ابتدا وارد حساب کاربری خود شوید."
            )
        elif status_key in ("INVALID", "EXPIRED"):
            self.status_page.set_status(
                f"⚠️ {message}\n\nلطفاً مجدداً وارد حساب کاربری خود شوید."
            )
        else:
            self.status_page.set_status(f"❓ {message}")

    @Slot(str)
    def _on_session_check_error(self, error: str):
        self.status_page.set_loading(False)
        self.status_page.set_status(f"❌ خطا در بررسی Session:\n{error}")
        self._log("ERROR", f"[{self._platform_name}] Session check error: {error}")

    # ------------------------------------------------------------------
    # Login Flow
    # ------------------------------------------------------------------
    def _on_start_login(self):
        """کاربر می‌خواهد Login کند."""
        self.phone_page.reset()
        self.stack.setCurrentIndex(self.PAGE_PHONE)
        self.phone_page.phone_input.setFocus()

    def _go_to_status(self):
        """بازگشت به صفحه وضعیت."""
        self.stack.setCurrentIndex(self.PAGE_STATUS)
        self._check_session()

    def _on_phone_submitted(self, phone: str):
        self.phone_page.set_loading(True)
        self.phone_page.set_status("در حال باز کردن مرورگر...")
        self._log("INFO", f"[{self._platform_name}] شروع Login برای شماره {phone}")

        self._current_worker = LoginWorker(
            phone=phone,
            platform_key=self._platform_key,
            login_manager_factory=self._factory,
        )
        self._current_worker.signals.code_needed.connect(self._on_code_needed)
        self._current_worker.signals.login_finished.connect(self._on_login_finished)
        self._current_worker.signals.error_occurred.connect(self._on_error)
        self._current_worker.signals.status_changed.connect(self._on_status_changed)

        QThreadPool.globalInstance().start(self._current_worker)

    @Slot(str)
    def _on_code_needed(self, phone: str):
        self._log("INFO", f"[{self._platform_name}] منتظر کد تأیید برای {phone}")
        self.code_page.set_phone(phone)
        self.code_page.clear()
        self.stack.setCurrentIndex(self.PAGE_CODE)
        self.code_page.code_input.setFocus()

    def _on_code_submitted(self, code: str):
        self.code_page.set_loading(True)
        self.code_page.set_status("در حال تأیید کد...")
        self._log("INFO", f"[{self._platform_name}] کد تأیید ارسال شد")

        if self._current_worker:
            self._current_worker.provide_code(code)

    def _on_cancel_login(self):
        """کاربر Login را لغو کرد."""
        self._log("INFO", f"[{self._platform_name}] Login cancelled by user")
        if self._current_worker:
            self._current_worker.cancel()
            self._current_worker = None
        self._go_to_status()

    @Slot(object)
    def _on_login_finished(self, result):
        self._current_worker = None

        if result.success:
            self._log(
                "INFO",
                f"[{self._platform_name}] ✅ ورود موفق - Session: {result.session_path}",
            )
            QMessageBox.information(
                self,
                "ورود موفق",
                f"✅ ورود به {self._platform_name} با موفقیت انجام شد!\n\n"
                f"شماره: {result.phone}\n\n"
                f"📦 Session در دو محل ذخیره شد:\n"
                f"• دیتابیس SQLite: data/db/sessions.db\n"
                f"• فایل JSON: {result.session_path}",
            )
            self._go_to_status()
        else:
            self._log("ERROR", f"[{self._platform_name}] ❌ خطا: {result.error}")
            QMessageBox.critical(
                self,
                "خطا در ورود",
                f"❌ ورود به {self._platform_name} ناموفق بود\n\n"
                f"وضعیت: {result.state.value}\n"
                f"خطا: {result.error}\n\n"
                f"می‌توانید دوباره تلاش کنید.",
            )
            self.phone_page.set_loading(False)
            self.phone_page.set_status("")
            self.stack.setCurrentIndex(self.PAGE_PHONE)

    @Slot(str)
    def _on_error(self, error_msg: str):
        self._current_worker = None
        self._log("ERROR", f"[{self._platform_name}] خطای غیرمنتظره: {error_msg}")

        # اگر مرورگر بسته شده، فقط اطلاع بده و برگرد
        if "Target closed" in error_msg or "browser" in error_msg.lower():
            QMessageBox.warning(
                self,
                "مرورگر بسته شد",
                f"مرورگر بسته شد.\n\n{error_msg}\n\n"
                f"می‌توانید دوباره تلاش کنید.",
            )
        else:
            QMessageBox.critical(
                self,
                "خطا",
                f"خطای غیرمنتظره:\n{error_msg}\n\n"
                f"می‌توانید دوباره تلاش کنید.",
            )
        self._go_to_status()

    @Slot(str)
    def _on_status_changed(self, status: str):
        self._log("INFO", f"[{self._platform_name}] {status}")
        idx = self.stack.currentIndex()
        if idx == self.PAGE_PHONE:
            self.phone_page.set_status(status)
        elif idx == self.PAGE_CODE:
            self.code_page.set_status(status)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    def _on_logout(self):
        """حذف Session و خروج."""
        if not self._current_session:
            return

        reply = QMessageBox.question(
            self,
            "تأیید خروج",
            f"آیا از حذف Session برای شماره {self._current_session.phone} مطمئن هستید؟\n\n"
            f"پس از این کار، باید دوباره وارد شوید.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            sm = SessionManager(platform=self._platform_key)
            sm.delete(self._current_session)
            self._log(
                "INFO",
                f"[{self._platform_name}] Session deleted for {self._current_session.phone}",
            )
            self._current_session = None
            self._check_session()