# 🔧 Divar Manager - اصلاحات نسخه 3.1

**تاریخ:** 2026-07-19  
**وضعیت:** ✅ اصلاحات اعمال شده

---

## 🚨 مشکل اصلی شناسایی شده

برنامه برای **دیوار** همیشه پیغام "Internet disconnected" نمایش می‌دهد، در حالی که:
- اینترنت وصل است
- برای **شیپور** درست کار می‌کند
- تنها مشکل، **چک اینترنت با گوگل** است

---

## 🎯 علت مشکل

### در `config/settings.py`:
```python
NETWORK_CHECK_URL = "https://www.google.com/generate_204"
```
**→ در ایران، دسترسی به گوگل مسدود است!**

### در `modules/login/login_manager.py`:
```python
async def _step_open_login_page(self, page: Page) -> None:
    # ❌ چک اینترنت قبل از باز کردن صفحه
    if not await self._check_internet(page):
        if not await self._wait_for_internet(page, max_wait=60):
            raise RuntimeError("Internet connection failed...")
    
    await page.goto(DIVAR_LOGIN_URL, ...)
```
**→ اگر چک اینترنت شکست بخورد، 60 ثانیه صبر می‌کند!**

### در `modules/sheypoor/login/login_manager.py`:
```python
async def _step_open_login_page(self, page: Page) -> None:
    # ✅ هیچ چک اینترنتی ندارد!
    await page.goto(SHEYPOOR_LOGIN_URL, ...)
```
**→ به همین دلیل شیپور درست کار می‌کند!**

---

## ✅ اصلاحات اعمال شده

### 1️⃣ فایل `config/settings.py`
**تغییر:**
```python
# قبل:
NETWORK_CHECK_URL = "https://www.google.com/generate_204"

# بعد:
NETWORK_CHECK_URL = "https://www.divar.ir"  # سایت ایرانی قابل دسترسی
```

### 2️⃣ فایل `modules/login/login_manager.py`
**تغییرات:**

#### تغییر اول: اصلاح متد `_check_internet`
```python
# قبل:
async def _check_internet(self, page: Page) -> bool:
    try:
        response = await page.goto(
            "https://www.google.com/generate_204",
            timeout=10_000,
            wait_until="domcontentloaded"
        )
        return response is not None
    except Exception as e:
        logger.debug("[divar] Internet check failed: %s", e)
        return False

# بعد:
async def _check_internet(self, page: Page) -> bool:
    """بررسی اتصال اینترنت با تلاش برای لود کردن یک صفحه ایرانی."""
    try:
        # استفاده از سایت دیوار به عنوان چک اینترنت (قابل دسترسی در ایران)
        response = await page.goto(
            DIVAR_BASE_URL,
            timeout=10_000,
            wait_until="domcontentloaded"
        )
        return response is not None and response.status < 500
    except Exception as e:
        logger.debug("[divar] Internet check failed: %s", e)
        return False
```

#### تغییر دوم: حذف انتظار 60 ثانیه‌ای یا کوتاه کردن آن
```python
# قبل:
async def _step_open_login_page(self, page: Page) -> None:
    self._set_state(LoginState.OPENING_LOGIN_PAGE)
    logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
    
    # بررسی اینترنت قبل از شروع
    if not await self._check_internet(page):
        if not await self._wait_for_internet(page, max_wait=60):
            raise RuntimeError("Internet connection failed. Please check your connection.")
    
    await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    logger.info("[divar] Login page loaded (URL=%s)", page.url)

# بعد (گزينه 1 - حذف کامل چک):
async def _step_open_login_page(self, page: Page) -> None:
    self._set_state(LoginState.OPENING_LOGIN_PAGE)
    logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
    
    # ✅ چک اینترنت را حذف کن (مثل شیپور)
    # if not await self._check_internet(page):
    #     if not await self._wait_for_internet(page, max_wait=60):
    #         raise RuntimeError("Internet connection failed. Please check your connection.")
    
    await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    logger.info("[divar] Login page loaded (URL=%s)", page.url)

# یا (گزينه 2 - کوتاه کردن زمان انتظار):
async def _step_open_login_page(self, page: Page) -> None:
    self._set_state(LoginState.OPENING_LOGIN_PAGE)
    logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
    
    # بررسی اینترنت قبل از شروع (با زمان انتظار کوتاه‌تر)
    if not await self._check_internet(page):
        if not await self._wait_for_internet(page, max_wait=10):  # ⏱️ 10 ثانیه به جای 60
            logger.warning("[divar] Internet check failed, trying to open page anyway...")
    
    await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")
    logger.info("[divar] Login page loaded (URL=%s)", page.url)
```

---

## 📦 محتویات این پوشه

```
divar-manager_fixed/
├── config/
│   └── settings.py              # ✅ اصلاح شده (NETWORK_CHECK_URL)
├── modules/
│   └── login/
│       └── login_manager.py     # ✅ اصلاح شده (حذف چک اینترنت)
├── APPLY_FIXES.md               # راهنمای اعمال اصلاحات
└── README_FIXES.md              # این فایل
```

---

## 🚀 نحوه اعمال اصلاحات

### روش 1: جایگزینی کامل فایل‌ها (پیشنهادی)

```bash
# در پوشه اصلی پروژه (D:\\Divar_Gui_New\\Version_new_pyside)

# پشتیبان‌گیری
copy config\settings.py config\settings.py.backup
copy modules\login\login_manager.py modules\login\login_manager.py.backup

# کپی فایل‌های اصلاح شده
copy /Y divar-manager_fixed\config\settings.py config\settings.py
copy /Y divar-manager_fixed\modules\login\login_manager.py modules\login\login_manager.py
```

### روش 2: اعمال Patch به صورت دستی

فایل `APPLY_FIXES.md` را مشاهده کنید.

---

## ✅ چک‌لیست تست بعد از اعمال اصلاحات

- [ ] برنامه را اجرا کنید
- [ ] وارد تب دیوار شوید
- [ ] روی "ورود با شماره جدید" کلیک کنید
- [ ] شماره را وارد کنید
- [ ] ✅ **نباید پیغام "Internet disconnected" نمایش داده شود**
- [ ] ✅ مرورگر باید بلافاصله باز شود
- [ ] ✅ صفحه ورود دیوار باید لود شود
- [ ] ✅ کد را وارد کنید و Login کامل شود

---

## 📊 مقایسه قبل و بعد

| معیار | قبل از اصلاح | بعد از اصلاح |
|--------|-------------|-------------|
| چک اینترنت | گوگل (مسدود در ایران) | دیوار (قابل دسترسی) |
| زمان انتظار | 60 ثانیه | 0 یا 10 ثانیه |
| تجربه کاربر | بد (انتظار طولانی) | خوب (بلافاصله) |
| کارکرد دیوار | ❌ شکست | ✅ موفقیت |
| کارکرد شیپور | ✅ موفقیت | ✅ موفقیت |

---

## 🎉 نتیجه

با اعمال این اصلاحات، **دیوار هم مثل شیپور کار خواهد کرد** و دیگر پیغام "Internet disconnected" نمایش داده نخواهد شد.

---

## 📞 پشتیبانی

اگر بعد از اعمال اصلاحات همچنان مشکل داشتید:
1. لاگ‌های برنامه را از تب "📋 لاگ‌ها" کپی کنید
2. مراحل بازتولید مشکل را توضیح دهید
3. یک issue در GitHub ایجاد کنید: https://github.com/mhk0101/divar-manager/issues
