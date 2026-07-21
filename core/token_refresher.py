"""
TokenRefresher - مدیریت خودکار refresh token برای شیپور و دیوار.

ویژگی‌ها:
- بررسی انقضای access_token
- refresh خودکار با استفاده از refresh_token
- فرمت‌دهی زمان باقی‌مانده اعتبارسنجی به ثانیه، دقیقه، ساعت، روز و هفته
- ذخیره توکن‌های جدید در Session
- پشتیبانی از JWT decoding
"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime
from typing import Optional

from playwright.async_api import BrowserContext, Page

from core.session_manager import SessionManager
from core.session_models import SessionRecord, StorageState

logger = logging.getLogger("divar.token_refresher")


def format_human_readable_duration(seconds: int) -> str:
    """تبدیل زمان بر حسب ثانیه به متن خوانای فارسی (ثانیه، دقیقه، ساعت، روز، هفته)."""
    if seconds <= 0:
        return "منقضی شده"

    weeks = seconds // (7 * 24 * 3600)
    seconds %= (7 * 24 * 3600)

    days = seconds // (24 * 3600)
    seconds %= (24 * 3600)

    hours = seconds // 3600
    seconds %= 3600

    minutes = seconds // 60
    secs = seconds % 60

    parts = []
    if weeks > 0:
        parts.append(f"{weeks} هفته")
    if days > 0:
        parts.append(f"{days} روز")
    if hours > 0:
        parts.append(f"{hours} ساعت")
    if minutes > 0:
        parts.append(f"{minutes} دقیقه")
    if secs > 0 and not weeks and not days and hours < 2:
        parts.append(f"{secs} ثانیه")

    if not parts:
        return "چند لحظه"

    return " و ".join(parts)


class TokenRefresher:
    """مدیریت خودکار refresh token."""

    SHEYPOOR_REFRESH_URL = "https://api.sheypoor.com/auth/refresh-token"
    REFRESH_BUFFER_SECONDS = 60

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager

    @staticmethod
    def _decode_jwt(token: str) -> Optional[dict]:
        try:
            if token.startswith("Bearer "):
                token = token[7:]
            elif token.startswith("Bearer+"):
                token = token[7:]

            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("Invalid JWT format: expected 3 parts, got %d", len(parts))
                return None

            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes)

            return payload

        except Exception as e:
            logger.error("Failed to decode JWT: %s", e)
            return None

    def get_token_expiry(self, token: str) -> Optional[int]:
        payload = self._decode_jwt(token)
        if payload and "exp" in payload:
            return payload["exp"]
        return None

    def is_token_expired(self, token: str, buffer_seconds: int = 0) -> bool:
        exp = self.get_token_expiry(token)
        if exp is None:
            logger.warning("Cannot determine token expiry")
            return False

        now = int(time.time())
        time_left = exp - now

        if time_left <= buffer_seconds:
            dur_str = format_human_readable_duration(time_left)
            logger.info(
                "Token expired or expiring soon: %d seconds left (%s) (buffer=%d)",
                time_left, dur_str, buffer_seconds
            )
            return True

        logger.debug("Token valid: %d seconds left", time_left)
        return False

    def extract_tokens_from_session(self, record: SessionRecord) -> tuple[Optional[str], Optional[str]]:
        access_token = record.access_token
        refresh_token = record.refresh_token

        if not access_token or not refresh_token:
            for cookie in record.storage_state.cookies:
                if cookie.name == "sAccessToken":
                    access_token = cookie.value
                elif cookie.name == "sRefreshToken":
                    refresh_token = cookie.value
                elif cookie.name == "sFrontToken" and not access_token:
                    access_token = cookie.value
                elif cookie.name == "access_token":
                    access_token = cookie.value
                elif cookie.name == "refresh_token":
                    refresh_token = cookie.value

        return access_token, refresh_token

    async def refresh_token_via_browser(
        self,
        page: Page,
        context: BrowserContext,
        record: SessionRecord,
    ) -> bool:
        try:
            logger.info("[%s] Attempting token refresh via browser navigation", record.platform)

            if record.platform == "sheypoor":
                refresh_url = "https://www.sheypoor.com/session/myAccount/myListings/all"
            elif record.platform == "divar":
                refresh_url = "https://divar.ir/my-divar"
            else:
                refresh_url = "https://divar.ir"

            await page.goto(refresh_url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_timeout(3000)

            cookies = await context.cookies()
            new_access_token = None
            new_refresh_token = None

            for cookie in cookies:
                if cookie["name"] == "sAccessToken":
                    new_access_token = cookie["value"]
                elif cookie["name"] == "sRefreshToken":
                    new_refresh_token = cookie["value"]
                elif cookie["name"] == "access_token":
                    new_access_token = cookie["value"]
                elif cookie["name"] == "refresh_token":
                    new_refresh_token = cookie["value"]

            if new_access_token:
                logger.info("[%s] ✅ Token refreshed successfully", record.platform)

                old_access_token, _ = self.extract_tokens_from_session(record)
                if old_access_token != new_access_token:
                    await self._session_manager.save_from_context(
                        context=context,
                        phone=record.phone,
                        access_token=new_access_token,
                        refresh_token=new_refresh_token,
                        metadata={"refreshed_at": datetime.now().isoformat()},
                    )
                    logger.info("[%s] New tokens saved to database", record.platform)
                else:
                    logger.info("[%s] Token unchanged (still valid)", record.platform)

                return True
            else:
                logger.warning("[%s] ❌ No access_token found after refresh", record.platform)
                return False

        except Exception as e:
            logger.error("[%s] Token refresh failed: %s", record.platform, e)
            return False

    async def ensure_valid_token(
        self,
        page: Page,
        context: BrowserContext,
        record: SessionRecord,
    ) -> bool:
        access_token, refresh_token = self.extract_tokens_from_session(record)

        if not access_token:
            logger.warning("[%s] No access_token found in session", record.platform)
            return False

        if self.is_token_expired(access_token, buffer_seconds=self.REFRESH_BUFFER_SECONDS):
            logger.info("[%s] Access token expired, refreshing...", record.platform)

            if not refresh_token:
                logger.error("[%s] No refresh_token available, cannot refresh", record.platform)
                return False

            success = await self.refresh_token_via_browser(page, context, record)
            if success:
                logger.info("[%s] ✅ Token refreshed successfully", record.platform)
                return True
            else:
                logger.error("[%s] ❌ Token refresh failed", record.platform)
                return False
        else:
            exp = self.get_token_expiry(access_token)
            if exp:
                time_left = exp - int(time.time())
                duration_str = format_human_readable_duration(time_left)
                logger.info(
                    "[%s] Access token still valid: %d seconds left (%s)",
                    record.platform, time_left, duration_str
                )
            return True

    def get_token_info(self, token: str) -> dict:
        payload = self._decode_jwt(token)
        if not payload:
            return {"error": "Cannot decode token"}

        exp = payload.get("exp")
        iat = payload.get("iat")
        now = int(time.time())

        info = {
            "type": payload.get("type", "UNKNOWN"),
            "user_id": payload.get("userId"),
            "issued_at": datetime.fromtimestamp(iat).isoformat() if iat else None,
            "expires_at": datetime.fromtimestamp(exp).isoformat() if exp else None,
            "seconds_left": exp - now if exp else None,
            "human_duration": format_human_readable_duration(exp - now) if exp else "نامشخص",
            "is_expired": self.is_token_expired(token),
        }

        return info
