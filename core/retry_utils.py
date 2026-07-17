# -*- coding: utf-8 -*-
"""
ابزار عمومی Retry با Backoff + Timeout برای عملیات async (Playwright و ...)
بدون وابستگی به ساختار داخلی پروژه - قابل import مستقل.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger("divar_manager.retry")

T = TypeVar("T")


class OperationTimeoutError(Exception):
    """وقتی یک عملیات (مثلاً بارگذاری صفحه) بیش از حد طول بکشد."""


class NetworkError(Exception):
    """خطای مرتبط با قطعی شبکه/ارتباط با سرور."""


class RetryExhaustedError(Exception):
    """بعد از تمام تلاش‌های مجدد باز هم عملیات شکست خورد."""

    def __init__(self, message: str, last_error: Optional[BaseException] = None):
        super().__init__(message)
        self.last_error = last_error


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 2.0       # ثانیه - تأخیر پایه
    backoff_factor: float = 2.0   # ضریب افزایش تأخیر بین تلاش‌ها
    max_delay: float = 20.0       # سقف تأخیر
    timeout: float = 30.0         # ثانیه - timeout هر تلاش


NETWORK_ERROR_MARKERS = (
    "net::err",
    "err_internet_disconnected",
    "err_connection",
    "err_name_not_resolved",
    "err_network_changed",
    "timeout",
    "target closed",
    "navigation timeout",
    "connection refused",
    "connection reset",
)


def is_network_like_error(exc: BaseException) -> bool:
    """آیا این خطا شبیه قطعی اینترنت/شبکه است؟"""
    text = str(exc).lower()
    return any(marker in text for marker in NETWORK_ERROR_MARKERS)


def friendly_error_message(exc: BaseException) -> str:
    """تبدیل خطای فنی به پیام قابل فهم برای کاربر (فارسی)."""
    if isinstance(exc, OperationTimeoutError):
        return (
            "⏱️ زمان انتظار برای اتصال به سرور به پایان رسید. "
            "لطفاً اتصال اینترنت خود را بررسی کنید."
        )
    if isinstance(exc, NetworkError) or is_network_like_error(exc):
        return (
            "🌐 ارتباط با سرور برقرار نیست. "
            "لطفاً اتصال اینترنت خود را بررسی و دوباره تلاش کنید."
        )
    if isinstance(exc, RetryExhaustedError):
        inner = exc.last_error
        if inner:
            return f"❌ عملیات پس از چند تلاش ناموفق بود:\n{friendly_error_message(inner)}"
        return "❌ عملیات پس از چند تلاش ناموفق بود."
    return f"⚠️ خطای غیرمنتظره: {exc}"


async def with_timeout(coro: Awaitable[T], timeout: float, op_name: str = "operation") -> T:
    """اجرای یک coroutine با محدودیت زمانی مشخص."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError as e:
        logger.error("Timeout after %.1fs in %s", timeout, op_name)
        raise OperationTimeoutError(
            f"عملیات «{op_name}» بیش از {int(timeout)} ثانیه طول کشید."
        ) from e


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    config: Optional[RetryConfig] = None,
    op_name: str = "operation",
    on_attempt_failed: Optional[Callable[[int, BaseException], None]] = None,
) -> T:
    """اجرای یک تابع async با Retry + Exponential Backoff + Timeout."""
    cfg = config or RetryConfig()
    last_error: Optional[BaseException] = None

    for attempt in range(1, cfg.max_attempts + 1):
        try:
            logger.info("Attempt %d/%d for %s", attempt, cfg.max_attempts, op_name)
            return await with_timeout(func(), cfg.timeout, op_name)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.error(
                "Attempt %d/%d failed for %s: %s",
                attempt, cfg.max_attempts, op_name, e,
            )
            if on_attempt_failed:
                on_attempt_failed(attempt, e)

            if attempt >= cfg.max_attempts:
                break

            delay = min(cfg.base_delay * (cfg.backoff_factor ** (attempt - 1)), cfg.max_delay)
            logger.info("Retrying %s in %.1fs...", op_name, delay)
            await asyncio.sleep(delay)

    raise RetryExhaustedError(
        f"عملیات «{op_name}» پس از {cfg.max_attempts} تلاش ناموفق بود.",
        last_error=last_error,
    )
