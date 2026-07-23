"""
FingerprintManager — تولید fingerprint یکتا و واقعی برای هر شماره + پلتفرم.

هر شماره تلفن روی هر پلتفرم (دیوار/شیپور) یک fingerprint اختصاصی دریافت می‌کند
که بین اجراهای مختلف یکسان می‌ماند (persistent) ولی بین شماره‌ها متفاوت است.

ویژگی‌ها:
- User-Agent متفاوت (Chrome/Firefox/Edge، ویندوز/مک/لینوکس، نسخه‌های مختلف)
- Viewport متفاوت (رزولوشن‌های واقعی مانیتور)
- Platform متفاوت (Win32/MacIntel/Linux)
- Accept-Language متفاوت
- Color Scheme متفاوت
- Device Scale Factor متفاوت
- Fingerprintها در فایل JSON ذخیره می‌شوند (پایدار بین اجراها)
"""

from __future__ import annotations

import json
import hashlib
import random
from pathlib import Path
from typing import Dict, Optional

FINGERPRINT_DB_FILE = Path(__file__).resolve().parent.parent / "data" / "fingerprints.json"

# ── User-Agent های واقعی و متنوع ──
_USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# ── Viewportهای واقعی ──
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1600, "height": 900},
    {"width": 1680, "height": 1050},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 720},
    {"width": 1920, "height": 1200},
]

# ── Accept-Language های متنوع ──
_ACCEPT_LANGUAGES = [
    "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "fa-IR,fa;q=0.9,en;q=0.8",
    "fa-IR,fa;q=0.8,en-US;q=0.6,en;q=0.4",
    "fa;q=0.9,en-US;q=0.5",
    "en-US,en;q=0.9,fa;q=0.8",
]

# ── Color Scheme ──
_COLOR_SCHEMES = ["light", "dark", "no-preference"]

# ── Device Scale Factor ──
_DEVICE_SCALE_FACTORS = [1.0, 1.0, 1.0, 1.25, 1.5, 2.0]


def _make_key(phone: str, platform: str) -> str:
    """ساخت کلید یکتا از شماره و پلتفرم."""
    raw = f"{phone}:{platform}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _seeded_pick(key: str, items: list, index: int = 0) -> object:
    """انتخاب آیتم از لیست بر اساس hash کلید (قطعی و تکرارپذیر)."""
    h = hashlib.sha256(f"{key}:{index}".encode()).digest()
    num = int.from_bytes(h[:4], "big")
    return items[num % len(items)]


def generate_fingerprint(phone: str, platform: str) -> Dict:
    """
    تولید fingerprint یکتا برای یک شماره + پلتفرم خاص.
    نتیجه همیشه برای همان phone+platform یکسان است (deterministic).
    """
    key = _make_key(phone, platform)

    user_agent = _seeded_pick(key, _USER_AGENTS, 0)
    viewport = _seeded_pick(key, _VIEWPORTS, 1)
    accept_language = _seeded_pick(key, _ACCEPT_LANGUAGES, 2)
    color_scheme = _seeded_pick(key, _COLOR_SCHEMES, 3)
    device_scale_factor = _seeded_pick(key, _DEVICE_SCALE_FACTORS, 4)

    # تشخیص platform از User-Agent
    ua_lower = str(user_agent).lower()
    if "macintosh" in ua_lower or "mac os x" in ua_lower:
        os_platform = "MacIntel"
    elif "linux" in ua_lower:
        os_platform = "Linux x86_64"
    else:
        os_platform = "Win32"

    return {
        "phone": phone,
        "platform": platform,
        "user_agent": user_agent,
        "viewport": viewport,
        "accept_language": accept_language,
        "color_scheme": color_scheme,
        "device_scale_factor": device_scale_factor,
        "os_platform": os_platform,
    }


class FingerprintManager:
    """مدیریت fingerprintها با ذخیره‌سازی پایدار در فایل JSON."""

    def __init__(self):
        self._db: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        if FINGERPRINT_DB_FILE.exists():
            try:
                with open(FINGERPRINT_DB_FILE, "r", encoding="utf-8") as f:
                    self._db = json.load(f)
            except Exception:
                self._db = {}

    def _save(self):
        FINGERPRINT_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FINGERPRINT_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self._db, f, ensure_ascii=False, indent=2)

    def get(self, phone: str, platform: str) -> Dict:
        """دریافت fingerprint برای یک شماره + پلتفرم. در صورت نبود، تولید و ذخیره می‌کند."""
        key = f"{phone}::{platform}"
        if key not in self._db:
            self._db[key] = generate_fingerprint(phone, platform)
            self._save()
        return self._db[key]
