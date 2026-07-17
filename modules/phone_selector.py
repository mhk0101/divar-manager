"""
phone_selector.py
مدیریت انتخاب شماره تلفن - با پشتیبانی از UI و ترمینال
"""
import json
import os
from typing import List, Dict, Optional


class PhoneNumberSelector:
    def __init__(self, config_path: str = "config/phone_numbers.json"):
        self.config_path = config_path
        self.phone_numbers: List[Dict] = self.load_phone_numbers()

    def load_phone_numbers(self) -> List[Dict]:
        """بارگذاری شماره‌های موجود"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def save_phone_numbers(self):
        """ذخیره شماره‌ها"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.phone_numbers, f, ensure_ascii=False, indent=2)

    def add_phone_number(self, phone: str, name: str = "", is_active: bool = True):
        """افزودن شماره جدید"""
        # جلوگیری از تکرار
        for p in self.phone_numbers:
            if p.get("phone") == phone:
                return
        self.phone_numbers.append({
            "phone": phone,
            "name": name,
            "is_active": is_active,
            "sessions": {"divar": None, "sheypoor": None},
        })
        self.save_phone_numbers()

    def remove_phone(self, phone: str):
        self.phone_numbers = [p for p in self.phone_numbers if p.get("phone") != phone]
        self.save_phone_numbers()

    def get_active_phones(self) -> List[Dict]:
        """دریافت شماره‌های فعال"""
        return [p for p in self.phone_numbers if p.get("is_active", True)]

    def get_phone_list(self) -> List[str]:
        """فقط شماره‌ها به صورت لیست رشته"""
        return [p["phone"] for p in self.get_active_phones()]

    # ── نمایش ترمینالی (fallback) ─────────────────────────────────
    def display_phones_terminal(self) -> Optional[Dict]:
        active = self.get_active_phones()
        if not active:
            print("\n⚠️  هیچ شماره‌ای ثبت نشده است!")
            return None
        print("\n" + "=" * 45)
        print("📱  لیست شماره‌های موجود:")
        print("=" * 45)
        for i, p in enumerate(active, 1):
            name = f"  ({p.get('name', '')})" if p.get("name") else ""
            dv = "✓" if p.get("sessions", {}).get("divar") else "✗"
            sh = "✓" if p.get("sessions", {}).get("sheypoor") else "✗"
            print(f"  {i}. {p['phone']}{name}   دیوار:{dv}  شیپور:{sh}")
        print("=" * 45)
        while True:
            try:
                c = input(f"👉 انتخاب (1-{len(active)}) یا 0 برای خروج: ").strip()
                idx = int(c)
                if idx == 0:
                    return None
                if 1 <= idx <= len(active):
                    sel = active[idx - 1]
                    print(f"\n✅ شماره {sel['phone']} انتخاب شد.")
                    return sel
                print("❌ عدد نامعتبر، دوباره امتحان کنید.")
            except ValueError:
                print("❌ لطفاً یک عدد وارد کنید.")


# ── standalone test ────────────────────────────────────────────────
if __name__ == "__main__":
    sel = PhoneNumberSelector()
    if not sel.phone_numbers:
        sel.add_phone_number("09121234567", "حساب اصلی")
        sel.add_phone_number("09359876543", "حساب دوم")
        print("✓ شماره‌های نمونه اضافه شد")
    result = sel.display_phones_terminal()
    if result:
        print(f"\nشماره انتخاب شده: {result['phone']}")
