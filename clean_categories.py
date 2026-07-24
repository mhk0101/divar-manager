"""
اسکریپت تمیز کردن فایل categories.json

حذف موارد:
- دسته‌های نامعتبر (مثل "همهٔ آگهی‌ها")
- دسته‌های تکراری
"""

import json
from pathlib import Path

INPUT_FILE = Path(__file__).parent / "data" / "categories.json"
OUTPUT_FILE = Path(__file__).parent / "data" / "categories_clean.json"


def clean_categories():
    """تمیز کردن لیست دسته‌بندی‌ها."""
    if not INPUT_FILE.exists():
        print(f"❌ فایل پیدا نشد: {INPUT_FILE}")
        return
    
    print("=" * 60)
    print("🧹 تمیز کردن لیست دسته‌بندی‌ها")
    print("=" * 60)
    print()
    
    # خواندن فایل
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    original_count = len(data.get("categories", []))
    print(f"📊 تعداد اولیه: {original_count}")
    print()
    
    # لیست slug های نامعتبر
    invalid_slugs = ["tehran", "iran"]  # اینها شهر هستند نه دسته
    invalid_names = ["همهٔ آگهی‌ها", "همه آگهی‌ها", "همه‌ی آگهی‌ها"]
    
    # فیلتر کردن دسته‌های flat
    clean_categories = []
    removed_count = 0
    
    for cat in data.get("categories", []):
        slug = cat.get("slug", "")
        name = cat.get("name", "")
        
        # بررسی نامعتبر بودن
        is_invalid = False
        
        # slug نامعتبر
        if slug in invalid_slugs:
            is_invalid = True
            print(f"  ❌ حذف (slug نامعتبر): {name} ({slug})")
        
        # نام نامعتبر
        for invalid_name in invalid_names:
            if invalid_name in name:
                is_invalid = True
                print(f"  ❌ حذف (نام نامعتبر): {name} ({slug})")
                break
        
        # تکراری (همهٔ آگهی‌های استخدام و کاریابی)
        if "همهٔ آگهی‌های" in name or "همه آگهی‌های" in name:
            is_invalid = True
            print(f"  ❌ حذف (تکراری): {name} ({slug})")
        
        if not is_invalid:
            clean_categories.append(cat)
        else:
            removed_count += 1
    
    print()
    print(f"✅ {removed_count} مورد حذف شد")
    print(f"✅ {len(clean_categories)} مورد باقی ماند")
    print()
    
    # تمیز کردن tree
    clean_tree = []
    for cat in data.get("tree", []):
        slug = cat.get("slug", "")
        name = cat.get("name", "")
        
        is_invalid = False
        
        if slug in invalid_slugs:
            is_invalid = True
        
        for invalid_name in invalid_names:
            if invalid_name in name:
                is_invalid = True
                break
        
        if "همهٔ آگهی‌های" in name or "همه آگهی‌های" in name:
            is_invalid = True
        
        if not is_invalid:
            clean_tree.append(cat)
    
    # ساخت خروجی
    output = {
        "count": len(clean_categories),
        "main_count": len(clean_tree),
        "sub_count": len(clean_categories) - len(clean_tree),
        "categories": clean_categories,
        "tree": clean_tree,
    }
    
    # ذخیره
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print(f"💾 ذخیره شد: {OUTPUT_FILE}")
    print()
    print("📊 آمار نهایی:")
    print(f"   • دسته‌های اصلی: {len(clean_tree)}")
    print(f"   • زیردسته‌ها: {output['sub_count']}")
    print(f"   • مجموع: {len(clean_categories)}")
    print("=" * 60)
    print()
    
    # کپی به categories.json اصلی
    import shutil
    shutil.copy(OUTPUT_FILE, INPUT_FILE)
    print(f"✅ فایل اصلی بروزرسانی شد: {INPUT_FILE}")
    print()


if __name__ == "__main__":
    clean_categories()
