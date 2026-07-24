"""
Network utilities — بررسی اینترنت و ادامه خودکار عملیات بعد از وصل شدن.

هدف:
- قبل از شروع عملیات، اتصال اینترنت بررسی شود.
- اگر هنگام باز کردن صفحه/آگهی/چت اینترنت قطع شد، برنامه منتظر وصل شدن بماند
  و همان مرحله را دوباره تلاش کند.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("divar.network")

ProgressCallback = Optional[Callable[[str], None]]


async def _can_open_connection(host: str, port: int, timeout: float = 4.0) -> bool:
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def is_internet_available(timeout: float = 4.0) -> bool:
    """بررسی سبک اتصال اینترنت با چند مقصد مختلف.

    فقط به یک مقصد موفق نیاز داریم. نکته مهم: تمام Taskهای تست اتصال،
    حتی اگر یکی زودتر موفق شود، در پایان cancel/gather می‌شوند تا هنگام بستن
    event loop خطای «Task was destroyed but it is pending» تولید نشود.
    """
    targets = [
        ("divar.ir", 443),
        ("www.sheypoor.com", 443),
        ("1.1.1.1", 53),
        ("8.8.8.8", 53),
    ]

    tasks = [
        asyncio.create_task(_can_open_connection(h, p, timeout=timeout), name=f"netcheck:{h}:{p}")
        for h, p in targets
    ]

    ok = False
    try:
        pending = set(tasks)
        deadline = time.monotonic() + timeout + 1.0

        while pending and time.monotonic() < deadline:
            wait_timeout = max(0.1, deadline - time.monotonic())
            done, pending = await asyncio.wait(
                pending,
                timeout=wait_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                break

            for task in done:
                try:
                    if task.result():
                        ok = True
                        break
                except Exception:
                    pass

            if ok:
                break

        return ok

    finally:
        # خیلی مهم: هر Task باقی‌مانده باید cancel و سپس await شود؛
        # صرفاً cancel کردن کافی نیست و در پایان QThread/event-loop خطای pending می‌دهد.
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def wait_for_internet(
    progress_callback: ProgressCallback = None,
    check_interval: float = 5.0,
    first_message: str = "🌐 در حال بررسی اتصال اینترنت...",
    restored_message: str = "✅ اینترنت وصل است. ادامه عملیات...",
) -> None:
    """تا زمان وصل بودن اینترنت صبر می‌کند.

    اگر اینترنت همان ابتدا وصل باشد سریع برمی‌گردد؛ اگر قطع باشد هر چند ثانیه
    دوباره بررسی می‌کند و برنامه را متوقف/کرش نمی‌کند.
    """
    if progress_callback:
        progress_callback(first_message)

    if await is_internet_available():
        if progress_callback:
            progress_callback(restored_message)
        return

    start = time.monotonic()
    last_log = 0.0
    if progress_callback:
        progress_callback("⚠️ اینترنت قطع است؛ برنامه منتظر وصل شدن می‌ماند...")

    while True:
        await asyncio.sleep(check_interval)
        if await is_internet_available():
            waited = int(time.monotonic() - start)
            if progress_callback:
                progress_callback(f"✅ اینترنت بعد از {waited} ثانیه وصل شد. ادامه از همان مرحله...")
            return

        now = time.monotonic()
        if now - last_log >= 30:
            last_log = now
            msg = "⏳ اینترنت هنوز قطع است؛ همچنان منتظر اتصال..."
            logger.warning(msg)
            if progress_callback:
                progress_callback(msg)


def _looks_like_network_error(exc: Exception) -> bool:
    text = str(exc).lower()
    needles = [
        "err_internet_disconnected",
        "err_network_changed",
        "err_name_not_resolved",
        "err_connection",
        "err_timed_out",
        "timeout",
        "net::",
        "navigation failed",
    ]
    return any(n in text for n in needles)


async def safe_page_goto(
    page,
    url: str,
    *,
    wait_until: str = "domcontentloaded",
    timeout: int = 30_000,
    progress_callback: ProgressCallback = None,
    label: str = "صفحه",
    max_attempts: int = 5,
):
    """نسخه مقاوم page.goto.

    قبل از goto اینترنت را چک می‌کند. اگر هنگام navigation اینترنت قطع/کند شد،
    منتظر اتصال می‌ماند و همان URL را دوباره باز می‌کند.
    """
    last_error = None
    for attempt in range(1, max_attempts + 1):
        await wait_for_internet(
            progress_callback=progress_callback,
            first_message=f"🌐 بررسی اینترنت قبل از باز کردن {label}...",
            restored_message=f"✅ اینترنت برای باز کردن {label} آماده است.",
        )
        try:
            return await page.goto(url, wait_until=wait_until, timeout=timeout)
        except Exception as exc:
            last_error = exc
            if not _looks_like_network_error(exc) and attempt >= 2:
                raise
            if progress_callback:
                progress_callback(
                    f"⚠️ مشکل شبکه/لود هنگام باز کردن {label} (تلاش {attempt}/{max_attempts}): {exc}\n"
                    f"⏳ صبر تا اتصال پایدار و تلاش مجدد همان مرحله..."
                )
            await wait_for_internet(progress_callback=progress_callback)
            await asyncio.sleep(min(3 * attempt, 15))

    if last_error:
        raise last_error
