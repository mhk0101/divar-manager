"""
SettingsManager — ذخیره و بازیابی تنظیمات اتوماسیون برای هر شماره + پلتفرم.

هر شماره تلفن روی هر پلتفرم فایل JSON اختصاصی دارد:
  data/settings/divar_09228625372.json
  data/settings/sheypoor_09228625372.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

SETTINGS_DIR = Path(__file__).resolve().parent.parent / "data" / "settings"

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
}


def _file_path(phone: str) -> Path:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    return SETTINGS_DIR / f"{phone}.json"


def save(phone: str, settings: Dict) -> None:
    """ذخیره تنظیمات یک شماره."""
    path = _file_path(phone)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load(phone: str) -> Dict:
    """بارگذاری تنظیمات یک شماره. در صورت نبود، پیش‌فرض برمی‌گرداند."""
    path = _file_path(phone)
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # merge with defaults for any missing keys
        result = dict(DEFAULT_SETTINGS)
        result.update(data)
        return result
    except Exception:
        return dict(DEFAULT_SETTINGS)


def current_settings(phone: str) -> Dict:
    """تنظیمات فعلی (همان load — alias)."""
    return load(phone)
