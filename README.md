# 🎯 Divar Manager — استخراج هوشمند شماره تماس و ارسال پیام خودکار

مدیریت خودکار آگهی‌های **دیوار** و **شیپور** با PySide6 + Playwright

---

## ✨ قابلیت‌ها

| قابلیت | دیوار | شیپور |
|--------|:-----:|:-----:|
| ورود خودکار (Login) | ✅ | ✅ |
| مدیریت Session و کوکی | ✅ | ✅ |
| استخراج آگهی (چند صفحه) | ✅ | ✅ |
| استخراج شماره تماس | ✅ | ✅ |
| ارسال پیام چت خودکار | ✅ | ✅ |
| حل خودکار کپچا (EasyOCR) | — | ✅ |
| Escape فیزیکی (Win32 API) | — | ✅ |
| وقفه تصادفی ضد کپچا | — | ✅ |
| ذخیره اکسل پوشه‌بندی شده | ✅ | ✅ |
| بروزرسانی زنده کوکی‌ها | ✅ | ✅ |
| تشخیص بسته شدن دستی مرورگر | ✅ | ✅ |

---

## 📦 نصب

```bash
pip install -r requirements.txt
playwright install chromium
```

نیازمندی‌ها (`requirements.txt`):
```
playwright==1.49.1
pydantic==2.9.2
openpyxl>=3.1.0
easyocr>=1.7.0
opencv-python-headless>=4.8.0
pillow>=10.0.0
numpy>=1.24.0
PySide6>=6.5.0
```

---

## 🚀 اجرا

```bash
python ui/main.py
```

---

## 📂 ساختار پروژه

```
├── core/
│   ├── browser_manager.py      # مدیریت مرورگر + مسدودسازی popup
│   ├── session_manager.py      # مدیریت نشست‌ها
│   ├── session_db.py           # دیتابیس نشست‌ها
│   ├── session_models.py       # مدل‌های داده
│   └── token_refresher.py      # تمدید خودکار توکن
├── modules/
│   ├── ad_extractor.py         # ⭐ استخراج شماره + چت + Escape + کپچا
│   ├── captcha_solver.py       # ⭐ حل خودکار کپچا با EasyOCR
│   ├── phone_selector.py       # انتخاب پیش‌شماره
│   ├── login/                  # ورود دیوار
│   └── sheypoor/login/         # ورود شیپور
├── ui/
│   ├── automation_tab.py       # تب اتوماسیون اصلی
│   ├── platform_tab.py         # تب مدیریت حساب‌ها
│   ├── main_window.py          # پنجره اصلی
│   └── logs_tab.py             # تب لاگ‌ها
├── data/
│   ├── sheypoor_cities.json    # شهرهای شیپور
│   └── sheypoor_categories.json# دسته‌بندی‌های شیپور
├── tests/                      # تست‌های خودکار
├── fetch_cities.py             # دریافت شهرهای دیوار
├── fetch_categories.py         # دریافت دسته‌بندی‌های دیوار
├── fetch_sheypoor_locations.py # دریافت شهرهای شیپور
├── fetch_sheypoor_categories.py# دریافت دسته‌بندی‌های شیپور
└── requirements.txt
```

---

## 🔐 حل خودکار کپچای شیپور

برنامه با **EasyOCR** کد امنیتی شیپور را تشخیص می‌دهد:
- **دو روش**: Raw (سریع) + Advanced (پیش‌پردازش قوی)
- **۶ تلاش** خودکار با کلیک روی «تغییر کد امنیتی»
- نمایش **روش حل** در لاگ (Raw / Advanced / یکسان)

---

## ⌨️ مدیریت پاپ‌آپ ویندوز

برای جلوگیری از دیالوگ `"Open Pick an app?"` در ویندوز:
- Escape فیزیکی از طریق **Win32 API** (`keybd_event`)
- Escape از طریق **Playwright keyboard**
- Escape از طریق **DOM KeyboardEvent**
- **قبل و بعد** از کلیک روی دکمه تماس
- **قبل و بعد** از ارسال پیام چت
- **بعد** از حل کپچا

---

## 📊 خروجی اکسل

شماره‌ها به صورت خودکار در فایل‌های اکسل پوشه‌بندی شده ذخیره می‌شوند:

```
data/extracted_phones/
  └── 0917_ بوشهر_ دسته کالای دیجیتال/
      └── شماره_های_0917.xlsx
```

---

## 🧪 تست‌ها

```bash
python -m pytest
```
