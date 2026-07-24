"""
SettingsManager — ذخیره و بازیابی تنظیمات اتوماسیون برای هر شماره + پلتفرم.

هر شماره تلفن روی هر پلتفرم فایل JSON اختصاصی دارد:
  data/settings/divar_09228625372.json
  data/settings/sheypoor_09228625372.json

برای سازگاری با نسخه‌های قدیمی، اگر فایل قدیمی data/settings/{phone}.json
وجود داشته باشد و پلتفرم داخل آن با پلتفرم درخواستی یکی باشد، خوانده می‌شود.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

SETTINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "settings"
SUPPORTED_PLATFORMS = {"divar", "sheypoor"}

DEFAULT_SETTINGS: Dict = {
    "platform": "divar",
    "cities": [],
    "category_slug": None,
    "category_name": "همه دسته‌ها",
    "pages": 3,
    "chat_enabled": True,
    "chat_message": "",
    "extract_phone": True,
    "max_phones": 10,
    "max_chats": 10,
    "sync_phone_chat": True,
    "schedule_interval": 0,
    "cookie_interval": 60,
}


def _safe_platform(platform: Optional[str]) -> str:
    platform = (platform or "divar").strip().lower()
    return platform if platform in SUPPORTED_PLATFORMS else "divar"


def _file_path(phone: str, platform: Optional[str] = None) -> Path:
    """مسیر فایل تنظیمات جدید: {platform}_{phone}.json"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return SETTINGS_DIR / f"{_safe_platform(platform)}_{phone}.json"


def _legacy_file_path(phone: str) -> Path:
    """مسیر قدیمی نسخه‌های قبل: {phone}.json"""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return SETTINGS_DIR / f"{phone}.json"


def save(phone: str, settings: Dict, platform: Optional[str] = None) -> None:
    """ذخیره تنظیمات یک شماره برای پلتفرم مشخص.

    اگر platform پاس داده نشود، از settings['platform'] استفاده می‌شود.
    """
    plat = _safe_platform(platform or settings.get("platform"))
    payload = dict(DEFAULT_SETTINGS)
    payload.update(settings or {})
    payload["platform"] = plat

    path = _file_path(phone, plat)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load(phone: str, platform: Optional[str] = None) -> Dict:
    """بارگذاری تنظیمات یک شماره برای پلتفرم مشخص.

    نکته مهم: تنظیمات دیوار و شیپور جدا هستند تا انتخاب پلتفرم شیپور،
    تنظیمات ذخیره‌شده دیوار همان شماره را لود نکند و باعث تغییر پلتفرم/هنگ UI نشود.
    """
    plat = _safe_platform(platform)
    result = dict(DEFAULT_SETTINGS)
    result["platform"] = plat

    path = _file_path(phone, plat)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.update(data)
            result["platform"] = plat
            return result
        except Exception:
            return result

    # سازگاری با فایل‌های قدیمی {phone}.json؛ فقط اگر پلتفرم داخل فایل یکی بود.
    legacy = _legacy_file_path(phone)
    if legacy.exists():
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                data = json.load(f)
            legacy_platform = _safe_platform(data.get("platform"))
            if legacy_platform == plat:
                result.update(data)
                result["platform"] = plat
        except Exception:
            pass

    return result


def current_settings(phone: str, platform: Optional[str] = None) -> Dict:
    """تنظیمات فعلی (همان load — alias)."""
    return load(phone, platform=platform)
