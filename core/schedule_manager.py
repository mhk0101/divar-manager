"""
ScheduleManager — مدیریت زمانبندی‌های چندگانه همزمان برای دیوار و شیپور

هر زمانبندی شامل:
- پلتفرم (divar/sheypoor)
- شماره تلفن
- شهرها، دسته‌بندی
- تنظیمات استخراج و چت
- فاصله تکرار (دقیقه)
- وضعیت: waiting, running, paused, stopped

ذخیره‌سازی در data/schedules.json
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any


SCHEDULES_FILE = Path(__file__).resolve().parent.parent / "data" / "schedules.json"


@dataclass
class ScheduleJob:
    """یک زمانبندی مستقل"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    platform: str = "divar"  # divar / sheypoor
    phone: str = ""
    cities: List[Dict] = field(default_factory=list)  # [{'id':..., 'name':..., 'slug':...}]
    cities_names: List[str] = field(default_factory=list)
    category_slug: Optional[str] = None
    category_name: str = "همه دسته‌ها"
    pages: int = 3
    chat_enabled: bool = True
    chat_message: str = ""
    extract_phone: bool = True
    max_phones: int = 10
    max_chats: int = 10
    sync_phone_chat: bool = True
    interval_minutes: int = 60
    cookie_interval: int = 60

    # وضعیت اجرایی
    status: str = "waiting"  # waiting, running, paused, stopped, error
    remaining_seconds: int = 0
    next_run_at: Optional[str] = None  # ISO string
    last_run_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_runs: int = 0
    is_running: bool = False
    elapsed_seconds: int = 0
    total_ads: int = 0
    enabled: bool = True  # برای pause/resume

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleJob":
        # سازگاری با فایل‌های قدیمی
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        # اگر cities قدیمی فقط list of ids باشد، تبدیل کن
        if "cities" in filtered and filtered["cities"]:
            cleaned_cities = []
            for c in filtered["cities"]:
                if isinstance(c, dict):
                    cleaned_cities.append({
                        "id": c.get("id"),
                        "name": c.get("name", ""),
                        "slug": c.get("slug", ""),
                    })
                elif isinstance(c, str):
                    cleaned_cities.append({"id": None, "name": c, "slug": ""})
            filtered["cities"] = cleaned_cities
        return cls(**filtered)

    def to_display_dict(self) -> Dict[str, Any]:
        """برای نمایش در تب زمانبندی‌ها"""
        remaining = self.remaining_seconds
        return {
            "id": self.id,
            "platform": self.platform,
            "phone": self.phone,
            "cities": ", ".join(self.cities_names) if self.cities_names else "همه شهرها",
            "cities_raw": self.cities_names,
            "category": self.category_name,
            "category_slug": self.category_slug,
            "interval_minutes": self.interval_minutes,
            "remaining_seconds": remaining,
            "next_run": self.next_run_at,
            "status": "🟢 در حال اجرا" if self.is_running else (
                "⏸️ متوقف" if not self.enabled else (
                    "⏳ در انتظار" if self.status == "waiting" else self.status
                )
            ),
            "status_raw": self.status,
            "running": self.enabled and self.status != "stopped",
            "in_progress": self.is_running,
            "enabled": self.enabled,
            "total_runs": self.total_runs,
            "elapsed": self.elapsed_seconds,
            "ads": self.total_ads,
            "pages": self.pages,
            "phone_label": self.phone,
        }


class ScheduleManager:
    """مدیریت ذخیره و بازیابی زمانبندی‌های چندگانه"""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or SCHEDULES_FILE
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, ScheduleJob] = {}
        self.load()

    def load(self) -> List[ScheduleJob]:
        if not self.file_path.exists():
            self._jobs = {}
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            jobs = {}
            for item in data:
                try:
                    job = ScheduleJob.from_dict(item)
                    # هنگام لود، اگر job در حال اجرا بود، آن را به waiting برگردان
                    if job.is_running:
                        job.is_running = False
                        job.status = "waiting"
                    # اگر enabled نباشد، متوقف نگه دار
                    if not job.enabled:
                        job.status = "paused"
                    jobs[job.id] = job
                except Exception as e:
                    print(f"[ScheduleManager] skip invalid job: {e}")
                    continue
            self._jobs = jobs
            return list(self._jobs.values())
        except Exception as e:
            print(f"[ScheduleManager] load error: {e}")
            self._jobs = {}
            return []

    def save(self):
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump([j.to_dict() for j in self._jobs.values()], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ScheduleManager] save error: {e}")

    def add_job(self, job: ScheduleJob) -> ScheduleJob:
        # محاسبه next_run
        if job.interval_minutes > 0:
            next_run = datetime.now() + timedelta(minutes=job.interval_minutes)
            job.next_run_at = next_run.isoformat()
            job.remaining_seconds = job.interval_minutes * 60
            job.status = "waiting"
        else:
            job.next_run_at = None
            job.remaining_seconds = 0
            job.status = "stopped"
        job.enabled = True
        self._jobs[job.id] = job
        self.save()
        return job

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self.save()
            return True
        return False

    def get_job(self, job_id: str) -> Optional[ScheduleJob]:
        return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs) -> Optional[ScheduleJob]:
        job = self._jobs.get(job_id)
        if not job:
            return None
        for k, v in kwargs.items():
            if hasattr(job, k):
                setattr(job, k, v)
        self.save()
        return job

    def list_jobs(self) -> List[ScheduleJob]:
        return list(self._jobs.values())

    def list_active_jobs(self) -> List[ScheduleJob]:
        return [j for j in self._jobs.values() if j.enabled and j.status != "stopped"]

    def stop_job(self, job_id: str) -> Optional[ScheduleJob]:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = False
            job.status = "paused"
            job.is_running = False
            self.save()
        return job

    def resume_job(self, job_id: str) -> Optional[ScheduleJob]:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = True
            job.status = "waiting"
            if job.interval_minutes > 0 and job.remaining_seconds <= 0:
                job.remaining_seconds = job.interval_minutes * 60
                job.next_run_at = (datetime.now() + timedelta(seconds=job.remaining_seconds)).isoformat()
            self.save()
        return job

    def reset_job_timer(self, job_id: str) -> Optional[ScheduleJob]:
        job = self._jobs.get(job_id)
        if job and job.interval_minutes > 0:
            job.remaining_seconds = job.interval_minutes * 60
            job.next_run_at = (datetime.now() + timedelta(minutes=job.interval_minutes)).isoformat()
            job.status = "waiting"
            job.is_running = False
            self.save()
        return job

    def mark_running(self, job_id: str):
        job = self._jobs.get(job_id)
        if job:
            job.is_running = True
            job.status = "running"
            job.last_run_at = datetime.now().isoformat()
            job.elapsed_seconds = 0
            job.total_ads = 0
            self.save()

    def mark_finished(self, job_id: str, total_ads: int = 0):
        job = self._jobs.get(job_id)
        if job:
            job.is_running = False
            job.total_runs += 1
            job.total_ads = total_ads
            if job.enabled and job.interval_minutes > 0:
                job.status = "waiting"
                job.remaining_seconds = job.interval_minutes * 60
                job.next_run_at = (datetime.now() + timedelta(minutes=job.interval_minutes)).isoformat()
            else:
                job.status = "stopped"
                job.remaining_seconds = 0
                job.next_run_at = None
            self.save()

    def tick(self, seconds: int = 1):
        """کاهش remaining برای همه job های فعال - هر ثانیه صدا زده میشود"""
        changed = False
        for job in self._jobs.values():
            if not job.enabled or job.is_running or job.status == "stopped":
                continue
            if job.remaining_seconds > 0:
                job.remaining_seconds -= seconds
                if job.remaining_seconds < 0:
                    job.remaining_seconds = 0
                changed = True
        if changed:
            # ذخیره هر 10 ثانیه یکبار برای جلوگیری از IO زیاد - اینجا ساده هر بار ذخیره نمیکنیم
            pass

    def get_due_jobs(self) -> List[ScheduleJob]:
        """job هایی که زمان اجرایشان رسیده"""
        due = []
        for job in self._jobs.values():
            if not job.enabled or job.is_running or job.status in ("stopped", "paused"):
                continue
            if job.remaining_seconds <= 0 and job.interval_minutes > 0:
                due.append(job)
        return due

    def clear_all(self):
        self._jobs.clear()
        self.save()
