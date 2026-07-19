"""
اسکریپت دریافت لیست شهرها از API دیوار.

نحوه استفاده:
    python fetch_cities.py

خروجی: data/cities.json
"""

import json
import requests
from pathlib import Path

API_URL = "https://api.divar.ir/v8/postlist/w/places"
OUTPUT_FILE = Path(__file__).parent / "data" / "cities.json"


def fetch_cities() -> dict:
    """دریافت لیست شهرها از API دیوار."""
    print("📡 در حال دریافت لیست شهرها از API دیوار...")
    
    try:
        response = requests.post(
            API_URL,
            headers={"Content-Type": "application/json"},
            json={},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ دریافت شد! ({len(json.dumps(data))} bytes)")
        return data
    
    except requests.exceptions.RequestException as e:
        print(f"❌ خطا در دریافت: {e}")
        raise


def extract_cities(data: dict) -> list[dict]:
    """
    استخراج لیست شهرها از پاسخ API.
    
    ساختار پاسخ API ممکن است متفاوت باشد.
    این تابع سعی می‌کند شهرها را از ساختارهای مختلف استخراج کند.
    """
    cities = []
    
    def _extract_recursive(obj, path=""):
        """بازگشتی برای پیدا کردن شهرها در ساختار تودرتو."""
        if isinstance(obj, dict):
            # بررسی آیا این یک شهر است
            if "id" in obj and ("name" in obj or "title" in obj):
                city = {
                    "id": obj.get("id"),
                    "name": obj.get("name") or obj.get("title") or obj.get("label", ""),
                    "slug": obj.get("slug") or obj.get("key", ""),
                    "parent_id": obj.get("parent_id"),
                }
                if city["id"] and city["name"]:
                    cities.append(city)
            
            # ادامه جستجو
            for key, value in obj.items():
                _extract_recursive(value, f"{path}.{key}")
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _extract_recursive(item, f"{path}[{i}]")
    
    _extract_recursive(data)
    
    # حذف تکراری‌ها
    seen_ids = set()
    unique_cities = []
    for city in cities:
        if city["id"] not in seen_ids:
            seen_ids.add(city["id"])
            unique_cities.append(city)
    
    # مرتب‌سازی بر اساس نام
    unique_cities.sort(key=lambda c: c["name"])
    
    return unique_cities


def save_cities(cities: list[dict], filepath: Path):
    """ذخیره لیست شهرها در فایل JSON."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    output = {
        "count": len(cities),
        "cities": cities,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"💾 ذخیره شد: {filepath}")
    print(f"📊 تعداد شهرها: {len(cities)}")


def main():
    print("=" * 60)
    print("🏙️  دریافت لیست شهرهای دیوار")
    print("=" * 60)
    
    # دریافت از API
    raw_data = fetch_cities()
    
    # ذخیره پاسخ خام (برای debug)
    raw_file = OUTPUT_FILE.parent / "places_raw.json"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"💾 پاسخ خام ذخیره شد: {raw_file}")
    
    # استخراج شهرها
    cities = extract_cities(raw_data)
    
    if not cities:
        print("⚠️ هیچ شهری پیدا نشد! ساختار پاسخ API را بررسی کنید:")
        print(json.dumps(raw_data, ensure_ascii=False, indent=2)[:2000])
        return
    
    # نمایش چند نمونه
    print("\n📋 نمونه شهرها:")
    for city in cities[:10]:
        print(f"  • ID={city['id']}, نام={city['name']}, slug={city['slug']}")
    if len(cities) > 10:
        print(f"  ... و {len(cities) - 10} شهر دیگر")
    
    # ذخیره
    save_cities(cities, OUTPUT_FILE)
    
    print("\n✅ تمام شد!")
    print(f"📁 فایل خروجی: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
