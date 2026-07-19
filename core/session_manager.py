"""
SessionManager - مدیر اصلی Sessionها (نسخه کامل و اصلاح‌شده)

اصلاحات انجام‌شده:
1. ✅ اضافه شدن متد capture_storage_state() (برای رفع خطای Login)
2. ✅ اصلاح متد delete() برای حذف فایل JSON (برای رفع مشکل حذف ناقص)
3. ✅ اصلاح متد delete_by_phone() برای حذف فایل JSON

این کلاس API اصلی برای کار با Session است و تمام عملیات مربوط به
ذخیره، بازیابی، اعتبارسنجی و به‌روزرسانی Session را مدیریت می‌کند.

ویژگی‌ها:
- ذخیره در SQLite (با تمام جزئیات)
- تولید storage_state file برای Playwright
- اعتبارسنجی با تست واقعی روی سایت
- مدیریت انقضا و تغییر
- Logging کامل
- مستقل از UI
- حذف کامل Session (DB + JSON)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Error as PlaywrightError

from config.settings import SESSIONS_DIR, TEMP_DIR
from core.retry import async_retry
from core.session_db import SessionDB
from core.session_models import SessionRecord, SessionStatus, StorageState
from core.session_validator import SessionValidator

logger = logging.getLogger("divar.session")


class SessionManager:
    """
    مدیر Session حرفه‌ای.

    Example:
        sm = SessionManager(platform="divar")

        # ذخیره پس از Login
        record = await sm.save_from_context(context, phone="09121234567")

        # بارگذاری Session
        record = await sm.load(phone="09121234567")
        if record and record.is_valid():
            # استفاده از Session
            storage_path = await sm.export_storage_state(record)
            context = await browser.new_context(storage_state=str(storage_path))

        # اعتبارسنجی
        status = await sm.validate(record, page)
        if status == SessionStatus.INVALID:
            # نیاز به Login مجدد
            await sm.mark_invalid(record)
        
        # حذف کامل Session (DB + JSON)
        sm.delete(record)
    """

    def __init__(self, platform: str, db: Optional[SessionDB] = None) -> None:
        self._platform = platform
        self._db = db or SessionDB()
        self._validator = SessionValidator(platform)
        self._temp_files: list[Path] = []

    @property
    def platform(self) -> str:
        return self._platform

    # ------------------------------------------------------------------
    # ✨ NEW: Capture Storage State (بدون ذخیره در DB)
    # ------------------------------------------------------------------
    async def capture_storage_state(self, context: BrowserContext) -> StorageState:
        """
        استخراج storage_state از یک BrowserContext بدون ذخیره در DB.

        این متد فقط storage_state را می‌خواند و برمی‌گرداند.
        برای مقایسه state قبل و بعد از navigation استفاده می‌شود.

        Args:
            context: BrowserContext فعال

        Returns:
            StorageState شامل cookies، localStorage و sessionStorage
        """
        try:
            # استخراج storage_state استاندارد Playwright
            raw_state = await context.storage_state()
            storage_state = StorageState.from_playwright(raw_state)

            # استخراج sessionStorage از صفحات باز
            # Playwright به‌صورت پیش‌فرض sessionStorage را در storage_state نمی‌گذارد
            for page in context.pages:
                try:
                    session_data = await page.evaluate("""
                        () => ({
                            origin: window.location.origin,
                            data: Object.fromEntries(
                                Array.from({length: sessionStorage.length}, (_, i) => {
                                    const key = sessionStorage.key(i);
                                    return [key, key === null ? null : sessionStorage.getItem(key)];
                                })
                            ),
                        })
                    """)
                    origin = session_data.get("origin")
                    data = session_data.get("data")
                    if origin and data:
                        storage_state.session_storage[origin] = data
                except PlaywrightError:
                    # صفحه ممکن است بسته شده باشد
                    continue

            logger.info(
                "[%s] Captured storage state: cookies=%d, localStorage_origins=%d, sessionStorage_origins=%d",
                self._platform,
                len(storage_state.cookies),
                len(storage_state.local_storage),
                len(storage_state.session_storage),
            )

            return storage_state

        except PlaywrightError as e:
            logger.error("[%s] Failed to capture storage state: %s", self._platform, e)
            raise
        except Exception as e:
            logger.exception("[%s] Unexpected error capturing storage state: %s", self._platform, e)
            raise

    # ------------------------------------------------------------------
    # ذخیره Session
    # ------------------------------------------------------------------
    @async_retry(max_attempts=2, delay=0.5, exceptions=(Exception,))
    async def save_from_context(
        self,
        context: BrowserContext,
        phone: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        metadata: Optional[dict] = None,
        storage_state: Optional[StorageState] = None,
    ) -> SessionRecord:
        """
        ذخیره Session از یک BrowserContext.

        این متد معمولاً پس از Login موفق صدا زده می‌شود.
        """
        try:
            if storage_state is None:
                raw_state = await context.storage_state()
                storage_state = StorageState.from_playwright(raw_state)

            # Playwright omits sessionStorage from storage_state. Capture it
            # from every currently open same-context page before persistence.
            for page in context.pages:
                try:
                    session_data = await page.evaluate("""
                        () => ({
                            origin: window.location.origin,
                            data: Object.fromEntries(
                                Array.from({length: sessionStorage.length}, (_, i) => {
                                    const key = sessionStorage.key(i);
                                    return [key, key === null ? null : sessionStorage.getItem(key)];
                                })
                            ),
                        })
                    """)
                    origin = session_data.get("origin")
                    data = session_data.get("data")
                    if origin and data:
                        storage_state.session_storage[origin] = data
                except PlaywrightError:
                    # A page may have closed while the context is being saved.
                    continue

            # Preserve all available auth state. Tokens are normally already
            # represented in cookies/localStorage; explicit fields make DB
            # inspection and comparison deterministic as well.
            if access_token is None or refresh_token is None:
                for values in list(storage_state.local_storage.values()) + list(storage_state.session_storage.values()):
                    for key, value in values.items():
                        key_lower = key.lower()
                        if access_token is None and "access" in key_lower and "token" in key_lower:
                            access_token = value
                        elif refresh_token is None and "refresh" in key_lower and "token" in key_lower:
                            refresh_token = value

            record = SessionRecord(
                id=None,
                platform=self._platform,
                phone=phone,
                storage_state=storage_state,
                access_token=access_token,
                refresh_token=refresh_token,
                status=SessionStatus.VALID,
                metadata=metadata or {},
            )

            saved = self._db.save(record)
            logger.info(
                "[%s] Session saved: phone=%s cookies=%d",
                self._platform, phone, len(storage_state.cookies),
            )
            return saved

        except PlaywrightError as e:
            logger.error("[%s] Failed to extract storage state: %s", self._platform, e)
            raise
        except Exception as e:
            logger.exception("[%s] Unexpected error saving session: %s", self._platform, e)
            raise

    # ------------------------------------------------------------------
    # ذخیره Session در دیتابیس + export فایل JSON (برای backward compatibility)
    # ------------------------------------------------------------------
    async def save_and_export(
        self,
        context: BrowserContext,
        phone: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        metadata: Optional[dict] = None,
        storage_state: Optional[StorageState] = None,
    ) -> tuple[SessionRecord, Path]:
        """
        ذخیره Session در SQLite و هم‌زمان export به فایل JSON ثابت.

        فایل JSON در مسیر `data/sessions/{platform}_{phone}_session.json` نوشته می‌شود
        تا مطابق انتظار README و کاربران قابل مشاهده باشد. این فایل همچنین
        می‌تواند مستقیماً به `browser.new_context(storage_state=...)` پاس داده شود.

        نکته: نوشتن فایل JSON به صورت non-fatal انجام می‌شود؛ اگر شکست بخورد،
        فقط لاگ می‌شود و Login موفق باقی می‌ماند (چون Session در SQLite ذخیره شده).

        Returns:
            tuple of (SessionRecord, Path to JSON file یا placeholder در صورت شکست)
        """
        # گام ۱: ذخیره در SQLite (با retry و مدیریت خطا) - این مرحله critical است
        record = await self.save_from_context(
            context=context,
            phone=phone,
            access_token=access_token,
            refresh_token=refresh_token,
            metadata=metadata,
            storage_state=storage_state,
        )

        # گام ۲: export به فایل JSON ثابت در SESSIONS_DIR (non-fatal)
        fallback_path = SESSIONS_DIR / f"{self._platform}_session.json"
        try:
            json_path = await self._write_persistent_json(record)
        except Exception as e:
            logger.warning(
                "[%s] Session saved to DB but JSON export failed: %s",
                self._platform, e,
            )
            json_path = fallback_path
        return record, json_path

    async def _write_persistent_json(self, record: SessionRecord) -> Path:
        """
        نوشتن storage_state به صورت فایل JSON دائمی در SESSIONS_DIR.

        مسیر فایل: data/sessions/{platform}_{phone}_session.json
        """
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = SESSIONS_DIR / f"{self._platform}_{record.phone}_session.json"

        data = record.storage_state.to_playwright()
        # افزودن metadata برای debug راحت‌تر
        payload = {
            **data,
            "__meta__": {
                "platform": record.platform,
                "phone": record.phone,
                "session_id": record.id,
                "status": record.status.value,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                # Playwright cannot consume this field directly; the DB loader
                # restores it with an init script. Keep it in exports for a
                # complete, inspectable backup.
                "session_storage": record.storage_state.session_storage,
            },
        }

        # نوشتن اتمیک: اول به فایل موقت، بعد rename
        tmp_path = file_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(file_path)
            logger.info(
                "[%s] Session JSON exported to %s (cookies=%d)",
                self._platform, file_path, len(record.storage_state.cookies),
            )
            return file_path
        except Exception as e:
            logger.error(
                "[%s] Failed to export session JSON to %s: %s",
                self._platform, file_path, e,
            )
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    # ------------------------------------------------------------------
    # بارگذاری Session
    # ------------------------------------------------------------------
    def load(self, phone: Optional[str] = None) -> Optional[SessionRecord]:
        """
        بارگذاری Session.

        اگر phone داده شود، Session آن شماره بارگذاری می‌شود.
        در غیر این صورت، آخرین Session معتبر platform بارگذاری می‌شود.
        """
        if phone:
            record = self._db.get(self._platform, phone)
        else:
            record = self._db.get_latest(self._platform)

        if record:
            self._db.touch(record.id)
            record.touch()
            logger.info(
                "[%s] Session loaded: phone=%s status=%s",
                self._platform, record.phone, record.status.value,
            )
        else:
            logger.info("[%s] No session found (phone=%s)", self._platform, phone)

        return record

    def list_sessions(self) -> list[SessionRecord]:
        """لیست تمام Sessionهای این platform."""
        return self._db.list_all(self._platform)

    # ------------------------------------------------------------------
    # اعتبارسنجی
    # ------------------------------------------------------------------
    async def validate(self, record: SessionRecord, page) -> SessionStatus:
        """
        اعتبارسنجی یک Session با تست واقعی روی سایت.

        این متد یک صفحه protected را باز می‌کند و بررسی می‌کند
        آیا کاربر واقعاً لاگین است یا خیر.
        """
        if not record or record.id is None:
            return SessionStatus.INVALID

        try:
            status = await self._validator.validate(page)
        except PlaywrightError as e:
            logger.warning(
                "[%s] Validation failed with playwright error: %s",
                self._platform, e,
            )
            status = SessionStatus.UNKNOWN

        # به‌روزرسانی در DB
        self._db.update_status(record.id, status, reason="validation")
        record.status = status
        record.updated_at = datetime.now()

        logger.info(
            "[%s] Session validated: phone=%s -> %s",
            self._platform, record.phone, status.value,
        )
        return status

    # ------------------------------------------------------------------
    # تغییر وضعیت
    # ------------------------------------------------------------------
    def mark_invalid(self, record: SessionRecord, reason: str = "manual") -> bool:
        """علامت‌گذاری Session به عنوان نامعتبر."""
        if not record or record.id is None:
            return False
        ok = self._db.update_status(record.id, SessionStatus.INVALID, reason)
        if ok:
            record.status = SessionStatus.INVALID
            logger.warning(
                "[%s] Session marked invalid: phone=%s reason=%s",
                self._platform, record.phone, reason,
            )
        return ok

    def mark_valid(self, record: SessionRecord) -> bool:
        """علامت‌گذاری Session به عنوان معتبر."""
        if not record or record.id is None:
            return False
        ok = self._db.update_status(record.id, SessionStatus.VALID, "manual")
        if ok:
            record.status = SessionStatus.VALID
        return ok

    # ------------------------------------------------------------------
    # ✨ FIXED: حذف کامل Session (DB + JSON)
    # ------------------------------------------------------------------
    def delete(self, record: SessionRecord) -> bool:
        """
        حذف کامل یک Session.

        این متد هم رکورد را از دیتابیس SQLite حذف می‌کند و هم
        فایل JSON مربوطه را از data/sessions/ پاک می‌کند.

        Args:
            record: SessionRecord برای حذف

        Returns:
            True اگر حذف با موفقیت انجام شد
        """
        if not record or record.id is None:
            return False

        # گام 1: حذف فایل JSON
        try:
            # الگوی نام فایل: {platform}_{phone}_session.json
            json_file = SESSIONS_DIR / f"{self._platform}_{record.phone}_session.json"
            if json_file.exists():
                json_file.unlink()
                logger.info(
                    "[%s] Session JSON file deleted: %s",
                    self._platform, json_file,
                )
        except Exception as e:
            logger.warning(
                "[%s] Failed to delete session JSON file: %s",
                self._platform, e,
            )
            # ادامه می‌دهیم - حذف DB مهم‌تر است

        # گام 2: حذف از دیتابیس
        ok = self._db.delete(record.id)
        if ok:
            logger.info(
                "[%s] Session completely deleted: phone=%s (DB + JSON)",
                self._platform, record.phone,
            )
        return ok

    def delete_by_phone(self, phone: str) -> bool:
        """
        حذف Session بر اساس phone.

        هم از دیتابیس و هم فایل JSON حذف می‌شود.

        Args:
            phone: شماره موبایل

        Returns:
            True اگر حذف با موفقیت انجام شد
        """
        # گام 1: حذف فایل JSON
        try:
            json_file = SESSIONS_DIR / f"{self._platform}_{phone}_session.json"
            if json_file.exists():
                json_file.unlink()
                logger.info(
                    "[%s] Session JSON file deleted: %s",
                    self._platform, json_file,
                )
        except Exception as e:
            logger.warning(
                "[%s] Failed to delete session JSON file: %s",
                self._platform, e,
            )

        # گام 2: حذف از دیتابیس
        ok = self._db.delete_by_key(self._platform, phone)
        if ok:
            logger.info(
                "[%s] Session completely deleted: phone=%s (DB + JSON)",
                self._platform, phone,
            )
        return ok

    # ------------------------------------------------------------------
    # Export برای Playwright
    # ------------------------------------------------------------------
    async def export_storage_state(self, record: SessionRecord) -> Path:
        """
        تولید فایل storage_state برای استفاده در Playwright BrowserContext.

        این فایل را می‌توان به `new_context(storage_state=...)` پاس داد.

        Returns:
            Path به فایل موقت JSON
        """
        if not record:
            raise ValueError("Cannot export storage state: no record")

        file_name = f"{self._platform}_{record.phone}_{id(record)}.json"
        file_path = TEMP_DIR / file_name

        data = record.storage_state.to_playwright()
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._temp_files.append(file_path)
        logger.debug("[%s] Exported storage state to %s", self._platform, file_path)
        return file_path

    async def apply_to_context(self, record: SessionRecord) -> dict:
        """
        تولید storage_state dict برای پاس دادن به BrowserContext.new_context().

        Returns:
            Dict مناسب برای پارامتر storage_state
        """
        if not record:
            raise ValueError("Cannot apply to context: no record")
        return record.storage_state.to_playwright()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup_temp_files(self) -> None:
        """پاک کردن فایل‌های موقت."""
        for f in self._temp_files:
            try:
                if f.exists():
                    f.unlink()
            except OSError as e:
                logger.warning("Failed to delete temp file %s: %s", f, e)
        self._temp_files.clear()

    def __del__(self):
        try:
            self.cleanup_temp_files()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def get_history(self, record: SessionRecord, limit: int = 50) -> list[dict]:
        """دریافت تاریخچه تغییرات یک Session."""
        if not record or record.id is None:
            return []
        return self._db.get_history(record.id, limit)
