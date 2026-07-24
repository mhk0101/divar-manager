# 📋 راهنمای اعمال اصلاحات

## 🎯 هدف
حذف مشکل "Internet disconnected" برای دیوار و بهبود کارایی برنامه.

---

## 📦 محتویات پوشه

```
divar-manager_fixed/
├── config/
│   └── settings.py              # فایل اصلاح شده
├── modules/
│   └── login/
│       └── login_manager.py     # فایل اصلاح شده
├── APPLY_FIXES.md               # این فایل
└── README_FIXES.md              # توضیحات کامل
```

---

## 🚀 روش 1: جایگزینی کامل فایل‌ها (پیشنهادی)

### مرحله 1: پشتیبان‌گیری از فایل‌های اصلی

```cmd
cd D:\Divar_Gui_New\Version_new_pyside

:: ایجاد پوشه backup
mkdir backup_20260719

:: پشتیبان‌گیری
copy config\settings.py backup_20260719\settings.py
copy modules\login\login_manager.py backup_20260719\login_manager.py
```

### مرحله 2: کپی فایل‌های اصلاح شده

```cmd
:: کپی فایل تنظیمات
copy /Y divar-manager_fixed\config\settings.py config\settings.py

:: کپی فایل login_manager
copy /Y divar-manager_fixed\modules\login\login_manager.py modules\login\login_manager.py
```

### مرحله 3: تست برنامه

```cmd
python ui\main.py
```

---

## 🔧 روش 2: اعمال تغییرات به صورت دستی

### تغییر 1: فایل `config/settings.py`

**خط 67 را پیدا کنید:**
```python
NETWORK_CHECK_URL: str = "https://www.google.com/generate_204"
```

**به این تغییر دهید:**
```python
NETWORK_CHECK_URL: str = "https://www.divar.ir"  # سایت ایرانی قابل دسترسی
```

---

### تغییر 2: فایل `modules/login/login_manager.py`

#### تغییر A: حذف چک اینترنت در `_step_open_login_page`

**خط‌های حدود 207-213 را پیدا کنید:**
```python
async def _step_open_login_page(self, page: Page) -> None:
    self._set_state(LoginState.OPENING_LOGIN_PAGE)
    logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
    
    # بررسی اینترنت قبل از شروع
    if not await self._check_internet(page):
        if not await self._wait_for_internet(page, max_wait=60):
            raise RuntimeError("Internet connection failed. Please check your connection.")
    
    await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
```

**به این تغییر دهید:**
```python
async def _step_open_login_page(self, page: Page) -> None:
    self._set_state(LoginState.OPENING_LOGIN_PAGE)
    logger.info("[divar] Opening login page: %s", DIVAR_LOGIN_URL)
    
    # ✅ چک اینترنت را حذف کن (مثل شیپور)
    # if not await self._check_internet(page):
    #     if not await self._wait_for_internet(page, max_wait=60):
    #         raise RuntimeError("Internet connection failed. Please check your connection.")
    
    await page.goto(DIVAR_LOGIN_URL, wait_until="domcontentloaded")
```

#### تغییر B: اصلاح متد `_check_internet` (اختیاری)

**خط‌های حدود 185-195 را پیدا کنید:**
```python
async def _check_internet(self, page: Page) -> bool:
    """بررسی اتصال اینترنت با تلاش برای لود کردن یک صفحه ساده."""
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
```

**به این تغییر دهید:**
```python
async def _check_internet(self, page: Page) -> bool:
    """بررسی اتصال اینترنت با تلاش برای لود کردن یک صفحه ایرانی."""
    try:
        # ✅ استفاده از سایت دیوار به عنوان چک اینترنت
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

---

## ✅ چک‌لیست پس از اعمال تغییرات

- [ ] برنامه را اجرا کنید: `python ui\main.py`
- [ ] وارد تب **دیوار** شوید
- [ ] روی **"ورود با شماره جدید"** کلیک کنید
- [ ] شماره موبایل را وارد کنید
- [ ] ✅ **نباید پیغام "⚠️ Internet disconnected" نمایش داده شود**
- [ ] ✅ مرورگر باید **بلافاصله** باز شود
- [ ] ✅ صفحه ورود دیوار (`divar.ir/my-divar`) باید لود شود
- [ ] کد تأیید را وارد کنید
- [ ] ✅ Login باید با موفقیت کامل شود
- [ ] ✅ Session باید ذخیره شود

---

## 🎯 اگر هنوز مشکل داشتید

### مشکل 1: Selectorها کار نمی‌کنند
**علت:** سایت دیوار ممکن است ساختار HTML خود را تغییر داده باشد.

**راه‌حل:**
1. مرورگر را به صورت دستی باز کنید
2. صفحه `divar.ir/my-divar` را باز کنید
3. روی "ورود به حساب کاربری" کلیک کنید
4. Inspect Element بزنید و selectorهای جدید را پیدا کنید
5. فایل `modules/login/selectors.py` را به‌روزرسانی کنید

### مشکل 2: مرورگر باز نمی‌شود
**علت:** Playwright ممکن است به درستی نصب نشده باشد.

**راه‌حل:**
```cmd
playwright install chromium
```

### مشکل 3: خطای Import
**علت:** وابستگی‌ها نصب نیستند.

**راه‌حل:**
```cmd
pip install -r requirements.txt
pip install -r requirements_gui.txt
```

---

## 📞 دریافت کمک

اگر پس از اعمال تمام تغییرات همچنان مشکل داشتید:

1. **لاگ‌ها** را از تب "📋 لاگ‌ها" کپی کنید
2. **مراحل بازتولید** مشکل را توضیح دهید
3. **نسخه پایتون** خود را گزارش دهید: `python --version`
4. **سیستم عامل** خود را گزارش دهید

---

## 🎉 تبریک!

با اعمال این تغییرات، **دیوار هم مثل شیپور کار خواهد کرد** و دیگر با مشکل "Internet disconnected" مواجه نخواهید شد.
