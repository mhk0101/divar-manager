"""
Session Models - مدل‌های داده برای Session Manager.

تمام ساختارهای داده‌ای که در Session Manager استفاده می‌شوند اینجا تعریف شده‌اند.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(str, Enum):
    """وضعیت‌های ممکن یک Session."""

    VALID = "valid"                 # معتبر و قابل استفاده
    NEEDS_REFRESH = "needs_refresh" # نیاز به به‌روزرسانی
    EXPIRED = "expired"             # منقضی شده
    INVALID = "invalid"             # نامعتبر (نیاز به Login مجدد)
    UNKNOWN = "unknown"             # وضعیت ناشناخته (هنوز بررسی نشده)


@dataclass
class Cookie:
    """یک Cookie."""
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None
    http_only: bool = False
    secure: bool = False
    same_site: str = "Lax"

    def to_playwright(self) -> Dict[str, Any]:
        """تبدیل به فرمت قابل استفاده در Playwright."""
        data = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
        }
        if self.expires is not None:
            data["expires"] = self.expires
        if self.http_only:
            data["httpOnly"] = True
        if self.secure:
            data["secure"] = True
        if self.same_site:
            data["sameSite"] = self.same_site
        return data


@dataclass
class StorageState:
    """
    وضعیت کامل ذخیره‌سازی مرورگر.

    شامل Cookieها، LocalStorage و SessionStorage.
    """
    cookies: List[Cookie] = field(default_factory=list)
    local_storage: Dict[str, Dict[str, str]] = field(default_factory=dict)  # origin -> {key: value}
    session_storage: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def to_playwright(self) -> Dict[str, Any]:
        """تبدیل به فرمت storage_state قابل استفاده در Playwright BrowserContext."""
        origins = []
        # localStorage
        for origin, data in self.local_storage.items():
            origins.append({
                "origin": origin,
                "localStorage": [{"name": k, "value": v} for k, v in data.items()],
            })

        return {
            "cookies": [c.to_playwright() for c in self.cookies],
            "origins": origins,
        }

    @classmethod
    def from_playwright(cls, state: Dict[str, Any]) -> "StorageState":
        """ساخت از روی خروجی Playwright BrowserContext.storage_state()."""
        cookies = []
        for c in state.get("cookies", []):
            cookies.append(Cookie(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
                expires=c.get("expires"),
                http_only=c.get("httpOnly", False),
                secure=c.get("secure", False),
                same_site=c.get("sameSite", "Lax"),
            ))

        local_storage: Dict[str, Dict[str, str]] = {}
        for origin_data in state.get("origins", []):
            origin = origin_data.get("origin", "")
            items = {}
            for item in origin_data.get("localStorage", []):
                items[item.get("name", "")] = item.get("value", "")
            if items:
                local_storage[origin] = items

        session_storage = state.get("sessionStorage", {})
        if not isinstance(session_storage, dict):
            session_storage = {}
        return cls(cookies=cookies, local_storage=local_storage, session_storage=session_storage)

    def diff(self, other: "StorageState") -> Dict[str, Any]:
        """
        محاسبه تفاوت بین دو StorageState.

        برای تشخیص تغییرات Cookieها، LocalStorage و SessionStorage.
        """
        result: Dict[str, Any] = {"cookies": [], "local_storage": [], "session_storage": []}

        # Cookie diff
        old_cookies = {(c.name, c.domain): c.value for c in self.cookies}
        new_cookies = {(c.name, c.domain): c.value for c in other.cookies}

        for key, value in new_cookies.items():
            if key not in old_cookies:
                result["cookies"].append({"type": "added", "name": key[0], "domain": key[1]})
            elif old_cookies[key] != value:
                result["cookies"].append({"type": "changed", "name": key[0], "domain": key[1]})

        for key in old_cookies:
            if key not in new_cookies:
                result["cookies"].append({"type": "removed", "name": key[0], "domain": key[1]})

        # LocalStorage diff
        for origin in set(self.local_storage.keys()) | set(other.local_storage.keys()):
            old_data = self.local_storage.get(origin, {})
            new_data = other.local_storage.get(origin, {})
            if old_data != new_data:
                result["local_storage"].append({"origin": origin})

        # SessionStorage diff
        for origin in set(self.session_storage.keys()) | set(other.session_storage.keys()):
            old_data = self.session_storage.get(origin, {})
            new_data = other.session_storage.get(origin, {})
            if old_data != new_data:
                result["session_storage"].append({"origin": origin})

        return result

    def has_changes(self, other: "StorageState") -> bool:
        """بررسی اینکه آیا تغییری وجود دارد یا خیر."""
        diff = self.diff(other)
        return bool(diff["cookies"] or diff["local_storage"] or diff["session_storage"])

    def to_json(self) -> str:
        # ``sessionStorage`` is application metadata; it is deliberately not
        # passed to Playwright's storage_state option.
        payload = self.to_playwright()
        payload["sessionStorage"] = self.session_storage
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "StorageState":
        return cls.from_playwright(json.loads(data))


@dataclass
class SessionRecord:
    """
    یک رکورد Session ذخیره‌شده در دیتابیس.

    این کلاس تمام اطلاعات مربوط به یک Session کاربر برای یک پلتفرم خاص
    را نگهداری می‌کند.
    """
    id: Optional[int]
    platform: str                    # 'divar' یا 'sheypoor'
    phone: str                       # شماره موبایل
    storage_state: StorageState      # وضعیت کامل storage
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    status: SessionStatus = SessionStatus.UNKNOWN
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return self.status == SessionStatus.VALID

    def needs_login(self) -> bool:
        return self.status in (SessionStatus.EXPIRED, SessionStatus.INVALID)

    def touch(self) -> None:
        """به‌روزرسانی زمان آخرین استفاده."""
        self.last_used_at = datetime.now()
