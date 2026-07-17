"""
مدیریت انتخاب شماره تلفن
"""
import json
import os
from typing import List, Dict, Optional

class PhoneNumberSelector:
    def __init__(self, config_path: str = "config/phone_numbers.json"):
        self.config_path = config_path
        self.phone_numbers = self.load_phone_numbers()
    
    def load_phone_numbers(self) -> List[Dict]:
        """بارگذاری شماره‌های موجود"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_phone_numbers(self):
        """ذخیره شماره‌ها"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.phone_numbers, f, ensure_ascii=False, indent=2)
    
    def add_phone_number(self, phone: str, name: str = "", is_active: bool = True):
        """افزودن شماره جدید"""
        phone_data = {
            "phone": phone,
            "name": name,
            "is_active": is_active,
            "sessions": {
                "divar": None,
                "sheypoor": None
            }
        }
        self.phone_numbers.append(phone_data)
        self.save_phone_numbers()
    
    def get_active_phones(self) -> List[Dict]:
        """دریافت شماره‌های فعال"""
        return [p for p in self.phone_numbers if p.get('is_active', True)]
    
    def display_phones(self) -> Optional[Dict]:
        """نمایش لیست شماره‌ها و انتخاب توسط کاربر"""
        active_phones = self.get_active_phones()
        
        if not active_phones:
            print("\n⚠️ هیچ شماره‌ای ثبت نشده است!")
            return None
        
        print("\n" + "="*50)
        print("📱 لیست شماره‌های موجود:")
        print("="*50)
        
        for idx, phone_data in enumerate(active_phones, 1):
            phone = phone_data.get('phone', 'نامشخص')
            name = phone_data.get('name', '')
            divar_session = "✓" if phone_data.get('sessions', {}).get('divar') else "✗"
            sheypoor_session = "✓" if phone_data.get('sessions', {}).get('sheypoor') else "✗"
            
            display_name = f" ({name})" if name else ""
            print(f"{idx}. {phone}{display_name}")
            print(f"   دیوار: {divar_session}  |  شیپور: {sheypoor_session}")
            print("-"*50)
        
        while True:
            try:
                choice = input("\n👉 شماره مورد نظر را انتخاب کنید (یا 0 برای خروج): ").strip()
                
                if choice == '0':
                    return None
                
                choice_idx = int(choice) - 1
                
                if 0 <= choice_idx < len(active_phones):
                    selected = active_phones[choice_idx]
                    print(f"\n✅ شماره {selected['phone']} انتخاب شد.")
                    return selected
                else:
                    print("❌ شماره نامعتبر! دوباره امتحان کنید.")
            
            except ValueError:
                print("❌ لطفاً یک عدد وارد کنید!")
            except KeyboardInterrupt:
                print("\n\n⚠️ عملیات لغو شد.")
                return None

# نمونه استفاده
if __name__ == "__main__":
    selector = PhoneNumberSelector()
    
    # اگر شماره‌ای نبود، چند نمونه اضافه کن
    if not selector.phone_numbers:
        selector.add_phone_number("09121234567", "حساب اصلی")
        selector.add_phone_number("09359876543", "حساب دوم")
        print("✓ شماره‌های نمونه اضافه شد")
    
    # نمایش و انتخاب
    selected_phone = selector.display_phones()
    
    if selected_phone:
        print(f"\nشماره انتخاب شده: {selected_phone['phone']}")
