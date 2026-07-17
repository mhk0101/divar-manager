# Session Manager - Phase 2

## ✅ تکمیل شده

Session Manager حرفه‌ای با قابلیت‌های زیر پیاده‌سازی شده است.

---

## 🎯 ویژگی‌ها

### ۱. ذخیره‌سازی در SQLite

**مسیر دیتابیس:** `data/db/sessions.db`

**جدول sessions:**
| ستون | توضیح |
|------|-------|
| `id` | شناسه یکتا |
| `platform` | نام پلتفرم (divar / sheypoor) |
| `phone` | شماره موبایل کاربر |
| `storage_state` | JSON کامل (Cookies + LocalStorage) |
| `access_token` | Access Token (در صورت وجود) |
| `refresh_token` | Refresh Token (در صورت وجود) |
| `status` | وضعیت: valid, invalid, expired, needs_refresh, unknown |
| `created_at` | زمان ایجاد |
| `updated_at` | زمان آخرین بروزرسانی |
| `last_used_at` | زمان آخرین استفاده |
| `metadata` | JSON اطلاعات اضافی |

**جدول session_history:** ثبت تمام تغییرات هر Session (Audit Log)

---

### ۲. API کامل SessionManager

```python
from core.session_manager import SessionManager

sm = SessionManager(platform="divar")

# ذخیره پس از Login
record = await sm.save_from_context(
    context=browser_context,
    phone="09121234567",
    access_token="...",       # اختیاری
    refresh_token="...",      # اختیاری
    metadata={"user_id": 123} # اختیاری
)

# بارگذاری
record = sm.load(phone="09121234567")  # بر اساس شماره
record = sm.load()                      # آخرین Session معتبر

# اعتبارسنجی (تست واقعی روی سایت)
status = await sm.validate(record, page)

# تغییر وضعیت
sm.mark_invalid(record, reason="expired")
sm.mark_valid(record)

# لیست و حذف
all_sessions = sm.list_sessions()
sm.delete(record)
sm.delete_by_phone("09121234567")

# Export برای Playwright
storage_dict = await sm.apply_to_context(record)
file_path = await sm.export_storage_state(record)

# تاریخچه
history = sm.get_history(record)
```

---

### ۳. اعتبارسنجی واقعی Session

`SessionValidator` یک صفحه protected از سایت را باز می‌کند و بررسی می‌کند آیا کاربر لاگین است:

- **دیوار:** بررسی وجود دکمه «ورود به حساب کاربری» در `/my-divar`
- **شیپور:** بررسی وجود فیلد شماره در `/session`

اگر دکمه/فیلد لاگین دیده شد → Session نامعتبر  
اگر دیده نشد → Session معتبر

---

### ۴. مدیریت خطا و Retry

```python
from core.retry import async_retry, OperationCancelled, NetworkError

@async_retry(
    max_attempts=3,
    delay=2.0,
    backoff=2.0,
    jitter=0.1,
    exceptions=(PlaywrightTimeout, NetworkError),
    on_retry=lambda attempt, exc: logger.info(f"Retry {attempt}: {exc}"),
)
async def some_operation():
    ...
```

**ویژگی‌ها:**
- تلاش مجدد خودکار با backoff نمایی
- Jitter برای جلوگیری از thundering herd
- فقط برای exceptionهای مشخص
- Callback قبل از هر retry

**Exceptionهای اختصاصی:**
- `OperationCancelled` - لغو توسط کاربر
- `NetworkError` - خطای شبکه
- `SessionExpired` - انقضای Session
- `LoginRequired` - نیاز به Login

---

### ۵. عدم استفاده از Sleep/Timeout ثابت

طبق مستندات پروژه:

❌ **هرگز:**
```python
await asyncio.sleep(5)
```

✅ **همیشه:**
```python
await page.wait_for_selector("...", state="visible")
await page.wait_for_load_state("networkidle")
await locator.wait_for(state="attached")
```

**در انتظار کد تأیید:** هیچ timeout وجود ندارد. کاربر خودش تصمیم می‌گیرد:
- کد را وارد کند
- مرورگر را ببندد و دوباره تلاش کند
- دکمه «لغو» را بزند

---

### ۶. Logging کامل

تمام عملیات Session لاگ می‌شوند:

```
[INFO ] [divar] Session saved: phone=09121234567 cookies=15
[INFO ] [divar] Session loaded: phone=09121234567 status=valid
[INFO ] [divar] Session validated: phone=09121234567 -> valid
[WARN ] [divar] Session marked invalid: phone=09121234567 reason=expired
[INFO ] Session status changed: id=1 -> invalid (expired)
```

**کانال‌های لاگ:**
- Console (stdout)
- فایل: `data/logs/app_YYYYMMDD.log`
- UI: تب لاگ‌ها (از طریق `UILogHandler`)

---

## 🏗️ معماری ماژولار

```
core/
├── session_models.py       # مدل‌های داده (Cookie, SessionRecord, StorageState, SessionStatus)
├── session_db.py           # لایه دیتابیس SQLite
├── session_validator.py    # اعتبارسنجی واقعی روی سایت
├── session_manager.py      # API اصلی
├── browser_manager.py      # مدیریت Browser/Context
├── logger_manager.py       # سیستم لاگینگ
└── retry.py                # Decorator و Exceptionهای Retry
```

**اصل جداسازی دغدغه‌ها:**
- `session_db.py` فقط با SQLite کار می‌کند
- `session_validator.py` فقط با Playwright کار می‌کند
- `session_manager.py` این دو را هماهنگ می‌کند
- هیچ وابستگی مستقیمی به UI وجود ندارد

---

## 🔄 جریان اجرا

### در شروع برنامه:

```
1. PlatformTab._check_session()
   ↓
2. SessionCheckWorker (در QThread)
   ↓
3. SessionManager.load()
   ├─ Session وجود ندارد → نمایش پیام + دکمه Login
   ├─ Session INVALID → نمایش هشدار + دکمه Login
   └─ Session VALID یا UNKNOWN
      ↓
4. SessionManager.validate(record, page)
   ├─ باز کردن صفحه protected
   ├─ بررسی نشانه‌های لاگین
   └─ به‌روزرسانی status در DB
   ↓
5. نمایش نتیجه در UI
   ├─ VALID → دکمه «حذف Session» فعال
   └─ INVALID → دکمه «ورود مجدد»
```

### در هنگام Login:

```
1. کاربر دکمه «ورود» را می‌زند
   ↓
2. صفحه ورود شماره
   ↓
3. LoginWorker شروع می‌شود (QThread)
   ↓
4. BrowserManager.start() - مرورگر باز می‌شود
   ↓
5. LoginManager.login()
   ↓
6. شماره وارد می‌شود + انتظار برای API
   ↓
7. code_provider() صدا زده می‌شود
   ├─ Signal به UI: code_needed
   ├─ UI صفحه کد را نمایش می‌دهد
   └─ Worker منتظر Future.result() می‌ماند
      (بدون timeout - کاربر تصمیم می‌گیرد)
   ↓
8. کاربر کد را وارد می‌کند (یا مرورگر را می‌بندد، یا لغو می‌کند)
   ↓
9. کد به Worker ارسال می‌شود
   ↓
10. کد وارد می‌شود + تأیید
   ↓
11. SessionManager.save_from_context()
   ↓
12. Session در SQLite ذخیره می‌شود
   ↓
13. Signal login_finished → QMessageBox موفقیت
```

---

## 💾 داده‌های ذخیره شده

### Cookies
- تمام کوکی‌ها با تمام attributes
- شامل: domain, path, expires, httpOnly, secure, sameSite

### LocalStorage
- تمام داده‌های localStorage به تفکیک origin
- مثال: `https://divar.ir` → `{token: "..."}`

### SessionStorage
- تمام داده‌های sessionStorage (در آینده)

### Tokens
- Access Token (در صورت وجود)
- Refresh Token (در صورت وجود)

### Metadata
- اطلاعات اضافی به صورت JSON
- مثال: `{"user_id": 123, "plan": "premium"}`

---

## 🧪 تست‌های پاس شده

تمام تست‌های زیر در `integration test` پاس شدند:

```
✓ core.retry (decorator + exceptions)
✓ core.session_models (Cookie, SessionRecord, StorageState, SessionStatus)
✓ StorageState roundtrip (playwright format ↔ internal)
✓ SessionRecord methods (is_valid, needs_login, touch)
✓ core.session_db (CRUD + history + get_latest)
✓ DB save (create new)
✓ DB save (update existing)
✓ DB load (by phone)
✓ DB update_status
✓ DB history (audit log)
✓ DB list_all
✓ DB delete
✓ DB get_latest
✓ Phone normalization (فارسی، انگلیسی، با/بدون +98)
✓ Code normalization (۶ رقم فارسی/انگلیسی)
✓ OTP normalization (۴ رقم)
```

---

## 🚀 استفاده

```bash
cd divar_manager
python ui/main.py
```

### تب دیوار / شیپور:

1. **بررسی خودکار Session** در شروع
2. اگر Session معتبر: نمایش اطلاعات + دکمه «حذف»
3. اگر Session نامعتبر: دکمه «ورود به حساب»
4. کلیک «ورود» → صفحه شماره موبایل
5. وارد کردن شماره → مرورگر باز می‌شود
6. انتظار کد (بدون timeout)
7. وارد کردن کد → Session ذخیره می‌شود
8. بازگشت به صفحه وضعیت

### هر زمان کاربر می‌تواند:
- ✖ **لغو** - برگشت به صفحه وضعیت
- 🚪 **حذف Session** - Logout
- 🔄 **بررسی مجدد** - اعتبارسنجی Session
- بستن مرورگر - خطا مدیریت می‌شود و دوباره می‌تواند تلاش کند

---

## ⏭️ مراحل بعدی پیشنهادی

1. **ماژول City / Category Selector**
2. **ماژول Listing Scraper**
3. **ماژول Ad Detail Extractor**
4. **Task / Status Manager**
5. **Scheduler & Worker Pool**

---

## 📝 نکات فنی

- **Type Hints:** تمام توابع Type Hint دارند
- **Docstrings:** تمام کلاس‌ها و متدهای public
- **Thread Safety:** ارتباط UI/Worker از طریق Signal
- **Dependency Injection:** SessionManager از بیرون تزریق می‌شود
- **Independent:** هیچ وابستگی به UI
- **Modular:** هر فایل یک مسئولیت مشخص دارد
- **Testable:** تست‌های unit و integration
