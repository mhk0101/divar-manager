"""
اسکریپت دریافت و پردازش دسته بندی ها و زیردسته های شیپور از API.

نحوه استفاده:
    python fetch_sheypoor_categories.py

ورودی: API رسمی شیپور (https://www.sheypoor.com/api/v10.0.0/general/categories)
خروجی: data/sheypoor_categories.json
"""

import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

API_URL = "https://www.sheypoor.com/api/v10.0.0/general/categories"
OUTPUT_FILE = Path(__file__).parent / "data" / "sheypoor_categories.json"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def fetch_categories_api() -> dict:
    """دریافت ساختار کامل دسته‌بندی‌ها و زیردسته‌ها از API شیپور."""
    print("📡 در حال دریافت لیست دسته‌بندی‌ها و زیردسته‌ها از API شیپور...")
    req = urllib.request.Request(API_URL, headers=HEADERS)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            print("✅ اطلاعات دسته‌بندی‌های شیپور با موفقیت دریافت شد!")
            return data
    except urllib.error.URLError as e:
        print(f"❌ خطا در برقراری ارتباط با API شیپور: {e}")
        raise


def process_categories(raw_data: dict) -> dict:
    """
    پردازش هوشمند و جامع دسته‌ها و زیردسته‌های شیپور.
    
    آیتم‌های موجود در data آرایه دسته‌های اصلی (سطح ۱) هستند
    و آیتم‌های موجود در included آرایه زیردسته‌ها (سطح ۲، ۳ و ...) می‌باشند.
    """
    data_items = raw_data.get("data", [])
    included_items = raw_data.get("included", [])

    if isinstance(data_items, dict):
        data_items = [data_items]
    if not isinstance(included_items, list):
        included_items = []

    all_items_map = {}
    root_ids = set()

    # ۱. پردازش دسته‌های اصلی (Root Categories در data)
    for item in data_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        if not item_id or item_id == "None":
            continue
        attrs = item.get("attributes", {})
        root_ids.add(item_id)
        all_items_map[item_id] = {
            "id": item_id,
            "name": attrs.get("name") or attrs.get("title") or item.get("name", ""),
            "slug": attrs.get("slug") or attrs.get("key") or item.get("slug", ""),
            "is_root": True,
            "parent_id": None,
        }

    # ۲. پردازش زیردسته‌ها (Subcategories در included)
    for item in included_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        if not item_id or item_id == "None":
            continue
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})

        p_id = None
        p_data = rels.get("parent", {}).get("data", {})
        if isinstance(p_data, dict) and p_data.get("id"):
            p_id = str(p_data.get("id"))
        elif attrs.get("parent_id") or attrs.get("parentId"):
            p_id = str(attrs.get("parent_id") or attrs.get("parentId"))

        all_items_map[item_id] = {
            "id": item_id,
            "name": attrs.get("name") or attrs.get("title") or item.get("name", ""),
            "slug": attrs.get("slug") or attrs.get("key") or item.get("slug", ""),
            "is_root": False,
            "parent_id": p_id,
        }

    # تابع پیدا کردن دسته اصلی والد (Root Ancestor)
    def find_root_ancestor(item_id: str, visited=None) -> Optional[dict]:
        if visited is None:
            visited = set()
        if item_id in visited:
            return None
        visited.add(item_id)

        obj = all_items_map.get(item_id)
        if not obj:
            return None
        if obj["is_root"]:
            return obj
        if obj["parent_id"]:
            return find_root_ancestor(obj["parent_id"], visited)
        return None

    flat_categories = []

    # اضافه کردن دسته‌های اصلی
    for rid in root_ids:
        root_obj = all_items_map[rid]
        flat_categories.append({
            "id": root_obj["id"],
            "slug": root_obj["slug"],
            "name": root_obj["name"],
            "category": "اصلی",
            "type": "main",
            "parent_slug": None,
        })

    # اضافه کردن زیردسته‌ها
    for item_id, obj in all_items_map.items():
        if obj["is_root"]:
            continue

        root_parent = find_root_ancestor(item_id)
        parent_obj = all_items_map.get(obj["parent_id"]) if obj["parent_id"] else None

        category_label = root_parent["name"] if root_parent else (parent_obj["name"] if parent_obj else "اصلی")
        parent_slug = parent_obj["slug"] if parent_obj else (root_parent["slug"] if root_parent else None)

        flat_categories.append({
            "id": obj["id"],
            "slug": obj["slug"],
            "name": obj["name"],
            "category": category_label,
            "type": "sub",
            "parent_slug": parent_slug,
        })

    return {
        "count": len(flat_categories),
        "main_count": len(root_ids),
        "sub_count": len(flat_categories) - len(root_ids),
        "categories": flat_categories,
    }


def save_categories(data: dict, filepath: Path):
    """ذخیره ساختار دسته‌بندی‌ها در فایل JSON."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 فایل دسته‌بندی‌های شیپور ذخیره شد: {filepath}")
    print(f"📊 دسته‌های اصلی: {data['main_count']} | زیردسته‌ها: {data['sub_count']} | مجموع: {data['count']}")


def main():
    print("=" * 60)
    print("📂 دریافت و پردازش دسته‌بندی‌ها و زیردسته‌های شیپور")
    print("=" * 60)

    try:
        raw_data = fetch_categories_api()
        processed = process_categories(raw_data)
        save_categories(processed, OUTPUT_FILE)
        print("\n✅ عملیات با موفقیت انجام شد.")
    except Exception as e:
        print(f"\n⚠️ خطا در پردازش: {e}")


if __name__ == "__main__":
    main()
