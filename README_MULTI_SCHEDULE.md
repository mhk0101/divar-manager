# قابلیت زمانبندی چندگانه - Multi Schedule

## چی شد؟
قبلا فقط 1 زمانبندی برای 1 شماره فعال بود. اگر زمانبندی دوم می‌زدی، قبلی از بین می‌رفت.

الان می‌تونی **همزمان چندین زمانبندی** برای هر شماره، هر پلتفرم (دیوار/شیپور)، هر شهر و هر دسته‌بندی بسازی.

---

## پیاده سازی فنی

### 1. `core/schedule_manager.py` (جدید)
یک Manager مرکزی:

- `ScheduleJob` dataclass: هر job یک شناسه یکتا `id` (8 کاراکتر)، پلتفرم، شماره، لیست شهرها (`cities` + `cities_names`)، دسته، pages، تنظیمات چت و استخراج، `interval_minutes`، وضعیت `waiting/running/paused`، `remaining_seconds`، `next_run_at`, `total_runs`, etc.

- `ScheduleManager`:
  - ذخیره در `data/schedules.json` به صورت list json
  - `add_job(job)` -> محاسبه `next_run = now + interval`
  - `remove_job(id)`, `stop_job(id)` (enabled=False, status=paused), `resume_job(id)`, `tick(1)` هر ثانیه remaining کم می‌کند
  - `get_due_jobs()` -> job هایی که remaining <=0 و enabled هستند
  - `mark_running`, `mark_finished` برای آپدیت بعد از اجرا

### 2. `ui/automation_tab.py` - بازنویسی بخش زمانبندی

قدیم:
```python
self._schedule_timer (singleShot)
self._schedule_remaining_seconds
self._schedule_running (bool)
```

جدید:
```python
self._schedule_manager = ScheduleManager()
self._jobs: dict[id, ScheduleJob] = ...
self._workers: dict[id, AutomationBrowserWorker] = ...
self._job_elapsed, _job_ads
self._global_ticker = QTimer(1000) -> _on_global_tick
```

- `_on_global_tick()` هر ثانیه:
  1. `schedule_manager.tick(1)` -> کاهش remaining همه job های فعال
  2. `get_due_jobs()` -> برای هر job که وقت اجرا رسیده و worker فعال ندارد، `_execute_job(id)` را صدا می‌زند
  3. `_emit_schedules()` -> لیست نمایش را به تب زمانبندی می‌فرستد

- `_create_job_from_current_settings()` : تنظیمات فعلی UI (شهرها، دسته، پیام، شماره، پلتفرم، interval) را می‌خواند و یک `ScheduleJob` می‌سازد.

- `_on_add_schedule_clicked()` : دکمه "➕ افزودن زمانبندی جدید"
  - چک می‌کند شماره انتخاب شده، interval>0، متن چت اگر فعال است پر باشد
  - چک تکراری (همان شماره/پلتفرم/شهر/دسته/بازه) -> سوال از کاربر
  - `schedule_manager.add_job(job)` + emit

- `_execute_job(job_id)`:
  - از job.cities و category_slug URL می‌سازد (`build_divar_url` / `build_sheypoor_url`)
  - `mark_running`
  - `AutomationBrowserWorker` جدید با تنظیمات همان job می‌سازد
  - سیگنال‌ها با lambda و job_id متصل می‌شوند تا بفهمیم کدام job
  - worker به `_workers[job_id]` اضافه و به ThreadPool می‌رود

- `_on_job_finished / _on_job_error / _on_job_status / _on_job_progress` : وضعیت job را آپدیت، worker را پاک، `mark_finished` (next_run = now+interval) و emit

- مدیریت per-job:
  - `stop_job_by_id(id)` -> stop + بستن مرورگر worker اگر باز است
  - `remove_job_by_id(id)` -> بستن worker + حذف از disk
  - `resume_job_by_id(id)` -> enabled=True

- UI جدید زمانبندی:
  - دکمه اصلی "شروع" فقط اجرای یکباره فوری است (دیگر زمانبندی تکی نمی‌سازد)
  - دکمه جدید "➕ افزودن زمانبندی جدید (تنظیمات فعلی)" -> زمانبندی چندگانه
  - "توقف همه" و "حذف همه" برای مدیریت گروهی
  - لیبل وضعیت: "✅ 3 زمانبندی فعال | به تب زمانبندی‌ها بروید"

- `settings_manager.py` هم قبلا فیکس شده بود: فایل بر اساس پلتفرم `divar_0912.json` تا تداخل نداشته باشد + انتخاب شهرها بر اساس id نه slug خالی

### 3. `ui/schedule_tab.py` - بازنویسی کامل

قدیم: فقط 7 ستون نمایش، هیچ دکمه کنترلی

جدید: 9 ستون
- شناسه، پلتفرم، شماره، شهرها، دسته، تکرار، اجرای بعدی (شمارش معکوس + ساعت)، وضعیت، عملیات

در ستون عملیات برای هر ردیف یک QWidget با دو دکمه:
- "⏸️ توقف" اگر فعال است / "▶️ ادامه" اگر متوقف است
- "🗑️ حذف"

سیگنال‌ها:
```python
stop_requested = Signal(str)  # job_id
remove_requested = Signal(str)
resume_requested = Signal(str)
```

در `main_window.py`:
```python
automation_tab.schedules_changed -> schedule_tab.update_schedules
schedule_tab.stop_requested -> automation_tab.stop_job_by_id
schedule_tab.remove_requested -> automation_tab.remove_job_by_id
schedule_tab.resume_requested -> automation_tab.resume_job_by_id
```

این باعث می‌شود کاربر هر زمانبندی را جداگانه کنترل کند.

### 4. همزمانی و منابع
- هر job یک `AutomationBrowserWorker` جدا و یک مرورگر جدا باز می‌کند (Playwright). یعنی اگر 3 زمانبندی همزمان اجرا شوند، 3 مرورگر باز می‌شود.
- برای جلوگیری از اجرای دوباره همان job زمانی که هنوز در حال اجراست، چک `if job_id in self._workers: continue`
- اگر 2 job با یک شماره همزمان اجرا شوند، مشکلی نیست (هر کدام fingerprint جدا). ولی اگر بخواهی جلوی همزمانی یک شماره را بگیری، می‌توانی در `_on_global_tick` چک کنی آیا worker دیگری با همان phone/platform در حال اجراست.

---

## نحوه استفاده کاربر

1. تب اتوماسیون: پلتفرم (دیوار)، شماره (0912...), شهر (تهران)، دسته (موبایل)، پیام چت، بازه (مثلاً 60 دقیقه)
2. دکمه "➕ افزودن زمانبندی جدید" -> پیام "زمانبندی اضافه شد ID: a1b2c3d4"
3. دوباره شهر را عوض کن (مثلاً اصفهان + خودرو) و بازه 30 دقیقه، دوباره افزودن -> حالا 2 زمانبندی فعال داری
4. برو تب "زمانبندی‌ها" -> 2 ردیف می‌بینی: هر کدام شمارش معکوس، وضعیت، دکمه توقف/حذف
5. می‌تونی یکی را متوقف کنی، دیگری همچنان کار می‌کند
6. پلتفرم را به شیپور عوض کن، یک شماره شیپور با یک شهر دیگر و 15 دقیقه، افزودن -> حالا 3 زمانبندی همزمان (2 دیوار + 1 شیپور)

همه زمانبندی‌ها در `data/schedules.json` ذخیره می‌شوند و بعد از بستن/باز کردن برنامه باقی می‌مانند.

---

## فایل‌های تغییر یافته
- `core/schedule_manager.py` [جدید]
- `core/settings_manager.py` [فیکس قبلی]
- `ui/automation_tab.py` [بازنویسی زمانبندی چندگانه + فیکس هنگ]
- `ui/schedule_tab.py` [بازنویسی کامل با کنترل per-job]
- `ui/main_window.py` [اتصال سیگنال‌های جدید]
