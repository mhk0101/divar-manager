"""
اسکریپت استخراج دسته‌بندی‌ها از سایت دیوار.

روش کار:
1. سایت دیوار را باز می‌کند
2. منتظر می‌ماند تا کاربر روی دکمه "دسته‌ها" کلیک کند
3. لیست دسته‌بندی‌ها را استخراج و ذخیره می‌کند
4. تمام! (فقط یکبار اجرا می‌شود)

خروجی: data/categories.json
"""

import json
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "data" / "categories.json"


def fetch_categories_interactive():
    """استخراج دسته‌بندی‌ها به صورت تعاملی."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright نصب نیست. نصب کنید:")
        print("   pip install playwright")
        print("   playwright install chromium")
        return None

    print("=" * 60)
    print("📂 استخراج تعاملی دسته‌بندی‌های دیوار")
    print("=" * 60)
    print()
    print("🌐 مرورگر باز می‌شود...")
    print()
    print("📋 دستورالعمل:")
    print("   1. در سایت دیوار، روی دکمه «دسته‌ها» کلیک کنید")
    print("   2. منتظر بمانید تا لیست دسته‌بندی‌ها ظاهر شود")
    print("   3. سپس در این پنجره Enter بزنید")
    print()
    
    categories = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        # باز کردن سایت دیوار
        print("📡 باز کردن سایت دیوار...")
        page.goto("https://divar.ir/s/tehran", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        print()
        input("⏸️  وقتی روی دکمه «دسته‌ها» کلیک کردید و لیست ظاهر شد، Enter بزنید...")
        print()
        print("📋 در حال استخراج دسته‌بندی‌ها...")
        
        # استخراج دسته‌های اصلی
        main_categories = page.query_selector_all('a.selector-cf812')
        
        if not main_categories:
            print("❌ هیچ دسته‌بندی پیدا نشد!")
            print("💡 مطمئن شوید که روی دکمه «دسته‌ها» کلیک کرده‌اید.")
            browser.close()
            return None
        
        print(f"✅ {len(main_categories)} دسته اصلی پیدا شد!")
        
        for i, main_cat in enumerate(main_categories, 1):
            try:
                # نام دسته
                name_elem = main_cat.query_selector('span.selector__title-f2695')
                if not name_elem:
                    continue
                
                name = name_elem.inner_text().strip()
                href = main_cat.get_attribute("href") or ""
                
                if not name or not href:
                    continue
                
                # استخراج slug
                slug = href.split("/")[-1] if "/" in href else href
                
                # استخراج آیکون (اختیاری)
                icon_elem = main_cat.query_selector('i.kt-icon')
                icon_class = ""
                if icon_elem:
                    icon_classes = icon_elem.get_attribute("class") or ""
                    # استخراج نام آیکون از class
                    for cls in icon_classes.split():
                        if cls.startswith("kt-icon-cat-"):
                            icon_class = cls
                            break
                
                print(f"  [{i}/{len(main_categories)}] {name} ({slug})")
                
                # hover روی دسته برای دیدن زیردسته‌ها
                main_cat.hover()
                page.wait_for_timeout(500)
                
                # استخراج زیردسته‌ها
                subcategories = []
                sub_links = page.query_selector_all('a.category-menu-item-ed973')
                
                for sub_link in sub_links:
                    try:
                        sub_name = sub_link.inner_text().strip()
                        sub_href = sub_link.get_attribute("href") or ""
                        
                        if sub_name and sub_href:
                            sub_slug = sub_href.split("/")[-1] if "/" in sub_href else sub_href
                            subcategories.append({
                                "slug": sub_slug,
                                "name": sub_name,
                            })
                    except Exception:
                        continue
                
                categories.append({
                    "slug": slug,
                    "name": name,
                    "icon": icon_class,
                    "subcategories": subcategories,
                })
                
            except Exception as e:
                print(f"    ⚠️ خطا در استخراج: {e}")
                continue
        
        print()
        print("✅ استخراج کامل شد!")
        browser.close()
    
    return categories


def save_categories(categories, filepath):
    """ذخیره لیست دسته‌بندی‌ها."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # تبدیل به فرمت ساده‌تر برای UI
    flat_categories = []
    for cat in categories:
        # دسته اصلی
        flat_categories.append({
            "slug": cat["slug"],
            "name": cat["name"],
            "category": "اصلی",
            "type": "main",
        })
        
        # زیردسته‌ها
        for sub in cat.get("subcategories", []):
            flat_categories.append({
                "slug": sub["slug"],
                "name": sub["name"],
                "category": cat["name"],
                "type": "sub",
                "parent_slug": cat["slug"],
            })
    
    output = {
        "count": len(flat_categories),
        "main_count": len(categories),
        "sub_count": len(flat_categories) - len(categories),
        "categories": flat_categories,
        "tree": categories,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print()
    print("💾 ذخیره شد:", filepath)
    print(f"📊 آمار:")
    print(f"   • دسته‌های اصلی: {len(categories)}")
    print(f"   • زیردسته‌ها: {output['sub_count']}")
    print(f"   • مجموع: {len(flat_categories)}")


def main():
    categories = fetch_categories_interactive()
    
    if not categories:
        print()
        print("❌ استخراج ناموفق بود.")
        return
    
    # نمایش خلاصه
    print()
    print("=" * 60)
    print(f"✅ {len(categories)} دسته اصلی استخراج شد:")
    print("=" * 60)
    
    for cat in categories:
        sub_count = len(cat.get("subcategories", []))
        print(f"  • {cat['name']} ({cat['slug']}) - {sub_count} زیردسته")
    
    # ذخیره
    save_categories(categories, OUTPUT_FILE)
    
    print()
    print("=" * 60)
    print("✅ تمام شد! می‌توانید این پنجره را ببندید.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
