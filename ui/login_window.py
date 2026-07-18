"""
LoginWindow - رابط کاربری گرافیکی برای ماژول Login.

این پنجره از QStackedWidget استفاده می‌کند تا بین دو صفحه جابجا شود:
1. صفحه ورود شماره موبایل
2. صفحه ورود کد تأیید

تمام عملیات Playwright در QThread جداگانه اجرا می‌شود تا UI فریز نشود.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# افزودن ریشه پروژه به sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DEFAULT_SESSION_FILE  # noqa: E402
from core.browser_manager import BrowserManager  # noqa: E402
from core.session_manager import SessionManager  # noqa: E402
from modules.login import LoginManager, LoginResult  # noqa: E402


# ---------------------------------------------------------------------------
# سیگنال‌ها برای ارتباط بین Threadها
# ---------------------------------------------------------------------------
class LoginSignals(QObject):
    """سیگنال‌های مورد نیاز برای ارتباط Login Thread با UI."""
    code_needed = Signal(str)  # phone number
    login_finished = Signal(object)  # LoginResult
    error_occurred = Signal(str)
    status_changed = Signal(str)


# ---------------------------------------------------------------------------
# Worker برای اجرای Login در Thread جداگانه
# ---------------------------------------------------------------------------
class LoginWorker(QRunnable):
    """اجرای LoginManager در یک thread مجزا."""

    def __init__(self, phone: str):
        super().__init__()
        self.phone = phone
        self.signals = LoginSignals()
        self._code_future: Optional[Future] = None
        self.setAutoDelete(True)

    def provide_code(self, code: str):
        """
        این متد از UI thread صدا زده می‌شود تا کد را به worker ارسال کند.
        """
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

    async def _code_provider(self):
        """
        این تابع از LoginManager صدا زده می‌شود.
        منتظر می‌ماند تا کاربر در UI کد را وارد کند.
        """
        # ایجاد future برای دریافت کد
        self._code_future = Future()
        # سیگنال به UI برای نمایش صفحه کد
        self.signals.code_needed.emit(self.phone)
        # منتظر کد می‌مانیم (این blocking است در worker thread)
        code = self._code_future.result()
        return code

    @Slot()
    def run(self):
        """اجرای فرآیند Login."""
        try:
            # Event loop جدید برای این thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def _run():
                session_manager = SessionManager(platform="divar")
                browser_manager = BrowserManager()

                async with browser_manager:
                    login_manager = LoginManager(
                        browser_manager=browser_manager,
                        session_manager=session_manager,
                        code_provider=self._code_provider,
                    )

                    self.signals.status_changed.emit("در حال باز کردن صفحه ورود...")
                    result = await login_manager.login(self.phone)
                    return result

            result = loop.run_until_complete(_run())
            self.signals.login_finished.emit(result)

        except Exception as e:
            self.signals.error_occurred.emit(str(e))
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# صفحه اول: ورود شماره موبایل
# ---------------------------------------------------------------------------
class PhonePage(QWidget):
    """صفحه ورود شماره موبایل."""

    submit_phone = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        # عنوان
        title = QLabel("ورود به حساب کاربری دیوار")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # توضیح
        description = QLabel("لطفاً شماره موبایل خود را وارد کنید")
        description.setAlignment(Qt.AlignCenter)
        description.setStyleSheet("color: #666;")
        layout.addWidget(description)

        # فاصله
        layout.addSpacing(20)

        # فیلد شماره موبایل
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09121234567")
        self.phone_input.setAlignment(Qt.AlignCenter)
        phone_font = QFont()
        phone_font.setPointSize(14)
        self.phone_input.setFont(phone_font)
        self.phone_input.setMinimumWidth(300)
        self.phone_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.phone_input, alignment=Qt.AlignCenter)

        # دکمه ارسال
        self.submit_btn = QPushButton("ادامه")
        self.submit_btn.setMinimumWidth(300)
        self.submit_btn.setMinimumHeight(45)
        submit_font = QFont()
        submit_font.setPointSize(12)
        submit_font.setBold(True)
        self.submit_btn.setFont(submit_font)
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #A62626;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #8B1F1F;
            }
            QPushButton:pressed {
                background-color: #6B1818;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        # وضعیت
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # فاصله اضافی
        layout.addSpacing(40)

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
        if loading:
            self.submit_btn.setText("در حال پردازش...")
        else:
            self.submit_btn.setText("ادامه")


# ---------------------------------------------------------------------------
# صفحه دوم: ورود کد تأیید
# ---------------------------------------------------------------------------
class CodePage(QWidget):
    """صفحه ورود کد تأیید ۶ رقمی."""

    submit_code = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        # عنوان
        title = QLabel("کد تأیید را وارد کنید")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # توضیح
        self.description = QLabel("کد ۶ رقمی ارسال شده به شماره ... را وارد کنید")
        self.description.setAlignment(Qt.AlignCenter)
        self.description.setStyleSheet("color: #666;")
        layout.addWidget(self.description)

        # فاصله
        layout.addSpacing(20)

        # فیلد کد
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("۱۲۳۴۵۶")
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMaxLength(6)
        code_font = QFont()
        code_font.setPointSize(24)
        code_font.setBold(True)
        self.code_input.setFont(code_font)
        self.code_input.setMinimumWidth(300)
        self.code_input.setStyleSheet("""
            QLineEdit {
                letter-spacing: 8px;
                padding: 15px;
            }
        """)
        self.code_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.code_input, alignment=Qt.AlignCenter)

        # دکمه ارسال
        self.submit_btn = QPushButton("ورود")
        self.submit_btn.setMinimumWidth(300)
        self.submit_btn.setMinimumHeight(45)
        submit_font = QFont()
        submit_font.setPointSize(12)
        submit_font.setBold(True)
        self.submit_btn.setFont(submit_font)
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #A62626;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
            }
            QPushButton:hover {
                background-color: #8B1F1F;
            }
            QPushButton:pressed {
                background-color: #6B1818;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        # وضعیت
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # فاصله اضافی
        layout.addSpacing(40)

    def set_phone(self, phone: str):
        self.description.setText(f"کد ۶ رقمی ارسال شده به شماره {phone} را وارد کنید")

    def _on_submit(self):
        code = self.code_input.text().strip()
        if len(code) != 6 or not code.isdigit():
            QMessageBox.warning(self, "خطا", "کد تأیید باید دقیقاً ۶ رقم باشد")
            return
        self.submit_code.emit(code)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_loading(self, loading: bool):
        self.submit_btn.setEnabled(not loading)
        self.code_input.setEnabled(not loading)
        if loading:
            self.submit_btn.setText("در حال ورود...")
        else:
            self.submit_btn.setText("ورود")

    def clear(self):
        self.code_input.clear()
        self.status_label.clear()


# ---------------------------------------------------------------------------
# پنجره اصلی Login
# ---------------------------------------------------------------------------
class LoginWindow(QMainWindow):
    """پنجره اصلی Login با دو صفحه."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Divar Manager - ورود")
        self.setMinimumSize(500, 600)
        self.resize(500, 600)

        self._current_worker: Optional[LoginWorker] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # Stacked widget برای جابجایی بین صفحات
        self.stack = QStackedWidget()
        self.phone_page = PhonePage()
        self.code_page = CodePage()

        self.stack.addWidget(self.phone_page)
        self.stack.addWidget(self.code_page)

        main_layout.addWidget(self.stack)

    def _connect_signals(self):
        self.phone_page.submit_phone.connect(self._on_phone_submitted)
        self.code_page.submit_code.connect(self._on_code_submitted)

    def _on_phone_submitted(self, phone: str):
        """کاربر شماره موبایل را وارد کرد."""
        self.phone_page.set_loading(True)
        self.phone_page.set_status("در حال ارسال شماره...")

        # ایجاد و شروع worker
        self._current_worker = LoginWorker(phone)
        self._current_worker.signals.code_needed.connect(self._on_code_needed)
        self._current_worker.signals.login_finished.connect(self._on_login_finished)
        self._current_worker.signals.error_occurred.connect(self._on_error)
        self._current_worker.signals.status_changed.connect(self._on_status_changed)

        QThreadPool.globalInstance().start(self._current_worker)

    @Slot(str)
    def _on_code_needed(self, phone: str):
        """Worker نیاز به کد تأیید دارد."""
        self.code_page.set_phone(phone)
        self.code_page.clear()
        self.stack.setCurrentWidget(self.code_page)
        self.code_page.code_input.setFocus()

    def _on_code_submitted(self, code: str):
        """کاربر کد تأیید را وارد کرد."""
        self.code_page.set_loading(True)
        self.code_page.set_status("در حال تأیید کد...")

        # ارسال کد به worker
        if self._current_worker:
            self._current_worker.provide_code(code)

    @Slot(object)
    def _on_login_finished(self, result: LoginResult):
        """فرآیند Login تمام شد."""
        if result.success:
            QMessageBox.information(
                self,
                "ورود موفق",
                f"✅ ورود با موفقیت انجام شد!\n\n"
                f"شماره: {result.phone}\n"
                f"Session ذخیره شد در:\n{result.session_path}",
            )
            self.close()
        else:
            QMessageBox.critical(
                self,
                "خطا در ورود",
                f"❌ ورود ناموفق بود\n\n"
                f"وضعیت: {result.state.value}\n"
                f"خطا: {result.error}",
            )
            # بازگشت به صفحه اول
            self.phone_page.set_loading(False)
            self.phone_page.set_status("")
            self.stack.setCurrentWidget(self.phone_page)

    @Slot(str)
    def _on_error(self, error_msg: str):
        """خطای غیرمنتظره."""
        QMessageBox.critical(self, "خطا", f"خطای غیرمنتظره:\n{error_msg}")
        self.phone_page.set_loading(False)
        self.phone_page.set_status("")

    @Slot(str)
    def _on_status_changed(self, status: str):
        """به‌روزرسانی وضعیت."""
        current = self.stack.currentWidget()
        if hasattr(current, "set_status"):
            current.set_status(status)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # استایل کلی
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QWidget {
            font-family: 'Segoe UI', 'Tahoma', sans-serif;
        }
        QLineEdit {
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 8px;
            background-color: white;
        }
        QLineEdit:focus {
            border: 2px solid #A62626;
        }
    """)

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
