# 🎯 Divar Manager - نسخه نهایی و کامل

## 📦 محتویات (همه در یک فایل)

```
divar_complete/
├── core/
│   ├── session_manager.py       ✅ حذف کامل + capture_storage_state
│   └── token_refresher.py       ✅ Auto-refresh (دیوار + شیپور)
├── modules/
│   ├── login/
│   │   └── login_manager.py     ✅ Login دیوار (همه اصلاحات)
│   └── sheypoor/login/
│       └── login_manager.py     ✅ Login شیپور
├── ui/
│   ├── platform_tab.py          ✅ UI (دکمه لغو + مرورگر باز)
│   ├── automation_tab.py        🤖 تب اتوماسیون
│   └── main_window.py           🪟 پنجره اصلی (4 تب)
├── fetch_cities.py              📡 دریافت لیست شهرها
└── README.md                    📖 این فایل
```

---

## 🚀 نصب (فقط یک دستور!)

```bash
# همه فایل‌ها را کپی کنید:
xcopy /E /I /Y divar_complete\* .
```

یا به صورت دستی:

```bash
# Core
copy /Y divar_complete\core\session_manager.py core\
copy /Y divar_complete\core\token_refresher.py core\

# Login Managers
copy /Y divar_complete\modules\login\login_manager.py modules\login\
copy /Y divar_complete\modules\sheypoor\login\login_manager.py modules\sheypoor\login\

# UI
copy /Y divar_complete\ui\platform_tab.py ui\
copy /Y divar_complete\ui\automation_tab.py ui\
copy /Y divar_complete\ui\main_window.py ui\

# Automation
copy /Y divar_complete\fetch_cities.py .
```

---

## 🤖 تب اتوماسیون

### مرحله 1: دریافت لیست شهرها

```bash
python fetch_cities.py
```

خروجی: `data/cities.json`

### مرحله 2: اجرا

```bash
python ui/main.py
```

حالا 4 تب می‌بینید:
- 🏠 دیوار
- 📢 شیپور
- 🤖 اتوماسیون (جدید!)
- 📋 لاگ‌ها

---

## ✅ اصلاحات انجام‌شده

### 1. دکمه لغو/بازگشت ✅
- `QTimer.singleShot()` برای تأخیر
- Force close بعد از 500ms

### 2. صفحه کد بار دوم ✅
- `page_state` بعد از کلیک دوباره detect می‌شود

### 3. تشخیص ورود کد از سایت ✅
- `asyncio.wait()` با دو task (UI + site)

### 4. مقاومت در برابر قطع اینترنت ✅
- URL های ایرانی (divar.ir, aparat.com, varzesh3.com)

### 5. حذف کامل Session ✅
- هم DB و هم فایل JSON حذف می‌شوند

### 6. capture_storage_state ✅
- متد اضافه شد

### 7. Token Auto-Refresh ✅
- دیوار: sAccessToken + sRefreshToken
- شیپور: access_token + refresh_token

### 8. status=VALID بعد از Login ✅
- چک تغییرات قبل از ذخیره
- فقط در صورت تغییر ذخیره می‌شود

### 9. مرورگر باز بعد از Login ✅
- `wait_for_event("close")` تا کاربر ببندد

### 10. ذخیره بهینه Session ✅
- فقط اگر تغییر کرده ذخیره می‌شود
- capture_storage_state یک بار (نه دو بار)

---

## 🎯 نتیجه نهایی

| قابلیت | وضعیت |
|--------|-------|
| Login دیوار | ✅ کامل |
| Login شیپور | ✅ کامل |
| Session Management | ✅ کامل |
| Token Auto-Refresh | ✅ کامل |
| تب اتوماسیون | ✅ کامل |
| Internet Resilience | ✅ کامل |

**موفق باشید! 🎉**
