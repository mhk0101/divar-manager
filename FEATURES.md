# ویژگی‌های پیاده‌سازی شده

## ✅ ماژول Login دیوار

### Selectorها
- **دکمه ورود:** `text=ورود به حساب کاربری`
- **فیلد شماره:** `input[name='phone']`
- **دکمه بعدی:** `button.kt-button--primary:has-text('بعدی')`
- **کد ۶ رقمی:** `input[aria-label='رقم ۱']` تا `رقم ۶`
- **دکمه ورود:** `button.kt-button--primary:has-text('ورود')`

### ویژگی‌ها
- اعتبارسنجی شماره موبایل (فارسی/انگلیسی، با/بدون +98)
- انتظار برای API `open-initiate-page` پس از ارسال شماره
- انتظار برای API `open-confirm-page` پس از ارسال کد
- تشخیص موفقیت از طریق حذف گروه کد از DOM
- ذخیره Session در `data/sessions/divar_session.json`

---

## ✅ ماژول Login شیپور

### Selectorها
- **فیلد شماره:** `input[data-test-id='login-field-tel']`
- **دکمه ورود:** `button[data-test-id='login-submit-tel']`
- **کد ۴ رقمی:** `input[data-test-id='otpInput-0']` تا `otpInput-3`
- **دکمه تأیید:** `button[data-test-id='verfication-submit']`
- **دکمه دریافت مجدد:** `button[data-test-id='resend-otp']`
- **دکمه اصلاح شماره:** `button[data-test-id='change-number']`

### ویژگی‌ها
- اعتبارسنجی شماره موبایل (فارسی/انگلیسی، با/بدون +98)
- کد تأیید ۴ رقمی (برخلاف دیوار که ۶ رقمی است)
- تشخیص موفقیت از طریق تغییر URL به `myAccount` یا `myListings`
- ذخیره Session در `data/sessions/sheypoor_session.json`

---

## ✅ رابط کاربری PySide6 (3 تب)

### تب دیوار 🏠
- رنگ اصلی: `#A62626` (قرمز دیوار)
- کد ۶ رقمی
- Session: `divar_session.json`

### تب شیپور 📢
- رنگ اصلی: `#3568d4` (آبی شیپور)
- کد ۴ رقمی
- Session: `sheypoor_session.json`

### تب لاگ‌ها 📋
- نمایش تمام لاگ‌های سیستم
- رنگ‌بندی:
  - **INFO:** سبز (`#4ec9b0`)
  - **WARNING:** زرد (`#dcdcaa`)
  - **ERROR:** قرمز (`#f48771`)
  - **CRITICAL:** قرمز پررنگ (`#ff0000`)
- قابلیت پاک کردن لاگ‌ها
- شمارنده تعداد لاگ‌ها
- نمایش زمان آخرین به‌روزرسانی

### معماری UI
- **PlatformTab:** کلاس عمومی قابل استفاده مجدد برای هر پلتفرم
- **LoginWorker:** اجرای LoginManager در QThread جداگانه (Non-blocking)
- **Thread-safe communication:** استفاده از Signal/Slot و concurrent.futures.Future
- **Dependency Injection:** LoginManager از بیرون تزریق می‌شود

---

## 🔄 جریان اجرا

```
کاربر شماره را وارد می‌کند
    ↓
PlatformTab._on_phone_submitted()
    ↓
LoginWorker در QThread شروع می‌شود
    ↓
BrowserManager.start() - مرورگر باز می‌شود
    ↓
LoginManager.login() شروع می‌شود
    ↓
صفحه Login باز می‌شود
    ↓
شماره وارد می‌شود و دکمه ارسال زده می‌شود
    ↓
LoginManager منتظر کد می‌ماند
    ↓
Signal code_needed به UI ارسال می‌شود
    ↓
UI صفحه کد را نمایش می‌دهد
    ↓
کاربر کد را وارد می‌کند
    ↓
Future.set_result(code) - کد به worker ارسال می‌شود
    ↓
LoginManager کد را وارد می‌کند
    ↓
تشخیص موفقیت/شکست
    ↓
ذخیره Session
    ↓
Signal login_finished به UI ارسال می‌شود
    ↓
QMessageBox نمایش داده می‌شود
    ↓
BrowserManager.stop() - مرورگر بسته می‌شود
```

---

## 📊 مقایسه دیوار و شیپور

| ویژگی | دیوار | شیپور |
|-------|-------|-------|
| **URL ورود** | `https://divar.ir/my-divar` | `https://www.sheypoor.com/session` |
| **طول کد** | ۶ رقم | ۴ رقم |
| **Selector فیلد شماره** | `name='phone'` | `data-test-id='login-field-tel'` |
| **Selector دکمه ارسال شماره** | `text='بعدی'` | `data-test-id='login-submit-tel'` |
| **Selector فیلد کد** | `aria-label='رقم X'` | `data-test-id='otpInput-X'` |
| **Selector دکمه تأیید** | `text='ورود'` | `data-test-id='verfication-submit'` |
| **تشخیص موفقیت** | حذف گروه کد از DOM | تغییر URL به `myAccount` |
| **رنگ UI** | `#A62626` | `#3568d4` |
| **فایل Session** | `divar_session.json` | `sheypoor_session.json` |

---

## 🎯 نکات فنی

### Thread Safety
- تمام عملیات Playwright در QThread جداگانه اجرا می‌شود
- ارتباط بین UI و Worker از طریق Signal/Slot
- استفاده از `concurrent.futures.Future` برای ارسال کد از UI به Worker

### Dependency Injection
```python
LoginManager(
    browser_manager=BrowserManager(...),
    session_manager=SessionManager(...),
    code_provider=async_function,
)
```

### Error Handling
- تمام خطاها catch شده و به UI ارسال می‌شوند
- لاگ‌ها هم به فایل و هم به UI ارسال می‌شوند
- MessageBox برای خطاهای کاربرپسند

### Logging
- **File Handler:** `data/logs/app_YYYYMMDD.log`
- **Console Handler:** stdout
- **UI Handler:** تب لاگ‌ها

---

## 🚀 مراحل بعدی (پیشنهادی)

1. **Session Manager کامل**
   - اعتبارسنجی Session (آیا هنوز معتبر است؟)
   - انقضای Session
   - پشتیبانی از چندکاربره
   - Refresh خودکار Session

2. **City / Category Selector**
   - انتخاب شهر
   - انتخاب دسته‌بندی
   - انتخاب زیردسته
   - فیلترهای پیشرفته

3. **Listing Scraper**
   - استخراج لیست آگهی‌ها
   - Pagination
   - فیلتر بر اساس تنظیمات کاربر

4. **Ad Detail Extractor**
   - باز کردن صفحه هر آگهی
   - استخراج اطلاعات کامل
   - ذخیره در دیتابیس

5. **Task / Status Manager**
   - مدیریت وضعیت هر آگهی
   - صف پردازش
   - اولویت‌بندی

6. **Scheduler & Worker**
   - زمان‌بندی اجرای خودکار
   - Worker Pool
   - Queue Management
