"""
TokenRefresher - مدیریت خودکار refresh token برای شیپور.

ویژگی‌ها:
- بررسی انقضای access_token
- refresh خودکار با استفاده از refresh_token
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


class TokenRefresher:
    """مدیریت خودکار refresh token."""

    # شیپور از این endpoint برای refresh استفاده می‌کند
    SHEYPOOR_REFRESH_URL = "https://api.sheypoor.com/auth/refresh-token"
    
    # buffer زمان قبل از انقضا (ثانیه) - اگر کمتر از این مانده باشد، refresh کن
    REFRESH_BUFFER_SECONDS = 60

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager

    # ------------------------------------------------------------------
    # JWT Decoding
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_jwt(token: str) -> Optional[dict]:
        """
        Decode JWT token بدون verification.
        
        فقط payload را decode می‌کند تا exp و iat را بخوانیم.
        """
        try:
            # حذف Bearer prefix اگر وجود داشته باشد
            if token.startswith("Bearer "):
                token = token[7:]
            elif token.startswith("Bearer+"):
                token = token[7:]
            
            # JWT = header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("Invalid JWT format: expected 3 parts, got %d", len(parts))
                return None
            
            # Decode payload (part 1)
            payload_b64 = parts[1]
            # اضافه کردن padding اگر لازم باشد
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
        """
        گرفتن زمان انقضای token (Unix timestamp).
        
        Returns:
            Unix timestamp یا None اگر decode نشد
        """
        payload = self._decode_jwt(token)
        if payload and "exp" in payload:
            return payload["exp"]
        return None

    def is_token_expired(self, token: str, buffer_seconds: int = 0) -> bool:
        """
        بررسی اینکه آیا token منقضی شده یا نه.
        
        Args:
            token: JWT token
            buffer_seconds: اگر کمتر از این ثانیه مانده باشد، منقضی حساب کن
        
        Returns:
            True اگر منقضی شده
        """
        exp = self.get_token_expiry(token)
        if exp is None:
            logger.warning("Cannot determine token expiry")
            return False
        
        now = int(time.time())
        time_left = exp - now
        
        if time_left <= buffer_seconds:
            logger.info(
                "Token expired or expiring soon: %d seconds left (buffer=%d)",
                time_left, buffer_seconds
            )
            return True
        
        logger.debug("Token valid: %d seconds left", time_left)
        return False

    # ------------------------------------------------------------------
    # Session Token Extraction
    # ------------------------------------------------------------------
    def extract_tokens_from_session(self, record: SessionRecord) -> tuple[Optional[str], Optional[str]]:
        """
        استخراج access_token و refresh_token از SessionRecord.
        
        Returns:
            tuple of (access_token, refresh_token)
        
        Note:
            - دیوار: sAccessToken (3 ساعت), sRefreshToken (30 روز), sFrontToken
            - شیپور: access_token (10 دقیقه), refresh_token (90 روز)
        """
        access_token = record.access_token
        refresh_token = record.refresh_token
        
        # اگر در فیلدهای اصلی نیستند، از cookies استخراج کن
        if not access_token or not refresh_token:
            for cookie in record.storage_state.cookies:
                # دیوار
                if cookie.name == "sAccessToken":
                    access_token = cookie.value
                elif cookie.name == "sRefreshToken":
                    refresh_token = cookie.value
                elif cookie.name == "sFrontToken" and not access_token:
                    access_token = cookie.value  # fallback
                # شیپور
                elif cookie.name == "access_token":
                    access_token = cookie.value
                elif cookie.name == "refresh_token":
                    refresh_token = cookie.value
        
        return access_token, refresh_token

    # ------------------------------------------------------------------
    # Token Refresh Logic
    # ------------------------------------------------------------------
    async def refresh_token_via_browser(
        self,
        page: Page,
        context: BrowserContext,
        record: SessionRecord,
    ) -> bool:
        """
        Refresh token با استفاده از browser.
        
        این متد صفحه‌ای از سایت را باز می‌کند و اجازه می‌دهد
        سایت خودش token را refresh کند (چون refresh_token در کوکی است).
        
        برای دیوار: sRefreshToken در path /v8/authenticate/session/refresh
                   دیوار خودش اتوماتیک sAccessToken جدید می‌سازد
        
        Args:
            page: صفحه مرورگر
            context: BrowserContext
            record: SessionRecord
        
        Returns:
            True اگر refresh موفق بود
        """
        try:
            logger.info("[%s] Attempting token refresh via browser navigation", record.platform)
            
            # باز کردن یک صفحه ساده از سایت
            if record.platform == "sheypoor":
                refresh_url = "https://www.sheypoor.com/session/myAccount/myListings/all"
            elif record.platform == "divar":
                refresh_url = "https://divar.ir/my-divar"
            else:
                refresh_url = "https://divar.ir"
            
            await page.goto(refresh_url, wait_until="networkidle", timeout=30_000)
            
            # صبر کن تا سایت token را refresh کند
            await page.wait_for_timeout(3000)
            
            # استخراج توکن‌های جدید از cookies
            cookies = await context.cookies()
            new_access_token = None
            new_refresh_token = None
            
            for cookie in cookies:
                # دیوار
                if cookie["name"] == "sAccessToken":
                    new_access_token = cookie["value"]
                elif cookie["name"] == "sRefreshToken":
                    new_refresh_token = cookie["value"]
                # شیپور
                elif cookie["name"] == "access_token":
                    new_access_token = cookie["value"]
                elif cookie["name"] == "refresh_token":
                    new_refresh_token = cookie["value"]
            
            if new_access_token:
                logger.info("[%s] ✅ Token refreshed successfully", record.platform)
                
                # بررسی اینکه آیا token واقعاً تغییر کرده
                old_access_token, _ = self.extract_tokens_from_session(record)
                if old_access_token != new_access_token:
                    # ذخیره توکن‌های جدید در Session
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

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------
    async def ensure_valid_token(
        self,
        page: Page,
        context: BrowserContext,
        record: SessionRecord,
    ) -> bool:
        """
        اطمینان از اینکه token معتبر است.
        
        اگر token منقضی شده باشد، refresh می‌کند.
        
        Args:
            page: صفحه مرورگر
            context: BrowserContext
            record: SessionRecord
        
        Returns:
            True اگر token معتبر است (یا refresh شد)
        """
        access_token, refresh_token = self.extract_tokens_from_session(record)
        
        if not access_token:
            logger.warning("[%s] No access_token found in session", record.platform)
            return False
        
        # بررسی انقضا
        if self.is_token_expired(access_token, buffer_seconds=self.REFRESH_BUFFER_SECONDS):
            logger.info("[%s] Access token expired, refreshing...", record.platform)
            
            if not refresh_token:
                logger.error("[%s] No refresh_token available, cannot refresh", record.platform)
                return False
            
            # تلاش برای refresh
            success = await self.refresh_token_via_browser(page, context, record)
            if success:
                logger.info("[%s] ✅ Token refreshed successfully", record.platform)
                return True
            else:
                logger.error("[%s] ❌ Token refresh failed", record.platform)
                return False
        else:
            # Token هنوز معتبر است
            exp = self.get_token_expiry(access_token)
            if exp:
                time_left = exp - int(time.time())
                logger.info(
                    "[%s] Access token still valid: %d seconds left",
                    record.platform, time_left
                )
            return True

    def get_token_info(self, token: str) -> dict:
        """
        گرفتن اطلاعات کامل token.
        
        Returns:
            dict با اطلاعات token
        """
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
            "is_expired": self.is_token_expired(token),
        }
        
        return info
