"""
PlatformTab - تب عمومی برای Login هر پلتفرم.

تغییرات مهم:
- هیچ مرورگری در شروع برنامه باز نمی‌شود
- لیست شماره‌های ذخیره‌شده (Sessionها) نمایش داده می‌شود
- کاربر شماره را از لیست انتخاب می‌کند
- بررسی واقعی Session (باز کردن مرورگر) فقط با کلیک «بررسی Session»
- بدون timeout برای انتظار کد - کاربر تصمیم می‌گیرد
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from concurrent.futures import Future
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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


IDLE_TIMEOUT_SECONDS = 300  # 5 دقیقه

LoginManagerFactory = Callable

# ---------------------------------------------------------------------------
# بستن اجباری مرورگر (fallback)
# ---------------------------------------------------------------------------
def _force_close_all_browsers() -> None:
    """بستن BrowserService مشترک + تلاش برای بستن پروسه‌های chromium متعلق به Playwright."""
    # 1) BrowserService singleton (اگر وجود داشته باشد)
    try:
        from core.browser_service import BrowserService  # type: ignore
        svc = BrowserService.instance()
        if hasattr(svc, "request_close_all"):
            svc.request_close_all(timeout=10.0)
    except Exception:
        pass

    # 2) Kill chromium/chrome متعلق به playwright (ویندوز)
    if sys.platform.startswith("win"):
        # فقط پروسه‌هایی که مسیرشان شامل ms-playwright یا chromium باشد
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "  ($_.Name -match 'chrome|chromium') -and "
            "  ($_.CommandLine -match 'ms-playwright|playwright|chromium') "
            "} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
    else:
        # تلاش برای بستن تمام پروسه‌های مرتبط با Playwright و Chromium
        for pattern in ("ms-playwright", "chromium", "chrome", "playwright"):
            try:
                subprocess.run(
                    ["pkill", "-f", pattern],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass



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
# Worker برای بررسی Session (فقط وقتی کاربر درخواست دهد)
# ---------------------------------------------------------------------------
class SessionCheckWorker(QRunnable):
    """بررسی اعتبار یک Session مشخص در thread مجزا (باز کردن مرورگر)."""

    def __init__(self, platform: str, phone: Optional[str] = None):
        super().__init__()
        self.platform = platform
        self.phone = phone
        self.signals = LoginSignals()
        self.setAutoDelete(True)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._close_event: Optional[asyncio.Event] = None
        self._browser_manager = None

    def request_close(self):
        """قابل فراخوانی امن از GUI thread برای بستن دستی مرورگر."""
        if self._loop is not None and self._close_event is not None:
            self._loop.call_soon_threadsafe(self._close_event.set)
        # بستن اجباری BrowserManager اگر هنوز باز است
        if self._loop is not None and self._browser_manager is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), self._loop
                )
            except Exception:
                pass

    @Slot()
    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._close_event = asyncio.Event()
        try:
            async def _run():
                sm = SessionManager(platform=self.platform)
                record = sm.load(phone=self.phone) if self.phone else sm.load()
                if not record:
                    return None, "NO_SESSION"

                if record.status == SessionStatus.INVALID:
                    return record, "INVALID"

                self.signals.status_changed.emit(
                    f"در حال بررسی Session شماره {record.phone}..."
                )
                bm = BrowserManager(session_record=record)
                async with bm:
                    status = await sm.validate(record, bm.page)

                    is_sheypoor = "sheypoor" in (self.platform or "").lower()

                    if is_sheypoor:
                        try:
                            self.signals.status_changed.emit(
                                "در حال انتقال به صفحه آگهی‌های من در شیپور..."
                            )
                            await bm.page.goto(
                                "https://www.sheypoor.com/session/myAccount/myListings/all",
                                wait_until="domcontentloaded",
                                timeout=30000,
                            )
                        except Exception as nav_err:
                            self.signals.status_changed.emit(
                                f"⚠️ خطا در انتقال به صفحه آگهی‌ها: {nav_err}"
                            )

                    # مرورگر باز می‌ماند تا کاربر خودش آن را ببندد
                    self.signals.status_changed.emit(
                        "🟢 مرورگر باز است. هر وقت کارتان تمام شد، "
                        "پنجرهٔ مرورگر را ببندید تا برنامه ادامه یابد."
                    )
                    try:
                        await bm.page.wait_for_event("close", timeout=0)
                    except Exception:
                        pass

                if status == SessionStatus.VALID:
                    return record, "VALID"
                return record, status.value

            record, status_key = loop.run_until_complete(_run())
            msg = {
                "NO_SESSION": "هیچ Session ذخیره‌شده‌ای وجود ندارد",
                "VALID": f"Session معتبر است ({record.phone if record else ''})",
                "INVALID": "Session منقضی/نامعتبر - نیاز به Login مجدد",
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
        login_manager_factory: LoginManagerFactory,
    ):
        super().__init__()
        self.phone = phone
        self._platform_key = platform_key
        self._factory = login_manager_factory
        self.signals = LoginSignals()
        self._code_future: Optional[Future] = None
        self._cancelled = False
        self.setAutoDelete(True)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._browser_manager = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._browser_manager = None

    def provide_code(self, code: str):
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

    def cancel(self):
        self._cancelled = True
        if self._code_future and not self._code_future.done():
            self._code_future.cancel()

    def request_close(self):
        """لغو login + بستن مرورگر."""
        self.cancel()
        if self._loop is not None and self._browser_manager is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), self._loop
                )
                fut.result(timeout=8)
            except Exception:
                pass
        _force_close_all_browsers()

    async def _code_provider(self):
        self._code_future = Future()
        self.signals.code_needed.emit(self.phone)
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
        self._loop = loop
        try:
            async def _run():
                session_manager = SessionManager(platform=self._platform_key)
                browser_manager = BrowserManager()
                self._browser_manager = browser_manager

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
# صفحه وضعیت + لیست شماره‌ها
# ---------------------------------------------------------------------------
class _StatusPage(QWidget):
    """صفحه اول: لیست شماره‌ها + انتخاب + دکمه‌ها (بدون باز کردن خودکار مرورگر)."""

    start_login = Signal()
    check_session = Signal()
    logout = Signal()
    close_browser = Signal()
    select_session = Signal(object)  # SessionRecord or None
    refresh_list = Signal()

    def __init__(self, platform_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._sessions: List[SessionRecord] = []
        self._setup_ui(platform_name)

    def _setup_ui(self, platform_name: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel(f"{platform_name}")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # راهنما
        hint = QLabel(
            "شماره‌های ذخیره‌شده را از لیست انتخاب کنید.\n"
            "مرورگر فقط وقتی «بررسی Session» را بزنید باز می‌شود."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)

        # لیست شماره‌ها
        list_label = QLabel("📱 لیست شماره‌های وارد‌شده:")
        list_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(list_label)

        self.phone_list = QListWidget()
        self.phone_list.setMinimumHeight(160)
        self.phone_list.setMaximumHeight(220)
        self.phone_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.phone_list.setStyleSheet("""
            QListWidget {
                border: 2px solid #ddd;
                border-radius: 8px;
                background: white;
                font-size: 13px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #000;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        self.phone_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.phone_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.phone_list)

        # کادر وضعیت انتخاب
        self.status_box = QLabel("هیچ شماره‌ای انتخاب نشده است.")
        self.status_box.setAlignment(Qt.AlignCenter)
        self.status_box.setWordWrap(True)
        self.status_box.setMinimumHeight(70)
        self.status_box.setStyleSheet("""
            QLabel {
                background-color: #f8f9fa;
                border: 2px solid #ddd;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.status_box)

        # دکمه‌ها
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        row1 = QHBoxLayout()
        self.refresh_btn = QPushButton("🔃 تازه‌سازی لیست")
        self._style_button(self.refresh_btn, "#17a2b8", min_w=180)
        self.refresh_btn.clicked.connect(self.refresh_list.emit)
        row1.addWidget(self.refresh_btn)

        self.check_btn = QPushButton("🔄 بررسی Session (باز کردن مرورگر)")
        self._style_button(self.check_btn, "#6c757d", min_w=220)
        self.check_btn.clicked.connect(self.check_session.emit)
        self.check_btn.setEnabled(False)
        row1.addWidget(self.check_btn)
        btn_layout.addLayout(row1)


        self.close_browser_btn = QPushButton("🔴 بستن مرورگر")
        self._style_button(self.close_browser_btn, "#dc3545", min_w=400)
        self.close_browser_btn.clicked.connect(self.close_browser.emit)
        self.close_browser_btn.setVisible(True)
        btn_layout.addWidget(self.close_browser_btn)

        self.login_btn = QPushButton("🔐 ورود با شماره جدید")
        self._style_button(self.login_btn, self._color)
        self.login_btn.clicked.connect(self.start_login.emit)
        btn_layout.addWidget(self.login_btn)

        self.logout_btn = QPushButton("🚪 حذف Session انتخاب‌شده")
        self._style_button(self.logout_btn, "#e74c3c")
        self.logout_btn.clicked.connect(self.logout.emit)
        self.logout_btn.setEnabled(False)
        btn_layout.addWidget(self.logout_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _style_button(self, btn: QPushButton, color: str, min_w: int = 400):
        btn.setMinimumWidth(min_w)
        btn.setMinimumHeight(42)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        btn.setFont(font)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background-color: #ccc; color: #666; }}
        """)

    def set_sessions(self, sessions: List[SessionRecord], selected_phone: Optional[str] = None):
        """پر کردن لیست از روی Sessionهای دیتابیس (بدون مرورگر)."""
        self._sessions = list(sessions or [])
        self.phone_list.clear()

        if not self._sessions:
            item = QListWidgetItem("— هیچ شماره‌ای ذخیره نشده —")
            item.setFlags(Qt.NoItemFlags)
            self.phone_list.addItem(item)
            self.status_box.setText(
                "ℹ️ هیچ Session ذخیره‌شده‌ای وجود ندارد.\n"
                "با «ورود با شماره جدید» وارد شوید."
            )
            self._set_valid_style(False)
            self.check_btn.setEnabled(False)
            self.logout_btn.setEnabled(False)
            return

        select_row = 0
        for i, rec in enumerate(self._sessions):
            status = rec.status.value if rec.status else "unknown"
            last = ""
            if rec.last_used_at:
                try:
                    last = rec.last_used_at.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    last = str(rec.last_used_at)
            cookies = len(rec.storage_state.cookies) if rec.storage_state else 0
            text = f"{rec.phone}   |   وضعیت: {status}   |   کوکی: {cookies}"
            if last:
                text += f"   |   آخرین استفاده: {last}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, rec)
            self.phone_list.addItem(item)
            if selected_phone and rec.phone == selected_phone:
                select_row = i

        self.phone_list.setCurrentRow(select_row)
        self._on_selection_changed()

    def get_selected_record(self) -> Optional[SessionRecord]:
        item = self.phone_list.currentItem()
        if not item:
            return None
        rec = item.data(Qt.UserRole)
        return rec if isinstance(rec, SessionRecord) else None

    def _on_selection_changed(self):
        rec = self.get_selected_record()
        has = rec is not None
        self.check_btn.setEnabled(has)
        self.logout_btn.setEnabled(has)

        if not has:
            if self._sessions:
                self.status_box.setText("یک شماره از لیست انتخاب کنید.")
            return

        status = rec.status.value if rec.status else "unknown"
        last = rec.last_used_at or "نامشخص"
        cookies = len(rec.storage_state.cookies) if rec.storage_state else 0
        is_valid = rec.status == SessionStatus.VALID
        self.status_box.setText(
            f"شماره انتخاب‌شده: {rec.phone}\n"
            f"وضعیت ذخیره‌شده در DB: {status}\n"
            f"کوکی‌ها: {cookies} | آخرین استفاده: {last}\n"
            f"(این وضعیت از دیتابیس است — برای بررسی واقعی «بررسی Session» را بزنید)"
        )
        self._set_valid_style(is_valid)

        # انتخاب خودکار از لیست (بدون دکمه جداگانه)
        self.select_session.emit(rec)

    def _on_double_click(self, item: QListWidgetItem):
        # دابل‌کلیک هم همان انتخاب را دوباره تأیید می‌کند
        rec = item.data(Qt.UserRole) if item else None
        if rec:
            self.select_session.emit(rec)

    def _set_valid_style(self, is_valid: bool):
        if is_valid:
            self.status_box.setStyleSheet("""
                QLabel {
                    background-color: #d4edda;
                    border: 2px solid #28a745;
                    border-radius: 8px;
                    padding: 12px;
                    font-size: 12px;
                    color: #155724;
                }
            """)
        else:
            self.status_box.setStyleSheet("""
                QLabel {
                    background-color: #f8f9fa;
                    border: 2px solid #ddd;
                    border-radius: 8px;
                    padding: 12px;
                    font-size: 12px;
                }
            """)

    def set_status(self, text: str, is_valid: bool = False):
        self.status_box.setText(text)
        self._set_valid_style(is_valid)

    def set_loading(self, loading: bool):
        self.check_btn.setEnabled(not loading and self.get_selected_record() is not None)
        self.login_btn.setEnabled(not loading)
        self.refresh_btn.setEnabled(not loading)
        self.logout_btn.setEnabled(not loading and self.get_selected_record() is not None)
        if loading:
            self.check_btn.setText("⏳ در حال بررسی...")
        else:
            self.check_btn.setText("🔄 بررسی Session (باز کردن مرورگر)")


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

        self.close_browser_btn = QPushButton("🔴 بستن مرورگر")
        self.close_browser_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.close_browser_btn.setMinimumWidth(350)
        self.close_browser_btn.setMinimumHeight(40)
        self.close_browser_btn.clicked.connect(self.cancel_login.emit)
        layout.addWidget(self.close_browser_btn, alignment=Qt.AlignCenter)


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

    PAGE_STATUS = 0
    PAGE_PHONE = 1
    PAGE_CODE = 2

    def __init__(
        self,
        platform_name: str,
        platform_key: str,
        color: str,
        code_length: int,
        login_manager_factory: LoginManagerFactory,
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

        # فقط لیست از DB — بدون باز کردن مرورگر
        self._reload_session_list()

    def _setup_ui(self, color: str, code_length: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)

        self.stack = QStackedWidget()

        self.status_page = _StatusPage(self._platform_name, color)
        self.phone_page = _PhonePage(self._platform_name, color)
        self.code_page = _CodePage(self._platform_name, color, code_length)

        self.stack.addWidget(self.status_page)   # 0
        self.stack.addWidget(self.phone_page)    # 1
        self.stack.addWidget(self.code_page)     # 2

        layout.addWidget(self.stack)

    def _connect_signals(self):
        self.status_page.start_login.connect(self._on_start_login)
        self.status_page.check_session.connect(self._check_session)
        self.status_page.logout.connect(self._on_logout)
        self.status_page.close_browser.connect(self._on_close_browser_clicked)
        self.status_page.select_session.connect(self._on_select_session)
        self.status_page.refresh_list.connect(self._reload_session_list)

        self.phone_page.submit_phone.connect(self._on_phone_submitted)
        self.phone_page.go_back.connect(self._go_to_status)

        self.code_page.submit_code.connect(self._on_code_submitted)
        self.code_page.cancel_login.connect(self._on_cancel_login)

    def _log(self, level: str, msg: str):
        self.log_message.emit(level, msg)

    # ------------------------------------------------------------------
    # لیست Sessionها از DB (بدون مرورگر)
    # ------------------------------------------------------------------
    def _reload_session_list(self):
        """بارگذاری لیست شماره‌ها از SQLite — بدون Playwright."""
        try:
            sm = SessionManager(platform=self._platform_key)
            sessions = sm.list_sessions()
            selected = self._current_session.phone if self._current_session else None
            self.status_page.set_sessions(sessions, selected_phone=selected)
            self._log(
                "INFO",
                f"[{self._platform_name}] Loaded {len(sessions)} session(s) from DB (no browser)",
            )
            if not sessions:
                self._current_session = None
            elif self._current_session:
                # همگام‌سازی آبجکت جاری
                for s in sessions:
                    if s.phone == self._current_session.phone:
                        self._current_session = s
                        break
        except Exception as e:
            self.status_page.set_status(f"❌ خطا در خواندن Sessionها:\n{e}")
            self._log("ERROR", f"[{self._platform_name}] list sessions error: {e}")

    @Slot(object)
    def _on_select_session(self, record: SessionRecord):
        """انتخاب شماره از لیست."""
        self._current_session = record
        self.status_page.set_status(
            f"✅ شماره انتخاب شد: {record.phone}\n\n"
            f"وضعیت DB: {record.status.value}\n"
            f"کوکی‌ها: {len(record.storage_state.cookies) if record.storage_state else 0}\n\n"
            f"برای اعتبارسنجی واقعی، «بررسی Session» را بزنید (مرورگر باز می‌شود).",
            is_valid=(record.status == SessionStatus.VALID),
        )
        self._log("INFO", f"[{self._platform_name}] Selected session phone={record.phone}")

    # ------------------------------------------------------------------
    # Session Checking (فقط با کلیک کاربر — مرورگر باز می‌شود)
    # ------------------------------------------------------------------
    def _check_session(self):
        """بررسی واقعی Session انتخاب‌شده با باز کردن مرورگر."""
        rec = self.status_page.get_selected_record()
        if not rec:
            QMessageBox.information(
                self,
                "انتخاب شماره",
                "ابتدا یک شماره از لیست انتخاب کنید.",
            )
            return

        self.status_page.set_loading(True)
        self.status_page.set_status(
            f"⏳ در حال بررسی Session شماره {rec.phone}...\n(مرورگر باز می‌شود)"
        )
        self._log(
            "INFO",
            f"[{self._platform_name}] Validating session phone={rec.phone} (browser will open)",
        )

        worker = SessionCheckWorker(self._platform_key, phone=rec.phone)
        worker.signals.session_status.connect(self._on_session_checked)
        worker.signals.error_occurred.connect(self._on_session_check_error)
        worker.signals.status_changed.connect(self._on_status_changed)
        self._current_check_worker = worker
        QThreadPool.globalInstance().start(worker)

    @Slot(str, str)
    def _on_session_checked(self, status_key: str, message: str):
        self.status_page.set_loading(False)
        self._current_check_worker = None
        self._log("INFO", f"[{self._platform_name}] Session check: {status_key} - {message}")

        # بعد از بررسی، لیست را تازه کن
        sm = SessionManager(platform=self._platform_key)
        rec = self.status_page.get_selected_record()
        phone = rec.phone if rec else None
        record = sm.load(phone=phone) if phone else sm.load()

        if status_key == "VALID" and record:
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
                f"[{self._platform_name}] Session ready: {record.phone}",
            )
        elif status_key == "NO_SESSION":
            self._current_session = None
            self.status_page.set_status(
                "ℹ️ هیچ Session ذخیره‌شده‌ای وجود ندارد.\n\n"
                "برای استفاده، با «ورود با شماره جدید» وارد شوید."
            )
        elif status_key in ("INVALID", "EXPIRED"):
            self.status_page.set_status(
                f"⚠️ {message}\n\nلطفاً مجدداً وارد حساب کاربری شوید."
            )
        else:
            self.status_page.set_status(f"❓ {message}")

        self._reload_session_list()

    @Slot(str)
    def _on_session_check_error(self, error: str):
        self.status_page.set_loading(False)
        self.status_page.set_status(f"❌ خطا در بررسی Session:\n{error}")
        self._log("ERROR", f"[{self._platform_name}] Session check error: {error}")

    # ------------------------------------------------------------------
    # Login Flow
    # ------------------------------------------------------------------
    def _on_start_login(self):
        self.phone_page.reset()
        self.stack.setCurrentIndex(self.PAGE_PHONE)
        self.phone_page.phone_input.setFocus()

    def _go_to_status(self):
        self.stack.setCurrentIndex(self.PAGE_STATUS)
        self._reload_session_list()  # بدون مرورگر

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
        self._log("INFO", f"[{self._platform_name}] Login cancelled / close browser by user")
        if self._current_worker:
            if hasattr(self._current_worker, "request_close"):
                self._current_worker.request_close()
            else:
                self._current_worker.cancel()
            self._current_worker = None
        _force_close_all_browsers()
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
            # بعد از لاگین موفق، این شماره را current کن
            sm = SessionManager(platform=self._platform_key)
            self._current_session = sm.load(phone=getattr(result, "phone", None))
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
        elif idx == self.PAGE_STATUS:
            # پیام موقت در حین بررسی
            self.status_page.set_status(status)

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def _on_close_browser_clicked(self):
        """بستن دستی مرورگر توسط کاربر از طریق GUI."""
        closed_any = False
        if getattr(self, "_current_check_worker", None):
            try:
                self._current_check_worker.request_close()
                closed_any = True
            except Exception:
                pass
        if getattr(self, "_current_worker", None):
            try:
                if hasattr(self._current_worker, "request_close"):
                    self._current_worker.request_close()
                else:
                    self._current_worker.cancel()
                closed_any = True
            except Exception:
                pass
        _force_close_all_browsers()
        self.status_page.set_loading(False)
        if hasattr(self.status_page, "set_status"):
            self.status_page.set_status("🔴 درخواست بستن مرورگر ارسال شد.")
        self._log(
            "INFO",
            f"[{self._platform_name}] کاربر درخواست بستن مرورگر داد (closed_any={closed_any})",
        )

    def _on_logout(self):
        rec = self.status_page.get_selected_record()
        if not rec:
            QMessageBox.information(self, "حذف", "ابتدا یک شماره از لیست انتخاب کنید.")
            return

        reply = QMessageBox.question(
            self,
            "تأیید خروج",
            f"آیا از حذف Session برای شماره {rec.phone} مطمئن هستید؟\n\n"
            f"پس از این کار، باید دوباره وارد شوید.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            sm = SessionManager(platform=self._platform_key)
            sm.delete(rec)
            self._log(
                "INFO",
                f"[{self._platform_name}] Session deleted for {rec.phone}",
            )
            if self._current_session and self._current_session.phone == rec.phone:
                self._current_session = None
            self._reload_session_list()
