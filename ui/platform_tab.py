"""
PlatformTab - تب عمومی برای Login هر پلتفرم (دیوار / شیپور).

ویژگی‌ها:
- مدیریت ورود به حساب و نمایش لیست شماره‌ها
- چیدمان منظم دکمه‌ها بدون روی هم افتادن
- کنترل هوشمند مرورگر به تفکیک تب
- نمایش فارسی دقیق وضعیت حساب‌ها و تعداد کوکی‌های فعال
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.browser_manager import BrowserManager
from core.session_manager import SessionManager
from core.session_models import SessionRecord, SessionStatus
from playwright.async_api import Error as PlaywrightError

IDLE_TIMEOUT_SECONDS = 300
OTP_WAIT_TIMEOUT_SECONDS = 300

LoginManagerFactory = Callable


def format_status_persian(status_str: str) -> str:
    """تبدیل وضعیت انگلیسی به برچسب فارسی زیبا با آیکون."""
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


# ---------------------------------------------------------------------------
# بستن اجباری مرورگر (fallback سراسری)
# ---------------------------------------------------------------------------
def _force_close_all_browsers() -> None:
    try:
        from core.browser_service import BrowserService
        svc = BrowserService.instance()
        if hasattr(svc, "request_close_all"):
            svc.request_close_all(timeout=10.0)
    except Exception:
        pass

    if sys.platform.startswith("win"):
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


# ---------------------------------------------------------------------------
# سیگنال‌ها
# ---------------------------------------------------------------------------
class LoginSignals(QObject):
    code_needed = Signal(str)
    login_finished = Signal(object)
    error_occurred = Signal(str)
    status_changed = Signal(str)
    session_status = Signal(str, str)


# ---------------------------------------------------------------------------
# Worker برای بررسی Session دستی
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
        self._browser_manager: Optional[BrowserManager] = None
        self._is_active = True

    def is_browser_running(self) -> bool:
        if not self._is_active:
            return False
        if self._browser_manager is not None:
            return self._browser_manager.is_running
        return True

    def request_close(self):
        if self._loop is not None and self._close_event is not None:
            self._loop.call_soon_threadsafe(self._close_event.set)
        if self._loop is not None and self._browser_manager is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), self._loop
                )
            except Exception:
                pass

    @Slot()
    def run(self):
        self._is_active = True
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

                self.signals.status_changed.emit(
                    f"در حال بررسی Session شماره {record.phone}..."
                )
                bm = BrowserManager(session_record=record)
                self._browser_manager = bm
                async with bm:
                    try:
                        from core.token_refresher import TokenRefresher
                        refresher = TokenRefresher(sm)
                        token_valid = await refresher.ensure_valid_token(
                            page=bm.page,
                            context=bm.context,
                            record=record,
                        )
                        if not token_valid:
                            self.signals.status_changed.emit(
                                "⚠️ Token منقضی شده و refresh ناموفق بود"
                            )
                    except ImportError:
                        pass
                    except Exception as e:
                        self.signals.status_changed.emit(
                            f"⚠️ خطا در بررسی token: {e}"
                        )

                    status = await sm.validate(record, bm.page)

                    status_key = status.value.upper()
                    msg = {
                        "VALID": f"Session معتبر است ({record.phone})",
                        "INVALID": "Session منقضی/نامعتبر - نیاز به Login مجدد",
                        "EXPIRED": "Session منقضی شده",
                        "UNKNOWN": "وضعیت Session قابل تشخیص نیست",
                    }.get(status_key, status_key)
                    self.signals.session_status.emit(status_key, msg)

                    destinations = {
                        "sheypoor": "https://www.sheypoor.com/session/myAccount/myListings/all",
                        "divar": "https://divar.ir/s/iran",
                    }
                    destination = destinations.get(self.platform.lower())
                    if status == SessionStatus.VALID and destination:
                        try:
                            label = "آگهی‌های من در شیپور" if self.platform.lower() == "sheypoor" else "آگهی‌های سراسر ایران در دیوار"
                            self.signals.status_changed.emit(f"در حال انتقال به صفحه {label}...")
                            await bm.page.goto(destination, wait_until="domcontentloaded", timeout=30_000)
                            await sm.save_from_context(bm.context, record.phone, metadata=record.metadata)
                        except Exception as nav_err:
                            self.signals.status_changed.emit(f"⚠️ خطا در انتقال/ذخیره Session: {nav_err}")

                    self.signals.status_changed.emit(
                        "🟢 مرورگر باز است. هر وقت کارتان تمام شد، "
                        "پنجرهٔ مرورگر را ببندید تا برنامه ادامه یابد."
                    )
                    try:
                        await bm.page.wait_for_event("close", timeout=0)
                    except (PlaywrightError, Exception):
                        pass

                return record, status.value

            record, status_key = loop.run_until_complete(_run())
            msg = {
                "NO_SESSION": "هیچ Session ذخیره‌شده‌ای وجود ندارد",
                "VALID": f"Session معتبر است ({record.phone if record else ''})",
                "INVALID": "Session منقضی/نامعتبر - نیاز به Login مجدد",
                "EXPIRED": "Session منقضی شده",
                "UNKNOWN": "وضعیت Session قابل تشخیص نیست",
            }.get(status_key.upper(), status_key)

            self.signals.session_status.emit(status_key.upper(), msg)

        except Exception as e:
            self.signals.error_occurred.emit(f"خطا در بررسی Session: {e}")
        finally:
            self._is_active = False
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
        self._code_future: Optional[asyncio.Future] = None
        self._cancelled = False
        self.setAutoDelete(True)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._browser_manager: Optional[BrowserManager] = None
        self._is_active = True

    def is_browser_running(self) -> bool:
        if not self._is_active:
            return False
        if self._browser_manager is not None:
            return self._browser_manager.is_running
        return True

    def _resolve_code(self, code: str) -> None:
        if self._code_future and not self._code_future.done():
            self._code_future.set_result(code)

    def provide_code(self, code: str):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._resolve_code, code)

    def _cancel_code(self) -> None:
        if self._code_future and not self._code_future.done():
            self._code_future.cancel()

    def cancel(self):
        self._cancelled = True
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._cancel_code)

    def request_close(self):
        self.cancel()
        if self._loop is not None and self._browser_manager is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._browser_manager.stop(), self._loop
                )
            except Exception:
                pass

    async def _code_provider(self):
        self._code_future = asyncio.get_running_loop().create_future()
        self.signals.code_needed.emit(self.phone)
        try:
            code = await asyncio.wait_for(self._code_future, timeout=OTP_WAIT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("زمان انتظار برای کد تأیید پس از ۵ دقیقه تمام شد.") from exc
        if self._cancelled:
            raise asyncio.CancelledError("Login cancelled by user")
        return code

    @Slot()
    def run(self):
        self._is_active = True
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
                    result = await login_manager.login(self.phone)

                    if result.success:
                        self.signals.status_changed.emit(
                            "✅ ورود موفق! مرورگر باز است.\n"
                            "هر وقت کارتان تمام شد، پنجره مرورگر را ببندید."
                        )
                        try:
                            await browser_manager.page.wait_for_event("close", timeout=0)
                        except Exception:
                            pass

                    return result

            result = loop.run_until_complete(_run())
            self.signals.login_finished.emit(result)
        except asyncio.CancelledError:
            self.signals.status_changed.emit("Login لغو شد")
        except Exception as e:
            self.signals.error_occurred.emit(f"{type(e).__name__}: {e}")
        finally:
            self._is_active = False
            loop.close()


# ---------------------------------------------------------------------------
# PlatformTab
# ---------------------------------------------------------------------------
class PlatformTab(QWidget):
    """تب عمومی Login برای یک پلتفرم (دیوار / شیپور)."""

    log_message = Signal(str, str)

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
        self._current_check_worker: Optional[SessionCheckWorker] = None
        self._current_session: Optional[SessionRecord] = None

        self._setup_ui(color, code_length)
        self._connect_signals()
        self._reload_session_list()

    def _setup_ui(self, color: str, code_length: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 20)

        self.stack = QStackedWidget()

        self.status_page = _StatusPage(self._platform_name, color)
        self.phone_page = _PhonePage(self._platform_name, color)
        self.code_page = _CodePage(self._platform_name, color, code_length)

        self.stack.addWidget(self.status_page)
        self.stack.addWidget(self.phone_page)
        self.stack.addWidget(self.code_page)

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

    def restyle(self):
        widgets = [
            getattr(self.status_page, "phone_list", None),
            getattr(self.status_page, "status_box", None),
            getattr(self.phone_page, "phone_input", None),
            getattr(self.code_page, "code_input", None),
        ]
        for w in widgets:
            if w is None:
                continue
            try:
                w.style().unpolish(w)
                w.style().polish(w)
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.status_page.reflow(self.width())
        except Exception:
            pass

    def is_browser_open(self) -> bool:
        if self._current_check_worker and self._current_check_worker.is_browser_running():
            return True
        if self._current_worker and self._current_worker.is_browser_running():
            return True
        return False

    def _reload_session_list(self):
        try:
            sm = SessionManager(platform=self._platform_key)
            sessions = sm.list_sessions()
            selected = self._current_session.phone if self._current_session else None
            self.status_page.set_sessions(sessions, selected_phone=selected)
            self._log(
                "INFO",
                f"[{self._platform_name}] Loaded {len(sessions)} session(s) from DB",
            )
            if not sessions:
                self._current_session = None
            elif self._current_session:
                for s in sessions:
                    if s.phone == self._current_session.phone:
                        self._current_session = s
                        break
        except Exception as e:
            self.status_page.set_status(f"❌ خطا در خواندن Sessionها:\n{e}")
            self._log("ERROR", f"[{self._platform_name}] list sessions error: {e}")

    def _on_select_session(self, record: SessionRecord):
        self._current_session = record
        status_persian = format_status_persian(record.status.value if record.status else "unknown")
        cookies = len(record.storage_state.cookies) if (record.storage_state and record.storage_state.cookies) else 0
        last = record.last_used_at.strftime("%Y-%m-%d %H:%M") if record.last_used_at else "نامشخص"

        self.status_page.set_status(
            f"📱 شماره انتخاب‌شده: {record.phone}\n\n"
            f"📊 وضعیت حساب در DB: {status_persian}\n"
            f"🍪 کوکی‌های فعال: {cookies} عدد  |  🕒 آخرین استفاده: {last}\n\n"
            f"💡 برای اعتبارسنجی واقعی زنده روی سایت، دکمه «بررسی Session» را بزنید.",
            is_valid=(record.status == SessionStatus.VALID),
        )
        self._log("INFO", f"[{self._platform_name}] Selected session phone={record.phone}")

    def _check_session(self):
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

    def _on_session_checked(self, status_key: str, message: str):
        sm = SessionManager(platform=self._platform_key)
        rec = self.status_page.get_selected_record()
        phone = rec.phone if rec else None
        record = sm.load(phone=phone) if phone else sm.load()

        status_key_upper = status_key.upper()
        if status_key_upper == "VALID" and record:
            self._current_session = record
            cookies = len(record.storage_state.cookies) if (record.storage_state and record.storage_state.cookies) else 0
            last = record.last_used_at.strftime("%Y-%m-%d %H:%M") if record.last_used_at else "نامشخص"
            self.status_page.set_status(
                f"✅ Session معتبر و آماده استفاده است\n\n"
                f"📱 شماره: {record.phone}\n"
                f"🍪 تعداد کوکی‌ها: {cookies}\n"
                f"🕒 آخرین استفاده: {last}",
                is_valid=True,
            )
            self._log("INFO", f"[{self._platform_name}] Session ready: {record.phone}")
        elif status_key_upper == "NO_SESSION":
            self._current_session = None
            self.status_page.set_status(
                "ℹ️ هیچ Session ذخیره‌شده‌ای وجود ندارد.\n\n"
                "برای استفاده، با «ورود با شماره جدید» وارد شوید."
            )
        elif status_key_upper in ("INVALID", "EXPIRED"):
            self.status_page.set_status(
                f"⚠️ {message}\n\nلطفاً مجدداً وارد حساب کاربری شوید."
            )
        else:
            self.status_page.set_status(f"❓ {message}")

        self._reload_session_list()

    def _on_session_check_error(self, error: str):
        self.status_page.set_loading(False)
        self.status_page.set_status(f"❌ خطا در بررسی Session:\n{error}")
        self._log("ERROR", f"[{self._platform_name}] Session check error: {error}")

    def _on_start_login(self):
        self.phone_page.reset()
        self.stack.setCurrentIndex(self.PAGE_PHONE)
        self.phone_page.phone_input.setFocus()

    def _go_to_status(self):
        self.stack.setCurrentIndex(self.PAGE_STATUS)
        self._reload_session_list()

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
            try:
                if hasattr(self._current_worker, "request_close"):
                    self._current_worker.request_close()
                else:
                    self._current_worker.cancel()
            except Exception as e:
                self._log("WARNING", f"[{self._platform_name}] Error closing worker: {e}")

        QTimer.singleShot(500, self._go_to_status)
        self._log("INFO", f"[{self._platform_name}] Login cancelled successfully")

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

    def _on_status_changed(self, status: str):
        self._log("INFO", f"[{self._platform_name}] {status}")
        idx = self.stack.currentIndex()
        if idx == self.PAGE_PHONE:
            self.phone_page.set_status(status)
        elif idx == self.PAGE_CODE:
            self.code_page.set_status(status)
        elif idx == self.PAGE_STATUS:
            self.status_page.set_status(status)

    def _on_close_browser_clicked(self):
        if not self.is_browser_open():
            QMessageBox.information(
                self,
                "بستن مرورگر",
                f"ℹ️ هیچ مرورگری برای تب «{self._platform_name}» باز نیست.",
            )
            self.status_page.set_status(f"ℹ️ مرورگری برای «{self._platform_name}» باز نیست.")
            self._log("INFO", f"[{self._platform_name}] درخواست بستن مرورگر رد شد (مرورگری باز نیست)")
            return

        closed_any = False
        if self._current_check_worker and self._current_check_worker.is_browser_running():
            try:
                self._current_check_worker.request_close()
                closed_any = True
            except Exception as e:
                self._log("WARNING", f"[{self._platform_name}] Error closing check worker: {e}")

        if self._current_worker and self._current_worker.is_browser_running():
            try:
                if hasattr(self._current_worker, "request_close"):
                    self._current_worker.request_close()
                else:
                    self._current_worker.cancel()
                closed_any = True
            except Exception as e:
                self._log("WARNING", f"[{self._platform_name}] Error closing login worker: {e}")

        self.status_page.set_loading(False)
        self.status_page.set_status(f"🔴 مرورگر اختصاصی تب «{self._platform_name}» بسته شد.")
        self._log(
            "INFO",
            f"[{self._platform_name}] مرورگر اختصاصی این تب بسته شد (closed_any={closed_any})",
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


# ---------------------------------------------------------------------------
# صفحه وضعیت + لیست شماره‌ها
# ---------------------------------------------------------------------------
class _StatusPage(QWidget):
    """صفحه اول: لیست شماره‌ها + انتخاب + دکمه‌ها."""

    start_login = Signal()
    check_session = Signal()
    logout = Signal()
    close_browser = Signal()
    select_session = Signal(object)
    refresh_list = Signal()

    def __init__(self, platform_name: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._sessions: List[SessionRecord] = []
        self._setup_ui(platform_name)

    def _setup_ui(self, platform_name: str):
        self._primary_obj_name = (
            "primaryDivar" if self._color.upper() == "#A62626" else "primarySheypoor"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 20)

        container = QWidget()
        container.setMaximumWidth(1300)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        clayout = QVBoxLayout(container)
        clayout.setSpacing(14)
        clayout.setContentsMargins(0, 0, 0, 0)

        # --- عنوان و توضیح ---
        title = QLabel(f"{platform_name}")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        clayout.addWidget(title)

        hint = QLabel(
            "شماره‌های ذخیره‌شده را انتخاب کنید. مرورگر فقط وقتی «بررسی Session» را بزنید باز می‌شود."
        )
        hint.setObjectName("subtitleLabel")
        hint.setWordWrap(True)
        clayout.addWidget(hint)

        # --- کارت: لیست شماره‌ها ---
        list_card = QFrame()
        list_card.setObjectName("card")
        list_card_layout = QVBoxLayout(list_card)
        list_card_layout.setContentsMargins(18, 14, 18, 16)
        list_card_layout.setSpacing(10)

        list_label = QLabel("📱 لیست شماره‌های وارد‌شده")
        list_label.setObjectName("subtitleLabel")
        list_font = QFont()
        list_font.setBold(True)
        list_label.setFont(list_font)
        list_card_layout.addWidget(list_label)

        self.phone_list = QListWidget()
        self.phone_list.setMinimumHeight(180)
        self.phone_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.phone_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.phone_list.itemDoubleClicked.connect(self._on_double_click)
        list_card_layout.addWidget(self.phone_list, stretch=1)

        clayout.addWidget(list_card, stretch=1)

        # --- جعبهٔ وضعیت ---
        self.status_box = QLabel("هیچ شماره‌ای انتخاب نشده است.")
        self.status_box.setObjectName("statusBox")
        self.status_box.setAlignment(Qt.AlignCenter)
        self.status_box.setWordWrap(True)
        self.status_box.setMinimumHeight(78)
        clayout.addWidget(self.status_box)

        # --- کارت: عملیات و دکمه‌ها ---
        actions_card = QFrame()
        actions_card.setObjectName("card")
        actions_layout = QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(18, 16, 18, 16)
        actions_layout.setSpacing(10)

        self.login_btn = QPushButton("🔐 ورود با شماره جدید")
        self._style_button(self.login_btn, self._primary_obj_name)
        self.login_btn.setToolTip("ورود حساب جدید با دریافت کد SMS")
        self.login_btn.clicked.connect(self.start_login.emit)
        actions_layout.addWidget(self.login_btn)

        grid = QGridLayout()
        grid.setSpacing(10)

        self.check_btn = QPushButton("🔄 بررسی Session")
        self._style_button(self.check_btn, "ghostBtn")
        self.check_btn.setToolTip("باز کردن مرورگر برای بررسی زنده روی سایت")
        self.check_btn.clicked.connect(self.check_session.emit)
        self.check_btn.setEnabled(False)

        self.refresh_btn = QPushButton("🔃 تازه‌سازی لیست")
        self._style_button(self.refresh_btn, "ghostBtn")
        self.refresh_btn.setToolTip("به‌روزرسانی لیست شماره‌ها از دیتابیس")
        self.refresh_btn.clicked.connect(self.refresh_list.emit)

        self.close_browser_btn = QPushButton("🔴 بستن مرورگر")
        self._style_button(self.close_browser_btn, "dangerBtn")
        self.close_browser_btn.setToolTip("بستن مرورگر اختصاصی این تب")
        self.close_browser_btn.clicked.connect(self.close_browser.emit)

        self.logout_btn = QPushButton("🚪 حذف Session")
        self._style_button(self.logout_btn, "dangerBtn")
        self.logout_btn.setToolTip("حذف شماره و Session انتخاب‌شده")
        self.logout_btn.clicked.connect(self.logout.emit)
        self.logout_btn.setEnabled(False)

        grid.addWidget(self.check_btn, 0, 0)
        grid.addWidget(self.refresh_btn, 0, 1)
        grid.addWidget(self.close_browser_btn, 1, 0)
        grid.addWidget(self.logout_btn, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        actions_layout.addLayout(grid)

        self._actions_grid = grid
        self._action_buttons = [
            self.check_btn, self.refresh_btn, self.close_browser_btn, self.logout_btn,
        ]
        self._actions_narrow = False

        clayout.addWidget(actions_card)

        outer_h = QHBoxLayout()
        outer_h.addStretch(1)
        outer_h.addWidget(container, stretch=100)
        outer_h.addStretch(1)
        outer.addLayout(outer_h, stretch=1)

    def _style_button(self, btn: QPushButton, object_name: str, min_w: int = 0):
        if min_w:
            btn.setMinimumWidth(min_w)
        btn.setMinimumHeight(42)
        btn.setObjectName(object_name)
        btn.setCursor(Qt.PointingHandCursor)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        btn.setFont(font)

    def reflow(self, width: int):
        narrow = width < 560
        if narrow == self._actions_narrow:
            return
        self._actions_narrow = narrow

        while self._actions_grid.count() > 0:
            item = self._actions_grid.takeAt(0)
            w = item.widget()
            if w:
                self._actions_grid.removeWidget(w)

        if narrow:
            positions = [(0, 0), (1, 0), (2, 0), (3, 0)]
        else:
            positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

        for btn, (r, cpos) in zip(self._action_buttons, positions):
            self._actions_grid.addWidget(btn, r, cpos)

        self._actions_grid.setColumnStretch(0, 1)
        self._actions_grid.setColumnStretch(1, 0 if narrow else 1)

    def set_sessions(self, sessions: List[SessionRecord], selected_phone: Optional[str] = None):
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
            status_text = format_status_persian(rec.status.value if rec.status else "unknown")
            last = ""
            if rec.last_used_at:
                try:
                    last = rec.last_used_at.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    last = str(rec.last_used_at)
            cookies = len(rec.storage_state.cookies) if (rec.storage_state and rec.storage_state.cookies) else 0
            text = f"{rec.phone}  |  وضعیت: {status_text}  |  {cookies} کوکی"
            if last:
                text += f"  |  آخرین استفاده: {last}"
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

        status_text = format_status_persian(rec.status.value if rec.status else "unknown")
        last = rec.last_used_at.strftime("%Y-%m-%d %H:%M") if rec.last_used_at else "نامشخص"
        cookies = len(rec.storage_state.cookies) if (rec.storage_state and rec.storage_state.cookies) else 0
        is_valid = (rec.status == SessionStatus.VALID)
        self.status_box.setText(
            f"📱 شماره انتخاب‌شده: {rec.phone}\n"
            f"📊 وضعیت ذخیره‌شده در DB: {status_text}\n"
            f"🍪 کوکی‌های فعال: {cookies} عدد  |  🕒 آخرین استفاده: {last}\n\n"
            f"💡 برای اعتبارسنجی زنده روی سایت، دکمه «بررسی Session» را بزنید."
        )
        self._set_valid_style(is_valid)
        self.select_session.emit(rec)

    def _on_double_click(self, item: QListWidgetItem):
        rec = item.data(Qt.UserRole) if item else None
        if rec:
            self.select_session.emit(rec)

    def _set_valid_style(self, is_valid: bool):
        self.status_box.setObjectName("statusBoxValid" if is_valid else "statusBox")
        self.status_box.style().unpolish(self.status_box)
        self.status_box.style().polish(self.status_box)

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
        self._primary_obj_name = (
            "primaryDivar" if self._color.upper() == "#A62626" else "primarySheypoor"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"ورود به {platform_name}")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = QLabel("لطفاً شماره موبایل خود را وارد کنید")
        description.setObjectName("subtitleLabel")
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        layout.addSpacing(20)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09121234567")
        self.phone_input.setAlignment(Qt.AlignCenter)
        phone_font = QFont()
        phone_font.setPointSize(15)
        self.phone_input.setFont(phone_font)
        self.phone_input.setMinimumWidth(260)
        self.phone_input.setMaximumWidth(520)
        self.phone_input.setMinimumHeight(50)
        self.phone_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.phone_input, alignment=Qt.AlignCenter)

        self.submit_btn = QPushButton("ادامه")
        self._style_button(self.submit_btn, self._primary_obj_name)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        self.back_btn = QPushButton("← بازگشت")
        self.back_btn.setObjectName("linkBtn")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back.emit)
        layout.addWidget(self.back_btn, alignment=Qt.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(450)
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        layout.addSpacing(20)

    def _style_button(self, btn: QPushButton, object_name: str):
        btn.setMinimumWidth(260)
        btn.setMaximumWidth(520)
        btn.setMinimumHeight(50)
        btn.setObjectName(object_name)
        btn.setCursor(Qt.PointingHandCursor)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        btn.setFont(font)

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
        self._primary_obj_name = (
            "primaryDivar" if self._color.upper() == "#A62626" else "primarySheypoor"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(f"کد تأیید {platform_name}")
        title.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.description = QLabel(f"کد {self._code_length} رقمی ارسال شده را وارد کنید")
        self.description.setObjectName("subtitleLabel")
        self.description.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.description)

        hint = QLabel("💡 هر زمان خواستید می‌توانید مرورگر را ببندید و دوباره تلاش کنید")
        hint.setObjectName("hintLabel")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        hint.setMaximumWidth(400)
        layout.addWidget(hint, alignment=Qt.AlignCenter)

        layout.addSpacing(10)

        self.code_input = QLineEdit()
        self.code_input.setObjectName("codeInput")
        self.code_input.setPlaceholderText("۰" * self._code_length)
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setMaxLength(self._code_length)
        code_font = QFont()
        code_font.setPointSize(24)
        code_font.setBold(True)
        self.code_input.setFont(code_font)
        self.code_input.setMinimumWidth(260)
        self.code_input.setMaximumWidth(520)
        self.code_input.setMinimumHeight(56)
        self.code_input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.code_input, alignment=Qt.AlignCenter)

        self.submit_btn = QPushButton("ورود")
        self._style_button(self.submit_btn, self._primary_obj_name)
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn, alignment=Qt.AlignCenter)

        self.close_browser_btn = QPushButton("🔴 بستن مرورگر و لغو")
        self.close_browser_btn.setObjectName("dangerBtn")
        self.close_browser_btn.setCursor(Qt.PointingHandCursor)
        self.close_browser_btn.setMinimumWidth(260)
        self.close_browser_btn.setMaximumWidth(520)
        self.close_browser_btn.setMinimumHeight(44)
        self.close_browser_btn.clicked.connect(self.cancel_login.emit)
        layout.addWidget(self.close_browser_btn, alignment=Qt.AlignCenter)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(450)
        layout.addWidget(self.status_label, alignment=Qt.AlignCenter)

        layout.addSpacing(16)

    def _style_button(self, btn: QPushButton, object_name: str):
        btn.setMinimumWidth(260)
        btn.setMaximumWidth(520)
        btn.setMinimumHeight(50)
        btn.setObjectName(object_name)
        btn.setCursor(Qt.PointingHandCursor)
        font = QFont()
        font.setPointSize(13)
        font.setBold(True)
        btn.setFont(font)

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
        self.close_browser_btn.setEnabled(not loading)
        self.submit_btn.setText("در حال ورود..." if loading else "ورود")

    def clear(self):
        self.code_input.clear()
        self.status_label.clear()
