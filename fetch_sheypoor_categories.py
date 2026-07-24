"""
اسکریپت دریافت و پردازش دسته‌بندی‌ها و زیردسته‌های واقعی شیپور از API.

نحوه استفاده:
    python fetch_sheypoor_categories.py

ورودی:
    https://www.sheypoor.com/api/v10.0.0/general/categories

خروجی:
    data/sheypoor_categories.json

نکته مهم:
    پاسخ API شیپور داخل included فقط دسته‌بندی ندارد؛ Attributeها، فیلترها، برندها/مدل‌ها
    و مواردی مثل «قیمت از»، «رنگ»، «گیربکس» هم داخل included می‌آیند.
    این اسکریپت فقط resourceهایی را نگه می‌دارد که type == "category" دارند و slug معتبر دارند.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

API_URL = "https://www.sheypoor.com/api/v10.0.0/general/categories"
OUTPUT_FILE = Path(__file__).parent / "data" / "sheypoor_categories.json"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


def fetch_categories_api() -> dict:
    """دریافت ساختار کامل دسته‌بندی‌ها از API شیپور."""
    print("📡 در حال دریافت دسته‌بندی‌های شیپور از API رسمی...")
    req = urllib.request.Request(API_URL, headers=HEADERS)

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
            print("✅ اطلاعات دسته‌بندی‌های شیپور با موفقیت دریافت شد.")
            return data
    except urllib.error.URLError as e:
        print(f"❌ خطا در برقراری ارتباط با API شیپور: {e}")
        raise


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _is_category_resource(item: dict) -> bool:
    """فقط resourceهای واقعی category را قبول کن."""
    return isinstance(item, dict) and item.get("type") == "category"


def _extract_category_object(item: dict, *, is_root: bool = False) -> Optional[dict]:
    """تبدیل resource شیپور به آبجکت داخلی دسته‌بندی."""
    if not _is_category_resource(item):
        return None

    item_id = str(item.get("id") or "").strip()
    attrs = item.get("attributes") or {}
    name = (attrs.get("name") or attrs.get("title") or item.get("name") or "").strip()
    slug = (attrs.get("slug") or attrs.get("key") or item.get("slug") or "").strip()

    # مواردی مثل قیمت، رنگ، گیربکس و فیلترها معمولاً slug ندارند یا type آنها category نیست.
    # دسته‌بندی قابل استفاده در URL باید slug داشته باشد.
    if not item_id or not name or not slug:
        return None

    return {
        "id": item_id,
        "name": name,
        "slug": slug,
        "is_root": is_root,
        "parent_id": None,
    }


def _extract_children_ids(item: dict) -> list[str]:
    """خواندن children از relationships برای ساخت parent_map."""
    rels = item.get("relationships") or {}
    children = rels.get("children") or {}
    data = children.get("data") if isinstance(children, dict) else None
    result: list[str] = []

    for child in _as_list(data):
        if isinstance(child, dict) and child.get("type") == "category" and child.get("id"):
            result.append(str(child.get("id")))
    return result


def process_categories(raw_data: dict) -> dict:
    """
    پردازش دسته‌بندی‌های واقعی شیپور.

    الگوریتم:
    1. فقط itemهایی با type == category خوانده می‌شوند.
    2. itemهایی که slug ندارند حذف می‌شوند.
    3. parent/child از relationships.children ساخته می‌شود.
    4. Attributeها و فیلترهایی مثل «قیمت»، «رنگ»، «گیربکس» وارد خروجی نمی‌شوند.
    """
    data_items = _as_list(raw_data.get("data"))
    included_items = _as_list(raw_data.get("included"))

    all_items_map: dict[str, dict] = {}
    root_ids: list[str] = []
    parent_map: dict[str, str] = {}

    # اول parent_map را از روی children همه categoryها بساز.
    for item in data_items + included_items:
        if not _is_category_resource(item):
            continue
        parent_id = str(item.get("id") or "").strip()
        if not parent_id:
            continue
        for child_id in _extract_children_ids(item):
            parent_map[child_id] = parent_id

    # دسته‌های اصلی در data هستند.
    for item in data_items:
        obj = _extract_category_object(item, is_root=True)
        if not obj:
            continue
        root_ids.append(obj["id"])
        all_items_map[obj["id"]] = obj

    # زیردسته‌ها در included هستند، اما included شامل attribute هم هست؛ فیلتر type و slug ضروری است.
    for item in included_items:
        obj = _extract_category_object(item, is_root=False)
        if not obj:
            continue
        obj["parent_id"] = parent_map.get(obj["id"])
        all_items_map[obj["id"]] = obj

    # parent_idهای root را null نگه دار.
    for rid in root_ids:
        if rid in all_items_map:
            all_items_map[rid]["is_root"] = True
            all_items_map[rid]["parent_id"] = None

    def find_root_ancestor(item_id: str, visited=None) -> Optional[dict]:
        if visited is None:
            visited = set()
        if item_id in visited:
            return None
        visited.add(item_id)

        obj = all_items_map.get(item_id)
        if not obj:
            return None
        if obj.get("is_root"):
            return obj
        parent_id = obj.get("parent_id")
        if parent_id:
            return find_root_ancestor(parent_id, visited)
        return None

    def calc_depth(item_id: str, visited=None) -> int:
        if visited is None:
            visited = set()
        if item_id in visited:
            return 0
        visited.add(item_id)
        obj = all_items_map.get(item_id)
        if not obj or obj.get("is_root") or not obj.get("parent_id"):
            return 0
        return 1 + calc_depth(obj["parent_id"], visited)

    flat_categories: list[dict] = []
    seen_ids: set[str] = set()

    # دسته‌های اصلی با ترتیب API
    for rid in root_ids:
        root_obj = all_items_map.get(rid)
        if not root_obj or rid in seen_ids:
            continue
        seen_ids.add(rid)
        flat_categories.append({
            "id": root_obj["id"],
            "slug": root_obj["slug"],
            "name": root_obj["name"],
            "category": "اصلی",
            "type": "main",
            "parent_slug": None,
            "depth": 0,
            "platform": "sheypoor",
        })

    # زیردسته‌ها؛ فقط مواردی که به یک root واقعی وصل هستند.
    sub_items = [obj for obj in all_items_map.values() if not obj.get("is_root")]
    sub_items.sort(key=lambda x: (find_root_ancestor(x["id"]) or {}).get("name", "") + "|" + x.get("name", ""))

    for obj in sub_items:
        if obj["id"] in seen_ids:
            continue
        root_parent = find_root_ancestor(obj["id"])
        if not root_parent:
            # دسته‌ای که به ریشه واقعی وصل نیست، در UI اتوماسیون کاربرد ندارد.
            continue

        parent_obj = all_items_map.get(obj.get("parent_id")) if obj.get("parent_id") else None
        parent_slug = parent_obj.get("slug") if parent_obj else root_parent.get("slug")

        seen_ids.add(obj["id"])
        flat_categories.append({
            "id": obj["id"],
            "slug": obj["slug"],
            "name": obj["name"],
            "category": root_parent["name"],
            "type": "sub",
            "parent_slug": parent_slug,
            "depth": calc_depth(obj["id"]),
            "platform": "sheypoor",
        })

    main_count = sum(1 for c in flat_categories if c["type"] == "main")
    sub_count = len(flat_categories) - main_count

    return {
        "count": len(flat_categories),
        "main_count": main_count,
        "sub_count": sub_count,
        "platform": "sheypoor",
        "source": API_URL,
        "note": "Only resources with type='category' and non-empty slug are included. Attributes/filters are excluded.",
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
    print("📂 دریافت و پردازش دسته‌بندی‌های واقعی شیپور")
    print("=" * 60)

    try:
        raw_data = fetch_categories_api()
        processed = process_categories(raw_data)
        save_categories(processed, OUTPUT_FILE)
        print("\n✅ عملیات با موفقیت انجام شد.")
        print("ℹ️ اگر قبلاً فایل خراب شامل قیمت/رنگ/گیربکس داشتید، با این خروجی جایگزین شد.")
    except Exception as e:
        print(f"\n⚠️ خطا در پردازش: {e}")
        raise


if __name__ == "__main__":
    main()
