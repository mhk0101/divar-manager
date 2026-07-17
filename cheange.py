# -*- coding: utf-8 -*-
"""
apply_close_browser.py
======================
قابلیت دکمه «بستن مرورگر» را به برنامه اضافه/تقویت می‌کند.

تغییرات (جایگزین فایل‌های موجود، بدون ساخت فایل جدید دائمی فیچر):
1) ui/platform_tab.py
   - دکمه 🔴 بستن مرورگر در صفحه وضعیت
   - request_close برای SessionCheckWorker
   - request_close برای LoginWorker (بستن واقعی BrowserManager)
   - بستن اجباری fallback (BrowserService + kill chromium playwright)
2) ui/main_window.py
   - دکمه سراسری «بستن مرورگر» در نوار ابزار

اجرا:
    .\.venv\Scripts\python.exe apply_close_browser.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
PLATFORM_TAB = PROJECT_ROOT / "ui" / "platform_tab.py"
MAIN_WINDOW = PROJECT_ROOT / "ui" / "main_window.py"
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


def backup(path: Path) -> Path:
    bak = path.with_suffix(f".py.bak_{STAMP}")
    shutil.copy2(path, bak)
    print(f"[OK] بکاپ: {bak}")
    return bak


def force_close_helper_snippet() -> str:
    """کد کمکی که داخل platform_tab تزریق می‌شود."""
    return r'''
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
        try:
            subprocess.run(
                ["pkill", "-f", "ms-playwright"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
'''


def patch_platform_tab(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    original = text

    # --- imports ---
    if "import subprocess" not in text:
        text = text.replace(
            "import asyncio\n",
            "import asyncio\nimport subprocess\n",
            1,
        )
        notes.append("import subprocess اضافه شد")

    # --- helper force close ---
    if "_force_close_all_browsers" not in text:
        # بعد از LoginManagerFactory یا قبل از class LoginSignals
        marker = "LoginManagerFactory = Callable"
        if marker in text:
            text = text.replace(
                marker,
                marker + "\n" + force_close_helper_snippet(),
                1,
            )
            notes.append("_force_close_all_browsers اضافه شد")
        else:
            # fallback: بعد از imports core
            insert_at = text.find("class LoginSignals")
            if insert_at != -1:
                text = text[:insert_at] + force_close_helper_snippet() + "\n" + text[insert_at:]
                notes.append("_force_close_all_browsers اضافه شد (fallback)")

    # --- IDLE_TIMEOUT ---
    if "IDLE_TIMEOUT_SECONDS" not in text:
        text = text.replace(
            "LoginManagerFactory = Callable",
            "IDLE_TIMEOUT_SECONDS = 300  # 5 دقیقه\n\nLoginManagerFactory = Callable",
            1,
        )
        notes.append("IDLE_TIMEOUT_SECONDS اضافه شد")

    # ========== SessionCheckWorker: request_close ==========
    if "class SessionCheckWorker" in text:
        if "def request_close(self)" not in text or text.find("def request_close") > text.find("class LoginWorker"):
            # ممکن است فقط LoginWorker داشته باشد؛ SessionCheck را چک کن
            sc_start = text.find("class SessionCheckWorker")
            lw_start = text.find("class LoginWorker", sc_start)
            sc_block = text[sc_start:lw_start] if lw_start > sc_start else text[sc_start:sc_start + 4000]
            if "def request_close" not in sc_block:
                # تزریق فیلدها و متد
                old_init_end = re.search(
                    r"(class SessionCheckWorker[\s\S]*?self\.setAutoDelete\(True\))",
                    text,
                )
                if old_init_end:
                    repl = old_init_end.group(1) + (
                        "\n        self._loop: Optional[asyncio.AbstractEventLoop] = None"
                        "\n        self._close_event: Optional[asyncio.Event] = None"
                        "\n        self._browser_manager = None"
                        "\n\n    def request_close(self):"
                        "\n        \"\"\"قابل فراخوانی امن از GUI thread برای بستن دستی مرورگر.\"\"\""
                        "\n        if self._loop is not None and self._close_event is not None:"
                        "\n            self._loop.call_soon_threadsafe(self._close_event.set)"
                        "\n        # بستن اجباری BrowserManager اگر هنوز باز است"
                        "\n        if self._loop is not None and self._browser_manager is not None:"
                        "\n            try:"
                        "\n                asyncio.run_coroutine_threadsafe("
                        "\n                    self._browser_manager.stop(), self._loop"
                        "\n                )"
                        "\n            except Exception:"
                        "\n                pass"
                    )
                    text = text[: old_init_end.start()] + repl + text[old_init_end.end() :]
                    notes.append("SessionCheckWorker.request_close اضافه شد")

        # در run: set loop/close_event
        if "self._close_event = asyncio.Event()" not in text:
            text = text.replace(
                "loop = asyncio.new_event_loop()\n        asyncio.set_event_loop(loop)\n        try:\n            async def _run():\n                sm = SessionManager",
                "loop = asyncio.new_event_loop()\n"
                "        asyncio.set_event_loop(loop)\n"
                "        self._loop = loop\n"
                "        self._close_event = asyncio.Event()\n"
                "        try:\n            async def _run():\n                sm = SessionManager",
                1,
            )
            notes.append("SessionCheckWorker loop/close_event در run تنظیم شد")

        # نگه داشتن مرورگر باز + wait برای close button
        # الگوی ساده (نسخه main)
        simple_close = '''                bm = BrowserManager(session_record=record)
                async with bm:
                    status = await sm.validate(record, bm.page)

                if status == SessionStatus.VALID:
                    return record, "VALID"
                else:
                    return record, status.value'''

        simple_close_alt = '''                bm = BrowserManager(session_record=record)
                async with bm:
                    status = await sm.validate(record, bm.page)

                if status == SessionStatus.VALID:
                    return record, "VALID"
                return record, status.value'''

        keep_open_block = '''                bm = BrowserManager(session_record=record)
                self._browser_manager = bm
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

                    self.signals.status_changed.emit(
                        "🟢 مرورگر باز است. دکمه «بستن مرورگر» را بزنید یا پنجره را ببندید. "
                        f"(بستن خودکار پس از {IDLE_TIMEOUT_SECONDS // 60} دقیقه)"
                    )
                    if self._close_event is None:
                        self._close_event = asyncio.Event()
                    close_task = asyncio.ensure_future(self._close_event.wait())
                    try:
                        page_close_task = asyncio.ensure_future(
                            bm.page.wait_for_event("close", timeout=0)
                        )
                    except Exception:
                        page_close_task = asyncio.ensure_future(asyncio.sleep(10**9))
                    idle_task = asyncio.ensure_future(asyncio.sleep(IDLE_TIMEOUT_SECONDS))
                    try:
                        done, pending = await asyncio.wait(
                            {close_task, page_close_task, idle_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    except Exception:
                        done, pending = set(), {close_task, page_close_task, idle_task}
                    for t in pending:
                        t.cancel()
                    if idle_task in done:
                        self.signals.status_changed.emit(
                            "⏱️ به دلیل عدم فعالیت، مرورگر به‌صورت خودکار بسته شد."
                        )
                    elif close_task in done:
                        self.signals.status_changed.emit("🔴 مرورگر با دکمه بسته شد.")

                if status == SessionStatus.VALID:
                    return record, "VALID"
                return record, status.value'''

        if "self._close_event.wait()" not in text:
            replaced = False
            for old in (simple_close, simple_close_alt):
                if old in text:
                    text = text.replace(old, keep_open_block, 1)
                    notes.append("منطق نگه داشتن مرورگر + wait برای دکمه بستن (نسخه ساده) اضافه شد")
                    replaced = True
                    break
            if not replaced and "wait_for_event(\"close\"" not in text and "wait_for_event('close'" not in text:
                # اگر الگوی keep-open وجود ندارد ولی validate دارد
                notes.append("WARN: الگوی SessionCheck برای keep-open پیدا نشد (شاید قبلاً سفارشی شده)")
        else:
            # اگر keep-open هست ولی self._browser_manager set نمی‌شود
            if "self._browser_manager = bm" not in text:
                text = text.replace(
                    "bm = BrowserManager(session_record=record)",
                    "bm = BrowserManager(session_record=record)\n                self._browser_manager = bm",
                    1,
                )
                notes.append("self._browser_manager در SessionCheckWorker ست شد")

    # ========== LoginWorker: request_close واقعی ==========
    if "class LoginWorker" in text:
        # فیلدها
        if "self._browser_manager" not in text or "LoginWorker" in text:
            lw_init = re.search(
                r"(class LoginWorker[\s\S]*?self\._cancelled = False\n\s+self\.setAutoDelete\(True\))",
                text,
            )
            if lw_init and "self._loop" not in lw_init.group(1):
                text = text.replace(
                    lw_init.group(1),
                    lw_init.group(1)
                    + "\n        self._loop: Optional[asyncio.AbstractEventLoop] = None"
                    + "\n        self._browser_manager = None",
                    1,
                )
                notes.append("LoginWorker: فیلدهای _loop/_browser_manager اضافه شد")

        # متد request_close برای LoginWorker
        if "def request_close(self):" not in text or text.count("def request_close(self)") < 2:
            # اگر فقط SessionCheck دارد، برای Login هم اضافه کن
            cancel_m = re.search(
                r"(class LoginWorker[\s\S]*?def cancel\(self\):[\s\S]*?"
                r"self\._code_future\.cancel\(\)\n)",
                text,
            )
            if cancel_m and "request_close" not in cancel_m.group(0):
                extra = (
                    cancel_m.group(1)
                    + "\n    def request_close(self):\n"
                    + "        \"\"\"لغو login + بستن مرورگر.\"\"\"\n"
                    + "        self.cancel()\n"
                    + "        if self._loop is not None and self._browser_manager is not None:\n"
                    + "            try:\n"
                    + "                fut = asyncio.run_coroutine_threadsafe(\n"
                    + "                    self._browser_manager.stop(), self._loop\n"
                    + "                )\n"
                    + "                fut.result(timeout=8)\n"
                    + "            except Exception:\n"
                    + "                pass\n"
                    + "        _force_close_all_browsers()\n"
                )
                text = text[: cancel_m.start()] + extra + text[cancel_m.end() :]
                notes.append("LoginWorker.request_close اضافه شد")
            elif "def cancel(self):" in text and "def request_close(self):" not in text[
                text.find("class LoginWorker") : text.find("class LoginWorker") + 2500
            ]:
                # cancel ساده‌تر
                text = text.replace(
                    "    def cancel(self):\n"
                    "        \"\"\"لغو Login توسط کاربر.\"\"\"\n"
                    "        self._cancelled = True\n"
                    "        if self._code_future and not self._code_future.done():\n"
                    "            self._code_future.cancel()\n",
                    "    def cancel(self):\n"
                    "        \"\"\"لغو Login توسط کاربر.\"\"\"\n"
                    "        self._cancelled = True\n"
                    "        if self._code_future and not self._code_future.done():\n"
                    "            self._code_future.cancel()\n"
                    "\n"
                    "    def request_close(self):\n"
                    "        \"\"\"لغو login + بستن مرورگر.\"\"\"\n"
                    "        self.cancel()\n"
                    "        if getattr(self, \"_loop\", None) is not None and getattr(self, \"_browser_manager\", None) is not None:\n"
                    "            try:\n"
                    "                fut = asyncio.run_coroutine_threadsafe(\n"
                    "                    self._browser_manager.stop(), self._loop\n"
                    "                )\n"
                    "                fut.result(timeout=8)\n"
                    "            except Exception:\n"
                    "                pass\n"
                    "        _force_close_all_browsers()\n",
                    1,
                )
                notes.append("LoginWorker.request_close (نسخه ساده) اضافه شد")

        # در run: set self._loop و self._browser_manager
        if "self._browser_manager = browser_manager" not in text:
            # الگوی 1
            text2 = text.replace(
                "browser_manager = BrowserManager()\n\n                async with browser_manager:",
                "browser_manager = BrowserManager()\n"
                "                self._browser_manager = browser_manager\n\n"
                "                async with browser_manager:",
                1,
            )
            if text2 != text:
                text = text2
                notes.append("LoginWorker: self._browser_manager set شد")
            else:
                text2 = text.replace(
                    "browser_manager = BrowserManager()\n",
                    "browser_manager = BrowserManager()\n"
                    "                self._browser_manager = browser_manager\n",
                    1,
                )
                if text2 != text:
                    text = text2
                    notes.append("LoginWorker: self._browser_manager set شد (alt)")

            # set loop
            text2 = text.replace(
                "loop = asyncio.new_event_loop()\n        asyncio.set_event_loop(loop)\n        try:\n            async def _run():\n                session_manager = SessionManager",
                "loop = asyncio.new_event_loop()\n"
                "        asyncio.set_event_loop(loop)\n"
                "        self._loop = loop\n"
                "        try:\n            async def _run():\n                session_manager = SessionManager",
                1,
            )
            if text2 != text:
                text = text2
                notes.append("LoginWorker: self._loop set شد")

    # ========== _StatusPage: دکمه بستن ==========
    if "close_browser_btn" not in text:
        # سیگنال
        if "close_browser = Signal()" not in text:
            # بعد از logout = Signal()
            for pat in (
                "    logout = Signal()\n",
                "    logout = Signal()\r\n",
            ):
                if pat in text:
                    text = text.replace(
                        pat,
                        pat + "    close_browser = Signal()\n",
                        1,
                    )
                    notes.append("سیگنال close_browser اضافه شد")
                    break
            # نسخه ساده فقط 3 سیگنال
            if "close_browser = Signal()" not in text:
                text = text.replace(
                    "    start_login = Signal()\n    check_session = Signal()\n    logout = Signal()\n",
                    "    start_login = Signal()\n    check_session = Signal()\n    logout = Signal()\n    close_browser = Signal()\n",
                    1,
                )
                notes.append("سیگنال close_browser (ساده) اضافه شد")

        # دکمه UI — قبل از login_btn
        btn_block = '''
        self.close_browser_btn = QPushButton("🔴 بستن مرورگر")
        self._style_button(self.close_browser_btn, "#dc3545")
        self.close_browser_btn.clicked.connect(self.close_browser.emit)
        self.close_browser_btn.setVisible(True)
        btn_layout.addWidget(self.close_browser_btn)
'''
        # اگر _style_button دو آرگومان دارد
        if "self.login_btn = QPushButton" in text and "close_browser_btn" not in text:
            # قبل از login_btn
            text = text.replace(
                "        self.login_btn = QPushButton",
                btn_block + "\n        self.login_btn = QPushButton",
                1,
            )
            # _style_button ممکن است signature متفاوت داشته باشد
            if "self._style_button(self.close_browser_btn, \"#dc3545\")" in text:
                # اگر _style_button min_w می‌خواهد
                if re.search(r"def _style_button\(self, btn: QPushButton, color: str, min_w", text):
                    text = text.replace(
                        'self._style_button(self.close_browser_btn, "#dc3545")',
                        'self._style_button(self.close_browser_btn, "#dc3545", min_w=400)',
                        1,
                    )
            notes.append("دکمه close_browser_btn به UI اضافه شد")

        # set_loading: نمایش دکمه
        if "def set_loading(self, loading: bool):" in text and "close_browser_btn.setVisible" not in text:
            # در set_loading صفحه status
            # پیدا کردن set_loading اول (_StatusPage)
            m = re.search(
                r"(class _StatusPage[\s\S]*?def set_loading\(self, loading: bool\):[\s\S]*?)(\n    def |\nclass )",
                text,
            )
            if m:
                body = m.group(1)
                if "close_browser_btn" not in body:
                    new_body = body.rstrip() + (
                        "\n        if hasattr(self, \"close_browser_btn\"):\n"
                        "            # همیشه قابل کلیک باشد تا کاربر بتواند مرورگر را ببندد\n"
                        "            self.close_browser_btn.setEnabled(True)\n"
                        "            self.close_browser_btn.setVisible(True)\n"
                    )
                    text = text[: m.start()] + new_body + m.group(2) + text[m.end() :]
                    notes.append("set_loading: دکمه بستن مرورگر همیشه visible")
    else:
        # دکمه هست — همیشه visible و enabled
        text = text.replace(
            "self.close_browser_btn.setVisible(False)",
            "self.close_browser_btn.setVisible(True)",
        )
        text = text.replace(
            "self.close_browser_btn.setVisible(loading)",
            "self.close_browser_btn.setVisible(True)\n        self.close_browser_btn.setEnabled(True)",
        )
        notes.append("دکمه close_browser همیشه visible شد")

    # ========== PlatformTab handler ==========
    if "_on_close_browser_clicked" not in text:
        handler = '''
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

'''
        # قبل از _on_logout
        if "def _on_logout(self):" in text:
            text = text.replace("    def _on_logout(self):", handler + "    def _on_logout(self):", 1)
            notes.append("هندلر _on_close_browser_clicked اضافه شد")
        else:
            # انتهای کلاس
            text = text.rstrip() + "\n" + handler + "\n"
            notes.append("هندلر _on_close_browser_clicked به انتهای فایل اضافه شد")

    # connect signal
    if "close_browser.connect" not in text:
        if "self.status_page.logout.connect(self._on_logout)" in text:
            text = text.replace(
                "self.status_page.logout.connect(self._on_logout)",
                "self.status_page.logout.connect(self._on_logout)\n"
                "        self.status_page.close_browser.connect(self._on_close_browser_clicked)",
                1,
            )
            notes.append("سیگنال close_browser وصل شد")
        elif "self.status_page.check_session.connect" in text:
            text = text.replace(
                "self.status_page.check_session.connect(self._check_session)",
                "self.status_page.check_session.connect(self._check_session)\n"
                "        if hasattr(self.status_page, \"close_browser\"):\n"
                "            self.status_page.close_browser.connect(self._on_close_browser_clicked)",
                1,
            )
            notes.append("سیگنال close_browser وصل شد (alt)")

    # _current_check_worker field
    if "_current_check_worker" not in text:
        text = text.replace(
            "self._current_worker: Optional[LoginWorker] = None",
            "self._current_worker: Optional[LoginWorker] = None\n"
            "        self._current_check_worker: Optional[SessionCheckWorker] = None",
            1,
        )
        notes.append("فیلد _current_check_worker اضافه شد")

    # هنگام start worker، reference نگه دار
    if "self._current_check_worker = worker" not in text:
        text2 = text.replace(
            "QThreadPool.globalInstance().start(worker)",
            "self._current_check_worker = worker\n        QThreadPool.globalInstance().start(worker)",
            1,
        )
        if text2 != text:
            text = text2
            notes.append("reference به check worker ذخیره می‌شود")

    # پاک کردن reference بعد از تمام شدن
    if "self._current_check_worker = None" not in text:
        text = text.replace(
            "self.status_page.set_loading(False)\n        self._log(\"INFO\", f\"[{self._platform_name}] Session check:",
            "self.status_page.set_loading(False)\n"
            "        self._current_check_worker = None\n"
            "        self._log(\"INFO\", f\"[{self._platform_name}] Session check:",
            1,
        )

    # بهبود handler موجود: LoginWorker + force close
    if "_on_close_browser_clicked" in text and "_force_close_all_browsers()" not in text[
        text.find("_on_close_browser_clicked") : text.find("_on_close_browser_clicked") + 800
    ]:
        old_h = '''    def _on_close_browser_clicked(self):
        """بستن دستی مرورگر توسط کاربر از طریق GUI."""
        if getattr(self, "_current_check_worker", None):
            self._current_check_worker.request_close()
            self._log(
                "INFO",
                f"[{self._platform_name}] کاربر درخواست بستن دستی مرورگر داد",
            )
        else:
            self._log(
                "INFO",
                f"[{self._platform_name}] درخواست بستن مرورگر - هیچ مرورگر فعالی یافت نشد",
            )
'''
        new_h = '''    def _on_close_browser_clicked(self):
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
        try:
            self.status_page.set_loading(False)
            self.status_page.set_status("🔴 درخواست بستن مرورگر ارسال شد.")
        except Exception:
            pass
        self._log(
            "INFO",
            f"[{self._platform_name}] کاربر درخواست بستن مرورگر داد (closed_any={closed_any})",
        )
'''
        if old_h in text:
            text = text.replace(old_h, new_h)
            notes.append("هندلر _on_close_browser_clicked تقویت شد")
        else:
            # soft replace partial
            if "هیچ مرورگر فعالی یافت نشد" in text:
                text = text.replace(
                    '''    def _on_close_browser_clicked(self):
        """بستن دستی مرورگر توسط کاربر از طریق GUI."""
        if getattr(self, "_current_check_worker", None):
            self._current_check_worker.request_close()
            self._log(
                "INFO",
                f"[{self._platform_name}] کاربر درخواست بستن دستی مرورگر داد",
            )
        else:
            self._log(
                "INFO",
                f"[{self._platform_name}] درخواست بستن مرورگر - هیچ مرورگر فعالی یافت نشد",
            )''',
                    new_h.rstrip(),
                )
                notes.append("هندلر close تقویت شد (partial)")

    # دکمه بستن روی صفحه کد (حین login)
    if "class _CodePage" in text and "بستن مرورگر" not in text[
        text.find("class _CodePage") : text.find("class PlatformTab")
    ]:
        # بعد از cancel_btn
        if "self.cancel_btn = QPushButton" in text:
            code_close = '''
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
'''
            # insert after cancel_btn connect
            text2 = re.sub(
                r"(self\.cancel_btn\.clicked\.connect\(self\.cancel_login\.emit\)\n"
                r"\s+layout\.addWidget\(self\.cancel_btn, alignment=Qt\.AlignCenter\))",
                r"\1\n" + code_close,
                text,
                count=1,
            )
            if text2 != text:
                text = text2
                notes.append("دکمه بستن مرورگر در صفحه کد (Login) اضافه شد")
                # cancel_login باید مرورگر را هم ببندد - از طریق _on_cancel_login
                if "def _on_cancel_login" in text and "request_close" not in text[
                    text.find("def _on_cancel_login") : text.find("def _on_cancel_login") + 400
                ]:
                    text = text.replace(
                        '''    def _on_cancel_login(self):
        """کاربر Login را لغو کرد."""
        self._log("INFO", f"[{self._platform_name}] Login cancelled by user")
        if self._current_worker:
            self._current_worker.cancel()
            self._current_worker = None
        self._go_to_status()
''',
                        '''    def _on_cancel_login(self):
        """کاربر Login را لغو کرد / بستن مرورگر."""
        self._log("INFO", f"[{self._platform_name}] Login cancelled / close browser by user")
        if self._current_worker:
            if hasattr(self._current_worker, "request_close"):
                self._current_worker.request_close()
            else:
                self._current_worker.cancel()
            self._current_worker = None
        _force_close_all_browsers()
        self._go_to_status()
''',
                        1,
                    )
                    # نسخه بدون docstring فارسی دقیق
                    text = text.replace(
                        '''    def _on_cancel_login(self):
        self._log("INFO", f"[{self._platform_name}] Login cancelled by user")
        if self._current_worker:
            self._current_worker.cancel()
            self._current_worker = None
        self._go_to_status()
''',
                        '''    def _on_cancel_login(self):
        self._log("INFO", f"[{self._platform_name}] Login cancelled / close browser by user")
        if self._current_worker:
            if hasattr(self._current_worker, "request_close"):
                self._current_worker.request_close()
            else:
                self._current_worker.cancel()
            self._current_worker = None
        _force_close_all_browsers()
        self._go_to_status()
''',
                        1,
                    )
                    notes.append("_on_cancel_login تقویت شد برای بستن مرورگر")

    if text == original and not notes:
        notes.append("هیچ تغییری لازم نبود / الگوها match نشدند")
    return text, notes


def patch_main_window(text: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    if "بستن مرورگر" in text and "close_all_browsers" in text:
        notes.append("main_window قبلاً دکمه سراسری دارد")
        return text, notes

    # import QToolBar / QPushButton if needed
    if "QPushButton" not in text:
        text = text.replace(
            "from PySide6.QtWidgets import (\n    QApplication,\n    QMainWindow,\n    QTabWidget,\n)",
            "from PySide6.QtWidgets import (\n    QApplication,\n    QMainWindow,\n    QPushButton,\n    QTabWidget,\n    QToolBar,\n)",
            1,
        )
        notes.append("imports widgets به‌روز شد")
    else:
        if "QToolBar" not in text:
            text = text.replace("QTabWidget,\n)", "QTabWidget,\n    QToolBar,\n    QPushButton,\n)", 1)
            if "QToolBar" not in text:
                text = text.replace(
                    "from PySide6.QtWidgets import (",
                    "from PySide6.QtWidgets import (\n    QToolBar,\n    QPushButton,",
                    1,
                )
            notes.append("QToolBar/QPushButton import شد")

    # after setCentralWidget
    toolbar_code = '''
        # نوار ابزار سراسری — بستن مرورگر
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.btn_close_browser = QPushButton("🔴 بستن مرورگر")
        self.btn_close_browser.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.btn_close_browser.clicked.connect(self._close_all_browsers)
        tb.addWidget(self.btn_close_browser)
'''
    if "btn_close_browser" not in text:
        if "self.setCentralWidget(self.tabs)" in text:
            text = text.replace(
                "self.setCentralWidget(self.tabs)",
                "self.setCentralWidget(self.tabs)\n" + toolbar_code,
                1,
            )
            notes.append("دکمه سراسری بستن مرورگر به toolbar اضافه شد")
        else:
            notes.append("WARN: setCentralWidget پیدا نشد")

    method = '''
    def _close_all_browsers(self):
        """بستن مرورگر از هر دو تب + force close."""
        try:
            if hasattr(self, "divar_tab") and hasattr(self.divar_tab, "_on_close_browser_clicked"):
                self.divar_tab._on_close_browser_clicked()
        except Exception:
            pass
        try:
            if hasattr(self, "sheypoor_tab") and hasattr(self.sheypoor_tab, "_on_close_browser_clicked"):
                self.sheypoor_tab._on_close_browser_clicked()
        except Exception:
            pass
        try:
            from core.browser_service import BrowserService
            BrowserService.instance().request_close_all(timeout=10.0)
        except Exception:
            pass
        # fallback kill playwright chromium
        try:
            import subprocess
            if sys.platform.startswith("win"):
                ps = (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { "
                    "  ($_.Name -match 'chrome|chromium') -and "
                    "  ($_.CommandLine -match 'ms-playwright|playwright|chromium') "
                    "} | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True,
                    timeout=15,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except Exception:
            pass
        try:
            self.logs_tab.append_log("INFO", "🔴 درخواست بستن سراسری مرورگر ارسال شد")
        except Exception:
            pass
'''
    if "def _close_all_browsers" not in text:
        # قبل از def main
        if "\ndef main():" in text:
            text = text.replace("\ndef main():", method + "\n\ndef main():", 1)
            notes.append("متد _close_all_browsers اضافه شد")
        else:
            text = text.rstrip() + "\n" + method + "\n"
            notes.append("متد _close_all_browsers به انتها اضافه شد")

    return text, notes


def syntax_check(path: Path) -> bool:
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        print(f"[OK] syntax check: {path.name}")
        return True
    except SyntaxError as e:
        print(f"[ERROR] syntax error in {path}: {e}")
        return False


def run_app():
    python_exe = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    main_py = PROJECT_ROOT / "ui" / "main.py"
    if not python_exe.exists():
        print(f"[WARN] venv python پیدا نشد، از sys.executable استفاده می‌شود")
        python_exe = Path(sys.executable)
    if not main_py.exists():
        print(f"[ERROR] {main_py} پیدا نشد")
        return
    print()
    print(f"[RUN] {python_exe} {main_py}")
    print("-" * 60)
    subprocess.run([str(python_exe), str(main_py)], cwd=str(PROJECT_ROOT))


def main():
    print("=" * 60)
    print("Apply Close Browser Button")
    print("=" * 60)

    if not PLATFORM_TAB.exists():
        print(f"[ERROR] پیدا نشد: {PLATFORM_TAB}")
        raise SystemExit(1)

    backup(PLATFORM_TAB)
    pt_text = PLATFORM_TAB.read_text(encoding="utf-8")
    pt_new, pt_notes = patch_platform_tab(pt_text)
    PLATFORM_TAB.write_text(pt_new, encoding="utf-8")
    print(f"[OK] نوشته شد: {PLATFORM_TAB}")
    for n in pt_notes:
        print(f"  - {n}")

    if not syntax_check(PLATFORM_TAB):
        # restore
        baks = sorted(PLATFORM_TAB.parent.glob(f"platform_tab.py.bak_{STAMP}"))
        if baks:
            shutil.copy2(baks[0], PLATFORM_TAB)
            print("[RESTORE] platform_tab به خاطر syntax error بازگردانی شد")
        raise SystemExit(1)

    if MAIN_WINDOW.exists():
        backup(MAIN_WINDOW)
        mw_text = MAIN_WINDOW.read_text(encoding="utf-8")
        mw_new, mw_notes = patch_main_window(mw_text)
        MAIN_WINDOW.write_text(mw_new, encoding="utf-8")
        print(f"[OK] نوشته شد: {MAIN_WINDOW}")
        for n in mw_notes:
            print(f"  - {n}")
        if not syntax_check(MAIN_WINDOW):
            baks = sorted(MAIN_WINDOW.parent.glob(f"main_window.py.bak_{STAMP}"))
            if baks:
                shutil.copy2(baks[0], MAIN_WINDOW)
                print("[RESTORE] main_window بازگردانی شد")
            raise SystemExit(1)
    else:
        print(f"[WARN] {MAIN_WINDOW} پیدا نشد — فقط platform_tab پچ شد")

    print()
    print("خلاصه قابلیت:")
    print("  • دکمه 🔴 بستن مرورگر در تب دیوار/شیپور")
    print("  • دکمه سراسری در نوار ابزار پنجره اصلی")
    print("  • بستن SessionCheck + Login + force kill chromium playwright")
    print()
    print("اجرای برنامه...")
    run_app()


if __name__ == "__main__":
    main()