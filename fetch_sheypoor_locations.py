"""
اسکریپت دریافت و پردازش لیست استان‌ها، شهرها و محله‌های شیپور از API.

نحوه استفاده:
    python fetch_sheypoor_locations.py

ورودی: API رسمی شیپور (https://www.sheypoor.com/api/v10.0.0/general/locations)
خروجی: data/sheypoor_cities.json
"""

import json
import urllib.request
import urllib.error
from pathlib import Path

API_URL = "https://www.sheypoor.com/api/v10.0.0/general/locations"
OUTPUT_FILE = Path(__file__).parent / "data" / "sheypoor_cities.json"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def fetch_locations_api() -> dict:
    """دریافت ساختار کامل موقعیت‌های مکانی از API شیپور."""
    print("📡 در حال دریافت لیست استان‌ها، شهرها و محله‌ها از API شیپور...")
    req = urllib.request.Request(API_URL, headers=HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            print("✅ اطلاعات موقعیت مکانی شیپور با موفقیت دریافت شد!")
            return data
    except urllib.error.URLError as e:
        print(f"❌ خطا در برقراری ارتباط با API شیپور: {e}")
        raise


def process_locations(raw_data: dict) -> dict:
    """پردازش و ساخت خروجی ساختاریافته از پاسخ API شیپور."""
    provinces_list = raw_data.get("data", {}).get("list", [])
    
    flat_cities = []
    tree_data = []
    
    for prov in provinces_list:
        p_id = prov.get("provinceID")
        p_name = prov.get("name", "")
        p_slug = prov.get("slug", "")
        
        prov_item = {
            "province_id": p_id,
            "name": p_name,
            "slug": p_slug,
            "cities": [],
        }
        
        for c in prov.get("cities", []):
            c_id = c.get("cityID")
            c_name = c.get("name", "")
            c_slug = c.get("slug", "")
            
            districts = []
            for d in c.get("districts", []):
                districts.append({
                    "district_id": d.get("districtID"),
                    "name": d.get("name", ""),
                })
            
            city_obj = {
                "id": c_id,
                "name": c_name,
                "slug": c_slug,
                "province_id": p_id,
                "province_name": p_name,
                "province_slug": p_slug,
                "display_name": f"{c_name} ({p_name})",
                "districts_count": len(districts),
                "districts": districts,
            }
            
            flat_cities.append(city_obj)
            prov_item["cities"].append(city_obj)
            
        tree_data.append(prov_item)
        
    flat_cities.sort(key=lambda x: x["name"])
    
    return {
        "count": len(flat_cities),
        "provinces_count": len(tree_data),
        "cities": flat_cities,
        "tree": tree_data,
    }


def save_locations(data: dict, filepath: Path):
    """ذخیره ساختار موقعیت‌ها در فایل JSON."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 فایل موقعیت‌های مکانی شیپور ذخیره شد: {filepath}")
    print(f"📊 تعداد شهرها: {data['count']} | تعداد استان‌ها: {data['provinces_count']}")


def main():
    print("=" * 60)
    print("🏙️ دریافت و پردازش شهرها و محله‌های شیپور")
    print("=" * 60)
    
    try:
        raw_data = fetch_locations_api()
        processed = process_locations(raw_data)
        save_locations(processed, OUTPUT_FILE)
        print("\n✅ عملیات با موفقیت انجام شد.")
    except Exception as e:
        print(f"\n⚠️ پردازش خودکار به علت عدم دسترسی انجام نشد: {e}")


if __name__ == "__main__":
    main()
