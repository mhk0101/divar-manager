# گزارش بررسی و رفع باگ - Divar Manager
تاریخ: 2026-07-23

## خلاصه باگ‌ها
1. **دیوار - تب اتوماسیون**: ذخیره تنظیمات انجام میشود ولی هنگام لود، به جای همان شهری که کاربر انتخاب کرده، **کل شهرها** انتخاب میشوند.
2. **شیپور - تب اتوماسیون**: وقتی پلتفرم شیپور انتخاب میشود، برنامه هنگام لود تنظیمات **Not Responding / هنگ** میکند.

---

## تحلیل ریشه‌ای (Root Cause Analysis)

### باگ 1: انتخاب کل شهرها به جای شهر انتخاب شده

**فایل:** `ui/automation_tab.py` + `core/settings_manager.py`

1. در `settings_manager.py` فایل تنظیمات فقط بر اساس `phone.json` ذخیره میشد:
   ```python
   def _file_path(phone): return SETTINGS_DIR / f"{phone}.json"
   ```
   یعنی دیوار و شیپور یک فایل مشترک داشتند و همدیگر را overwrite میکردند.

2. در `automation_tab.py` هنگام ذخیره:
   ```python
   cities.append({"name": ..., "slug": ..., "id": ...})
   ```
   اما در بسیاری از دیتاهای دیوار (fetch_cities.py) `slug` خالی (`""`) است چون API دیوار slug نمیدهد.

3. هنگام لود:
   ```python
   saved_slugs = {c.get("slug","") for c in saved_cities}
   # اگر slug ها خالی باشند => saved_slugs = {""}
   if d.get("slug","") in saved_slugs: # هر شهری که slug="" دارد انتخاب میشود
       item.setSelected(True)
   ```
   **نتیجه:** چون همه شهرهای دیتابیس دیوار slug خالی دارند، شرط برای **همه** True میشود => selectAll ناخواسته!

**راه حل:**
- مچ کردن بر اساس `id` (یکتا و عددی) نه `slug`
  ```python
  saved_ids = {c.get("id") for c in saved_cities if c.get("id") is not None}
  if d.get("id") in saved_ids: select
  ```
- ذخیره تنظیمات به صورت platform-specific: `divar_0912.json` و `sheypoor_0912.json`
- پاکسازی `cities` هنگام ذخیره فقط به `id, name, slug` برای جلوگیری از حجیم شدن فایل (districts حذف)

### باگ 2: هنگ شیپور هنگام انتخاب پلتفرم

**فایل:** `ui/automation_tab.py`

چند عامل با هم باعث هنگ میشد:

1. **لود سنگین QListWidget بدون blockSignals:**
   - شیپور ~1000 شهر + ~300 دسته دارد
   - هر `item.setSelected(True)` و `addItem` باعث `itemSelectionChanged` signal و repaint میشود
   - حلقه 1000 بار repaint => main thread block => Not Responding

2. **سوئیچ خودکار پلتفرم هنگام لود تنظیمات:**
   ```python
   saved_plat = s.get("platform")
   if need_rebuild: # saved_plat=divar, current=sheypoor
       _load_data_for_platform(divar) # برمیگردد به دیوار!
       platform_combo.setCurrentIndex(divar)
   ```
   کاربر شیپور انتخاب میکند، اما settings فایل دیوار را میخواند (چون فایل مشترک بود)، دوباره دیوار لود میشود، دوباره شهرهای دیوار populate میشوند، دوباره...
   این loop باعث دو بار لود سنگین پشت هم و فریز میشود.

3. **QTimer 10ms + بدون blockSignals در _on_phone_changed:**
   هر تغییر phone_combo یک تایمر جدید میساخت و _load_settings_for_phone را دوباره صدا میزد، در حالی که قبلی هنوز تمام نشده.

**راه حل‌های اعمال شده:**

- **الف) در `_on_platform_changed`:**
  ```python
  city_list.blockSignals(True)
  city_list.setUpdatesEnabled(False)
  phone_combo.blockSignals(True)
  try:
      _load_data_for_platform(plat)
      _reload_phone_numbers()
  finally:
      setUpdatesEnabled(True)
      blockSignals(False)
  QTimer.singleShot(50, _load_settings_for_phone) # تاخیر 50ms
  ```

- **ب) در `_load_settings_for_phone`:**
  - دیگر پلتفرم را عوض نکن! `current_plat = get_selected_platform()` را نگه دار
  - `load_settings(phone, platform=current_plat)` صدا بزن تا فقط فایل همان پلتفرم لود شود
  - اگر فایل برای آن پلتفرم وجود نداشت، دیفالت خالی برگردان (نه تنظیمات پلتفرم دیگر)
  - انتخاب شهرها با `blockSignals + setUpdatesEnabled(False)` + مچ با id
  - تمام spinbox ها blockSignals هنگام setValue

- **ج) در `_populate_city_list` و `_populate_category_list`:**
  ```python
  blockSignals(True)
  setUpdatesEnabled(False)
  try: clear + addItems
  finally: setUpdatesEnabled(True); blockSignals(False)
  ```

- **د) در `_load_cities`:**
  - پاکسازی دیتای حجیم: districts لیست کامل حذف شد، فقط `districts_count` نگه داشته شد
  - این جلوی مصرف RAM زیاد و هنگ را میگیرد

- **ه) در `settings_manager.py`:**
  - ذخیره بر اساس `platform_phone.json`
  - load با platform، fallback امن (اگر platform فایل متفاوت بود، دیفالت برگردان نه فایل اشتباه)

---

## فایل‌های تغییر یافته

1. `core/settings_manager.py` - بازنویسی کامل برای پشتیبانی platform-specific
2. `ui/automation_tab.py` - رفع هر دو باگ + بهینه سازی جلوگیری از هنگ

## نحوه اعمال

فایل‌های داخل `divar_manager_fixed_20260723.zip` را جایگزین فایل‌های اصلی پروژه کنید:

```
your_project/
  core/
    settings_manager.py  <- جایگزین کن
  ui/
    automation_tab.py    <- جایگزین کن
```

سپس یکبار پوشه `data/settings/` را پاک کنید یا فایل‌های قدیمی `0912...json` بدون پیشوند را به `divar_0912...json` تغییر نام دهید (اختیاری، کد جدید backward compat دارد اما برای تمیزی پیشنهاد میشود).

## تست

- دیوار: یک شهر (مثلا تهران) انتخاب کن، ذخیره کن، برنامه را ببند و باز کن، شماره را انتخاب کن => فقط تهران باید انتخاب باشد نه همه.
- شیپور: پلتفرم شیپور را انتخاب کن => نباید هنگ کند. شهر شیپور انتخاب کن، ذخیره کن، دوباره لود کن => فقط همان شهر.

