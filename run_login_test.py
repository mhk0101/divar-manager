"""
اسکریپت تست CLI برای Login Manager.

این فایل فعلاً جایگزین رابط کاربری PySide6 است تا بتوانیم ماژول Login
را به‌صورت مستقل تست کنیم. در مراحل بعد، UI اصلی جایگزین خواهد شد.

اجرا:
    python run_login_test.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# افزودن ریشه پروژه به sys.path تا import ها از `config` و `core` کار کنند
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DEFAULT_SESSION_FILE  # noqa: E402
from core.browser_manager import BrowserManager  # noqa: E402
from core.session_manager import SessionManager  # noqa: E402
from modules.login import LoginManager  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)


async def prompt_code() -> str:
    """دریافت کد ۶ رقمی از کاربر در ترمینال (به‌صورت async)."""
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(
        None,
        lambda: input("\n📲  لطفاً کد ۶ رقمی دریافتی از دیوار را وارد کنید: "),
    )
    return code.strip()


async def main() -> int:
    print("=" * 60)
    print("  Divar Manager - Login Test (CLI)")
    print("=" * 60)

    phone = input("\n📱  شماره موبایل (مثلاً 09121234567): ").strip()
    if not phone:
        print("❌  شماره موبایل وارد نشد.")
        return 1

    session_manager = SessionManager(session_name=DEFAULT_SESSION_FILE)
    browser_manager = BrowserManager(
        storage_state_path=session_manager.path,
    )

    async with browser_manager:
        login_manager = LoginManager(
            browser_manager=browser_manager,
            session_manager=session_manager,
            code_provider=prompt_code,
        )

        print("\n🚀  شروع فرآیند ورود...")
        result = await login_manager.login(phone)

    print("\n" + "=" * 60)
    print(result)
    print("=" * 60)
    return 0 if result.success else 2


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹  توسط کاربر متوقف شد.")
        exit_code = 130
    sys.exit(exit_code)
