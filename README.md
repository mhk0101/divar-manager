# 🔧 Divar Manager - Hotfix v4 (رفع باگ Login دیوار)

**تاریخ:** 2026-07-19  
**نسخه:** 4.0 (Hotfix)  
**وضعیت:** ✅ آماده نصب فوری

---

## 🐛 باگ پیدا شده

### مشکل:
```
[INFO] State -> clicking_entry_button
[INFO] Clicking entry button
[INFO] Phone input appeared
[INFO] State -> waiting_for_code  ← ❌ باگ! مستقیم رفت به waiting_for_code
[INFO] Waiting for user to enter verification code (no timeout)...
```

**علت:** بعد از کلیک روی دکمه "ورود به حساب کاربری"، صفحه تغییر می‌کند و فیلد phone ظاهر می‌شود. ولی `page_state` هنوز مقدار قدیمی (`has_phone_input = False`) را دارد و `_step_submit_phone` هرگز صدا زده نمی‌شود!

---

## ✅ راه‌حل

**کد قبلی (با باگ):**
```python
if page_state["has_entry_button"]:
    await self._step_click_entry_button(page)  # ← کلیک → صفحه تغییر می‌کند!

if page_state["has_phone_input"]:  # ← ❌ page_state قدیمی!
    await self._step_submit_phone(page, phone)  # ← هرگز صدا زده نمی‌شود!
```

**کد جدید (اصلاح‌شده):**
```python
if page_state["has_entry_button"]:
    await self._step_click_entry_button(page)
    # ✨ FIX: بعد از کلیک، صفحه تغییر می‌کند، دوباره detect کن
    page_state = await self._detect_page_state(page)

if page_state["has_phone_input"]:  # ← ✅ page_state جدید!
    await self._step_submit_phone(page, phone)  # ← حالا صدا زده می‌شود!
```

---

## 📦 محتویات فایل ZIP

```
divar_manager_fixes_v4/
├── core/
│   ├── session_manager.py       ✅ (از GitHub)
│   └── token_refresher.py       ✅ (از GitHub)
├── modules/
│   ├── login/
│   │   └── login_manager.py     ✅ اصلاح شد! (1 خط اضافه شد)
│   └── sheypoor/
│       └── login/
│           └── login_manager.py ✅ (از GitHub)
└── ui/
    └── platform_tab.py          ✅ (از GitHub)
```

---

## 🚀 نحوه نصب

**فقط 1 فایل را جایگزین کنید:**

```bash
copy /Y divar_manager_fixes_v4\modules\login\login_manager.py modules\login\login_manager.py
```

---

## ✅ نتیجه

حالا Login دیوار باید درست کار کند:

```
[INFO] State -> clicking_entry_button
[INFO] Clicking entry button
[INFO] Phone input appeared
[INFO] State -> entering_phone  ← ✅ حالا درست!
[INFO] Entering phone: 09023808876
[INFO] Phone filled, clicking Next
[INFO] Initiate API responded: status=200
[INFO] Code input page appeared
[INFO] State -> waiting_for_code
[INFO] Waiting for user to enter verification code (no timeout)...
```

---

## 📊 خلاصه تغییرات

| فایل | تغییر | توضیح |
|------|-------|-------|
| `modules/login/login_manager.py` | +1 خط | اضافه شدن `page_state = await self._detect_page_state(page)` بعد از کلیک روی دکمه ورود |

---

**این یک Hotfix سریع است. فقط یک فایل را جایگزین کنید و تست کنید! 🎯**
