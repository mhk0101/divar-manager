# راه‌اندازی سریع Divar & Sheypoor Manager

## اجرای یک‌کلیکی در ویندوز

1. پروژه را از GitHub دانلود یا Clone کنید.
2. مطمئن شوید Python 3.10 یا 3.11 نصب است و گزینه **Add Python to PATH** فعال بوده است.
3. روی فایل زیر دوبار کلیک کنید:

```bat
setup_and_run.bat
```

این فایل به‌صورت خودکار انجام می‌دهد:

- ساخت محیط مجازی `.venv`
- نصب پکیج‌های `requirements.txt` و `requirements_gui.txt`
- نصب Chromium برای Playwright
- بررسی فایل‌های شهر و دسته‌بندی
- اجرای برنامه

بعد از نصب اولیه، برای دفعات بعد می‌توانید فقط اجرا کنید:

```bat
run.bat
```

## فایل‌های داده‌ای که همراه پروژه Push شده‌اند

این فایل‌ها عمومی هستند و برای کارکرد تب اتوماسیون لازم‌اند:

```text
data/cities.json
data/categories.json
data/sheypoor_cities.json
data/sheypoor_categories.json
```

## فایل‌هایی که نباید Push شوند

این موارد شامل داده‌های شخصی/حساس یا خروجی‌های برنامه هستند:

```text
data/db/
data/sessions/
data/settings/
data/temp/
data/extracted_ads/
data/extracted_phones/
data/fingerprints.json
config/phone_numbers.json
*.db
*_session.json
*.xlsx
*.csv
.venv/
__pycache__/
```

## به‌روزرسانی شهرها و دسته‌بندی‌ها

اگر APIها در دسترس باشند، می‌توانید این اسکریپت‌ها را اجرا کنید:

```bat
.venv\Scripts\python.exe fetch_cities.py
.venv\Scripts\python.exe fetch_sheypoor_locations.py
.venv\Scripts\python.exe fetch_sheypoor_categories.py
```

سپس فایل‌های JSON داخل `data/` را Commit کنید.
