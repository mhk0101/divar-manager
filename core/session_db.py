"""
SessionDB - لایه دیتابیس SQLite برای Session Manager.

این ماژول مسئول تمام عملیات خواندن و نوشتن روی دیتابیس SQLite است.
از asyncio و aiosqlite استفاده می‌کنیم تا عملیات DB async باشند.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

from config.settings import SESSION_DB_PATH
from core.session_models import SessionRecord, SessionStatus, StorageState

logger = logging.getLogger("divar.session.db")


class SessionDB:
    """لایه دیتابیس برای مدیریت Sessionها."""

    SCHEMA_VERSION = 1

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        platform        TEXT    NOT NULL,
        phone           TEXT    NOT NULL,
        storage_state   TEXT    NOT NULL,
        access_token    TEXT,
        refresh_token   TEXT,
        status          TEXT    NOT NULL DEFAULT 'unknown',
        created_at      TEXT    NOT NULL,
        updated_at      TEXT    NOT NULL,
        last_used_at    TEXT,
        metadata        TEXT    NOT NULL DEFAULT '{}',
        UNIQUE(platform, phone)
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_platform
        ON sessions(platform);

    CREATE INDEX IF NOT EXISTS idx_sessions_phone
        ON sessions(phone);

    CREATE INDEX IF NOT EXISTS idx_sessions_status
        ON sessions(status);

    CREATE TABLE IF NOT EXISTS session_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  INTEGER NOT NULL,
        action      TEXT    NOT NULL,
        details     TEXT,
        timestamp   TEXT    NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
    );
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or SESSION_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    # ------------------------------------------------------------------
    # اتصال به DB
    # ------------------------------------------------------------------
    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript(self.SCHEMA_SQL)
        logger.info("Session DB initialized at %s", self._db_path)

    # ------------------------------------------------------------------
    # تبدیل ردیف‌ها به SessionRecord
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> SessionRecord:
        metadata_raw = row["metadata"] or "{}"
        try:
            metadata = json.loads(metadata_raw)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        storage_state = StorageState.from_json(row["storage_state"])

        return SessionRecord(
            id=row["id"],
            platform=row["platform"],
            phone=row["phone"],
            storage_state=storage_state,
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            status=SessionStatus(row["status"]),
            created_at=_parse_dt(row["created_at"]),
            updated_at=_parse_dt(row["updated_at"]),
            last_used_at=_parse_dt(row["last_used_at"]),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def save(self, record: SessionRecord) -> SessionRecord:
        """
        ذخیره یا به‌روزرسانی یک Session.

        اگر Session با همان (platform, phone) وجود داشت، به‌روز می‌شود.
        در غیر این صورت یک رکورد جدید ساخته می‌شود.
        """
        now = datetime.now()
        storage_json = record.storage_state.to_json()
        metadata_json = json.dumps(record.metadata, ensure_ascii=False, default=str)

        with self._connection() as conn:
            existing = conn.execute(
                "SELECT id, created_at, updated_at, last_used_at, storage_state, access_token, refresh_token, status, metadata "
                "FROM sessions WHERE platform=? AND phone=?",
                (record.platform, record.phone),
            ).fetchone()

            if existing:
                unchanged = (
                    existing["storage_state"] == storage_json
                    and existing["access_token"] == record.access_token
                    and existing["refresh_token"] == record.refresh_token
                    and existing["status"] == record.status.value
                    and existing["metadata"] == metadata_json
                )
                record.id = existing["id"]
                record.created_at = _parse_dt(existing["created_at"])
                if unchanged:
                    record.updated_at = _parse_dt(existing["updated_at"])
                    record.last_used_at = _parse_dt(existing["last_used_at"])
                    logger.info("Session unchanged: platform=%s phone=%s id=%s", record.platform, record.phone, record.id)
                    self._log_action(conn, record.id, "UNCHANGED", None)
                    return record

                conn.execute("""
                    UPDATE sessions SET
                        storage_state = ?,
                        access_token  = ?,
                        refresh_token = ?,
                        status        = ?,
                        updated_at    = ?,
                        last_used_at  = ?,
                        metadata      = ?
                    WHERE platform=? AND phone=?
                """, (
                    storage_json,
                    record.access_token,
                    record.refresh_token,
                    record.status.value,
                    now.isoformat(),
                    (record.last_used_at or now).isoformat(),
                    metadata_json,
                    record.platform,
                    record.phone,
                ))
                record.id = existing["id"]
                record.updated_at = now
                record.created_at = _parse_dt(existing["created_at"])
                logger.info(
                    "Session updated: platform=%s phone=%s id=%s",
                    record.platform, record.phone, record.id,
                )
                self._log_action(conn, record.id, "UPDATED", f"status={record.status.value}")
            else:
                cursor = conn.execute("""
                    INSERT INTO sessions (
                        platform, phone, storage_state,
                        access_token, refresh_token, status,
                        created_at, updated_at, last_used_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.platform,
                    record.phone,
                    storage_json,
                    record.access_token,
                    record.refresh_token,
                    record.status.value,
                    now.isoformat(),
                    now.isoformat(),
                    (record.last_used_at or now).isoformat(),
                    metadata_json,
                ))
                record.id = cursor.lastrowid
                record.created_at = now
                record.updated_at = now
                logger.info(
                    "Session created: platform=%s phone=%s id=%s",
                    record.platform, record.phone, record.id,
                )
                self._log_action(conn, record.id, "CREATED", f"status={record.status.value}")

        return record

    def get(self, platform: str, phone: str) -> Optional[SessionRecord]:
        """دریافت Session برای یک platform و phone مشخص."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE platform=? AND phone=?",
                (platform, phone),
            ).fetchone()
            if not row:
                return None
            record = self._row_to_record(row)
            self._log_action(conn, record.id, "LOADED", None)
            return record

    def get_latest(self, platform: str) -> Optional[SessionRecord]:
        """دریافت آخرین Session معتبر برای یک platform."""
        with self._connection() as conn:
            row = conn.execute("""
                SELECT * FROM sessions
                WHERE platform=? AND status IN ('valid', 'unknown', 'needs_refresh')
                ORDER BY last_used_at DESC
                LIMIT 1
            """, (platform,)).fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def list_all(self, platform: Optional[str] = None) -> List[SessionRecord]:
        """لیست تمام Sessionها (اختیاری: فیلتر بر اساس platform)."""
        with self._connection() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE platform=? ORDER BY last_used_at DESC",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY last_used_at DESC"
                ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def update_status(self, session_id: int, status: SessionStatus, reason: str = "") -> bool:
        """به‌روزرسانی وضعیت یک Session."""
        now = datetime.now()
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET status=?, updated_at=? WHERE id=?",
                (status.value, now.isoformat(), session_id),
            )
            if cursor.rowcount == 0:
                return False
            self._log_action(conn, session_id, "STATUS_CHANGE", f"{status.value}: {reason}")
            logger.info(
                "Session status changed: id=%s -> %s (%s)",
                session_id, status.value, reason,
            )
            return True

    def touch(self, session_id: int) -> bool:
        """به‌روزرسانی زمان آخرین استفاده."""
        now = datetime.now()
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET last_used_at=? WHERE id=?",
                (now.isoformat(), session_id),
            )
            return cursor.rowcount > 0

    def delete(self, session_id: int) -> bool:
        """حذف یک Session."""
        with self._connection() as conn:
            self._log_action(conn, session_id, "DELETED", None)
            cursor = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            if cursor.rowcount:
                logger.info("Session deleted: id=%s", session_id)
            return cursor.rowcount > 0

    def delete_by_key(self, platform: str, phone: str) -> bool:
        """حذف Session بر اساس platform و phone."""
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE platform=? AND phone=?",
                (platform, phone),
            )
            if cursor.rowcount:
                logger.info("Session deleted: platform=%s phone=%s", platform, phone)
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # History (Audit Log)
    # ------------------------------------------------------------------
    def _log_action(self, conn: sqlite3.Connection, session_id: Optional[int],
                    action: str, details: Optional[str]) -> None:
        if session_id is None:
            return
        try:
            conn.execute(
                "INSERT INTO session_history (session_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, action, details, datetime.now().isoformat()),
            )
        except Exception as e:
            logger.warning("Failed to log action %s for session %s: %s", action, session_id, e)

    def get_history(self, session_id: int, limit: int = 50) -> List[dict]:
        """دریافت تاریخچه تغییرات یک Session."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT action, details, timestamp FROM session_history "
                "WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
