"""
تنظیمات سراسری پروژه Divar Manager.

تمام مقادیر ثابت (URLها، مسیرها، Timeoutها) در این فایل نگهداری می‌شوند
تا در صورت نیاز به تغییر، فقط یک نقطه ویرایش وجود داشته باشد.
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# مسیرها
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"
SESSIONS_DIR: Path = DATA_DIR / "sessions"
DB_DIR: Path = DATA_DIR / "db"
TEMP_DIR: Path = DATA_DIR / "temp"

# اطمینان از وجود دایرکتوری‌ها در زمان import
for _d in (DATA_DIR, SESSIONS_DIR, DB_DIR, TEMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
SESSION_DB_PATH: Path = DB_DIR / "sessions.db"


# ---------------------------------------------------------------------------
# URL های اصلی
# ---------------------------------------------------------------------------
DIVAR_BASE_URL: str = "https://divar.ir"
DIVAR_LOGIN_URL: str = f"{DIVAR_BASE_URL}/my-divar"
DIVAR_PROTECTED_URL: str = f"{DIVAR_BASE_URL}/my-divar"  # صفحه‌ای که نیاز به Login دارد

SHEYPOOR_BASE_URL: str = "https://www.sheypoor.com"
SHEYPOOR_LOGIN_URL: str = f"{SHEYPOOR_BASE_URL}/session"
SHEYPOOR_PROTECTED_URL: str = f"{SHEYPOOR_BASE_URL}/session/myAccount/myListings/all"

# Endpointهای API که در طول Login دیوار فراخوانی می‌شوند
AUTH_INITIATE_ENDPOINT: str = "/v8/auth/open-initiate-page"
AUTH_VERIFY_ENDPOINT: str = "/v8/auth/open-confirm-page"


# ---------------------------------------------------------------------------
# Timeout ها (میلی‌ثانیه)
#
# توجه: برای انتظار کد تأیید از کاربر، هیچ timeout ثابتی نداریم.
# کاربر خودش تصمیم می‌گیرد چه زمانی کد را وارد کند یا مرورگر را ببندد.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT_MS: int = 30_000
NAVIGATION_TIMEOUT_MS: int = 60_000
POST_LOGIN_TIMEOUT_MS: int = 20_000
SESSION_VALIDATION_TIMEOUT_MS: int = 15_000


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------
HEADLESS: bool = False
SLOW_MO_MS: int = 50
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Retry / Error Handling
# ---------------------------------------------------------------------------
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SEC: float = 2.0
NETWORK_CHECK_URL: str = "https://www.google.com/generate_204"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
# نام پیش‌فرض فایل Session (فقط برای backward compatibility)
DEFAULT_SESSION_FILE: str = "divar_session.json"

# Session منقضی می‌شود اگر قدیمی‌تر از این باشد (ثانیه)
# None = انقضا فقط بر اساس اعتبارسنجی واقعی
SESSION_MAX_AGE_SECONDS: int | None = None  # فعلاً انقضای زمانی نداریم
