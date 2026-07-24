# راهنمای نصب و اجرا روی Windows

## پیش‌نیازها

- Python 3.11 (یا بالاتر)
- pip

## مراحل نصب

### 1. ایجاد Virtual Environment (توصیه می‌شود)

```cmd
cd D:\Divar_Gui_New\Version_new_pyside\divar_manager\divar_manager

python -m venv .venv
.venv\Scripts\activate
```

### 2. نصب وابستگی‌ها

```cmd
pip install -r requirements.txt
pip install -r requirements_gui.txt
```

### 3. نصب مرورگر Chromium برای Playwright

```cmd
playwright install chromium
```

این دستور مرورگر Chromium را دانلود و نصب می‌کند (حدود 150 مگابایت).

### 4. اجرای برنامه

#### رابط کاربری گرافیکی (GUI):

```cmd
python ui\main.py
```

#### تست از خط فرمان (CLI):

```cmd
python run_login_test.py
```

## عیب‌یابی

### خطای PySide6-QtWebEngine

اگر با خطای زیر مواجه شدید:
```
ERROR: Could not find a version that satisfies the requirement PySide6-QtWebEngine
```

**راه حل:** این پکیج لازم نیست. فقط `PySide6` را نصب کنید:
```cmd
pip install PySide6
```

### خطای Playwright

اگر با خطای "Playwright browser not found" مواجه شدید:
```cmd
playwright install chromium
```

### مشکل DLL

اگر خطای مربوط به DLL دریافت کردید:
```cmd
pip install --upgrade PySide6
```

## ساختار پروژه

```
divar_manager/
├── config/
│   └── settings.py              # تنظیمات پروژه
├── core/
│   ├── browser_manager.py       # مدیریت مرورگر
│   ├── session_manager.py       # مدیریت Session
│   └── logger_manager.py        # مدیریت لاگ‌ها
├── modules/
│   ├── login/                   # ماژول Login دیوار
│   │   ├── selectors.py         # Selectorهای دیوار
│   │   ├── models.py            # مدل‌های داده
│   │   └── login_manager.py     # منطق Login
│   └── sheypoor/                # ماژول Login شیپور
│       └── login/
│           ├── selectors.py     # Selectorهای شیپور
│           ├── models.py        # مدل‌های داده
│           └── login_manager.py # منطق Login
├── ui/
│   ├── main_window.py           # پنجره اصلی با 3 تب
│   ├── platform_tab.py          # تب عمومی Login
│   ├── logs_tab.py              # تب لاگ‌ها
│   └── main.py                  # Entry point GUI
├── requirements.txt
├── requirements_gui.txt
└── run_login_test.py            # تست CLI (فقط دیوار)
```

## نکات مهم

### دیوار
1. **Session ذخیره می‌شود در:** `data\sessions\divar_session.json`
2. **کد تأیید:** ۶ رقمی
3. **مرورگر Chromium** به صورت خودکار باز می‌شود (headless=False)

### شیپور
1. **Session ذخیره می‌شود در:** `data\sessions\sheypoor_session.json`
2. **کد تأیید:** ۴ رقمی
3. **مرورگر Chromium** به صورت خودکار باز می‌شود (headless=False)

### عمومی
- **پس از ورود موفق**، Session ذخیره می‌شود و می‌توانید دفعات بعد بدون Login مجدد استفاده کنید
- **لاگ‌ها** در `data\logs\` ذخیره می‌شوند و در تب لاگ‌ها قابل مشاهده هستند
- **کد تأیید** را از SMS دریافتی وارد کنید

## توقف برنامه

- در GUI: پنجره را ببندید یا `Ctrl+C` در ترمینال
- در CLI: `Ctrl+C`
