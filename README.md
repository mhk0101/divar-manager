# Divar Manager

نرم‌افزار مدیریت آگهی‌های سایت دیوار — توسعه‌یافته با Python 3.11، PySide6 و Playwright.

> این پروژه به‌صورت **ماژولار و مرحله‌به‌مرحله** توسعه می‌یابد.
> هر بخش پس از پیاده‌سازی و تأیید، وارد مرحله بعدی می‌شویم.

---

## مراحل توسعه (نقشه راه)

| # | ماژول | وضعیت |
|---|-------|-------|
| 1 | **Login Module - دیوار** | ✅ کامل |
| 2 | **Login Module - شیپور** | ✅ کامل |
| 3 | **PySide6 UI (3 تب)** | ✅ کامل |
| 4 | Session Manager (کامل) | ⏳ در انتظار |
| 5 | City / Category / Sub-Category Selector | ⏳ در انتظار |
| 6 | Listing Scraper | ⏳ در انتظار |
| 7 | Ad Detail Extractor | ⏳ در انتظار |
| 8 | Task / Status Manager | ⏳ در انتظار |
| 9 | Scheduler & Worker | ⏳ در انتظار |

---

## ماژول‌های تکمیل‌شده

### ✅ Login Module - دیوار

وظایف:
1. باز کردن صفحه ورود دیوار
2. کلیک روی «ورود به حساب کاربری»
3. وارد کردن شماره موبایل و فشردن «بعدی»
4. انتظار برای ورود کد تأیید (۶ رقمی)
5. وارد کردن کد در ۶ فیلد مجزا و فشردن «ورود»
6. تشخیص موفق/ناموفق بودن ورود
7. ذخیره‌ی Session از طریق `SessionManager`

**محل فایل‌ها:** `modules/login/`

### ✅ Login Module - شیپور

وظایف:
1. باز کردن صفحه ورود شیپور
2. وارد کردن شماره موبایل و فشردن «ورود یا ثبت نام»
3. انتظار برای ورود کد تأیید (۴ رقمی)
4. وارد کردن کد در ۴ فیلد مجزا و فشردن «تائید نهایی»
5. تشخیص موفق/ناموفق بودن ورود
6. ذخیره‌ی Session از طریق `SessionManager`

**محل فایل‌ها:** `modules/sheypoor/login/`

### ✅ PySide6 UI (3 تب)

رابط کاربری گرافیکی با سه تب:
- **تب دیوار:** Login دیوار
- **تب شیپور:** Login شیپور
- **تب لاگ‌ها:** نمایش لاگ‌های سراسری

**محل فایل‌ها:** `ui/`

### معماری انتخاب Selector

اولویت انتخاب Selector طبق مستندات پروژه:

**دیوار:**
1. `name`
2. `aria-label`
3. `text` (محتوای متنی)
4. `placeholder`
5. Selector پایدار

**شیپور:**
1. `data-test-id` (پایدارترین)
2. `name`
3. `aria-label`
4. `text`
5. Selector پایدار

---

## نصب و اجرا

```bash
cd divar_manager
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# نصب وابستگی‌ها
pip install -r requirements.txt
pip install -r requirements_gui.txt
playwright install chromium
```

### 🖥️ اجرای رابط کاربری گرافیکی (پیشنهادی)

```bash
python ui/main.py
```

رابط کاربری PySide6 با **سه تب** اجرا می‌شود:

#### تب دیوار 🏠
- ورود شماره موبایل
- دریافت کد تأیید ۶ رقمی
- ذخیره Session در `data/sessions/divar_session.json`

#### تب شیپور 📢
- ورود شماره موبایل
- دریافت کد تأیید ۴ رقمی
- ذخیره Session در `data/sessions/sheypoor_session.json`

#### تب لاگ‌ها 📋
- نمایش تمام لاگ‌های سیستم
- رنگ‌بندی بر اساس سطح (INFO, ERROR, WARNING)
- قابلیت پاک کردن لاگ‌ها

### 💻 اجرای تست از خط فرمان (CLI) - فقط دیوار

```bash
python run_login_test.py
```

اسکریپت `run_login_test.py` یک flow تعاملی در ترمینال اجرا می‌کند:
- شماره موبایل را می‌گیرد
- کد تأیید را از شما می‌پرسد
- نتیجه Login و مسیر فایل Session را نمایش می‌دهد

> هر دو روش (GUI و CLI) از همان `LoginManager` استفاده می‌کنند.
