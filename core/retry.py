"""
Retry - ابزار مدیریت خطا و تلاش مجدد.

Decorator و کمکی‌های برای مدیریت عملیاتی که ممکن است به دلایل مختلف
(قطع اینترنت، timeout، ...) شکست بخورند و نیاز به retry دارند.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Tuple, Type

logger = logging.getLogger("divar.retry")


def async_retry(
    max_attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    jitter: float = 0.1,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException], Any] | None = None,
):
    """
    Decorator برای تلاش مجدد روی توابع async.

    Args:
        max_attempts: حداکثر تعداد تلاش‌ها
        delay: تأخیر اولیه بین تلاش‌ها (ثانیه)
        backoff: ضریب افزایش تأخیر
        jitter: نویز تصادفی برای جلوگیری از thundering herd
        exceptions: exceptionهایی که باعث retry می‌شوند
        on_retry: callback که قبل از هر retry صدا زده می‌شود
                  امضا: (attempt_number, exception) -> None
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            "[%s] Failed after %d attempts: %s",
                            func.__name__, attempt, e,
                        )
                        raise

                    # Jitter
                    actual_delay = current_delay * (1 + random.uniform(-jitter, jitter))
                    logger.warning(
                        "[%s] Attempt %d/%d failed: %s. Retrying in %.1fs...",
                        func.__name__, attempt, max_attempts, e, actual_delay,
                    )

                    if on_retry:
                        try:
                            on_retry(attempt, e)
                        except Exception:
                            pass

                    await asyncio.sleep(actual_delay)
                    current_delay *= backoff

            # نباید به اینجا برسیم
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    """Decorator برای تلاش مجدد روی توابع sync."""
    import time

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        raise
                    logger.warning(
                        "[%s] Attempt %d/%d failed: %s. Retrying...",
                        func.__name__, attempt, max_attempts, e,
                    )
                    time.sleep(delay)
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


class OperationCancelled(Exception):
    """زمانی که کاربر یا سیستم عملیات را لغو می‌کند."""
    pass


class NetworkError(Exception):
    """خطای شبکه (قطع اینترنت، timeout و ...)."""
    pass


class SessionExpired(Exception):
    """Session منقضی شده و نیاز به Login مجدد دارد."""
    pass


class LoginRequired(Exception):
    """کاربر هنوز لاگین نکرده است."""
    pass
