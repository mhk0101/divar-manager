"""
CaptchaSolver - حل‌کننده خودکار کد امنیتی شیپور با EasyOCR.

ویژگی‌ها:
- تشخیص خودکار مودال کپچای شیپور («کد امنیتی»)
- استخراج تصویر کپچا (base64) و ذخیره موقت
- حل با EasyOCR در دو روش Raw و Advanced
- تلاش تا ۶ بار با کلیک روی «تغییر کد امنیتی» در صورت شکست
- وارد کردن کد حل‌شده و کلیک روی دکمه تأیید
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import Page

logger = logging.getLogger("divar.captcha_solver")

# -------------------------------
# تلاش برای import کتابخانه‌های OCR
# -------------------------------
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("OpenCV (cv2) نصب نیست. روش Advanced غیرفعال می‌شود.")

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    logger.warning("EasyOCR نصب نیست. حل خودکار کپچا غیرفعال است.")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# -------------------------------
# ثابت‌ها
# -------------------------------
MAX_CAPTCHA_ATTEMPTS = 6

# سلکتورهای مودال کپچای شیپور
CAPTCHA_MODAL_SELECTOR = "h2[data-test-id='modal-title']"
CAPTCHA_IMG_SELECTOR = "img[alt='Captcha']"
CAPTCHA_INPUT_SELECTOR = "[data-test-id='number-input-code'] input[name='code']"
CAPTCHA_SUBMIT_SELECTOR = "button[type='submit']"
CAPTCHA_CLOSE_SELECTOR = "button[data-test-id='close-modal']"
CAPTCHA_CHANGE_TEXT = "تغییر کد امنیتی"


def _preprocess_image(image_path: str):
    """پیش‌پردازش قوی برای افزایش دقت EasyOCR (روش Advanced)."""
    if not HAS_CV2:
        return None
    img = cv2.imread(image_path)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    return morph


def _solve_raw(image_path: str) -> str:
    """روش Raw: تصویر خاکستری ساده بدون پیش‌پردازش سنگین."""
    if not HAS_EASYOCR or not HAS_CV2:
        return ""
    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result = reader.readtext(
            gray,
            allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            paragraph=False,
        )
        if result:
            text = ''.join(r[1] for r in result)
            return re.sub(r'[^A-Za-z0-9]', '', text.strip())
        return ""
    except Exception as e:
        logger.debug("Raw OCR error: %s", e)
        return ""


def _solve_advanced(image_path: str) -> str:
    """روش Advanced: پیش‌پردازش قوی + threshold پایین‌تر."""
    if not HAS_EASYOCR or not HAS_CV2:
        return ""
    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        processed = _preprocess_image(image_path)
        if processed is None:
            return ""
        result = reader.readtext(
            processed,
            allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            paragraph=False,
            text_threshold=0.1,
            width_ths=0.7,
            height_ths=0.7,
        )
        if result:
            text = ''.join(r[1] for r in result)
            return re.sub(r'[^A-Za-z0-9]', '', text.strip())
        return ""
    except Exception as e:
        logger.debug("Advanced OCR error: %s", e)
        return ""


def _solve_captcha_image(image_path: str) -> Optional[str]:
    """
    تلاش برای حل تصویر کپچا با دو روش Raw و Advanced.
    بازگرداندن پاسخ معتبر (حداقل ۳ کاراکتر) یا None.
    """
    raw_result = _solve_raw(image_path)
    adv_result = _solve_advanced(image_path)

    logger.debug("Captcha OCR results - Raw: %r, Advanced: %r", raw_result, adv_result)

    # هر دو جواب دادند و یکسان هستند
    if raw_result and adv_result and raw_result == adv_result:
        return raw_result

    # هر دو جواب دادند ولی متفاوت — Raw را ترجیح بده (سریع‌تر)
    if raw_result and len(raw_result) >= 3:
        return raw_result
    if adv_result and len(adv_result) >= 3:
        return adv_result
    if raw_result:
        return raw_result

    return None


async def _is_captcha_visible(page: Page) -> bool:
    """بررسی وجود مودال کپچای شیپور روی صفحه."""
    try:
        modal = page.locator(CAPTCHA_MODAL_SELECTOR).first
        if await modal.count() > 0 and await modal.is_visible():
            text = (await modal.inner_text()).strip()
            if "کد امنیتی" in text:
                return True
        return False
    except Exception:
        return False


async def _capture_captcha_image(page: Page) -> Optional[str]:
    """
    استخراج تصویر کپچا از مودال شیپور.
    تصویر base64 را decode کرده و در فایل موقت ذخیره می‌کند.
    مسیر فایل موقت را برمی‌گرداند.
    """
    try:
        img_el = page.locator(CAPTCHA_IMG_SELECTOR).first
        if await img_el.count() == 0:
            return None

        src = await img_el.get_attribute("src") or ""
        if not src.startswith("data:image/"):
            # ممکن است src معمولی باشد - اسکرین‌شات از المان
            screenshot_bytes = await img_el.screenshot()
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(screenshot_bytes)
            tmp.close()
            return tmp.name

        # src="data:image/png;base64,..."
        _, b64_data = src.split(",", 1)
        img_bytes = base64.b64decode(b64_data)

        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(img_bytes)
        tmp.close()
        return tmp.name

    except Exception as e:
        logger.debug("Failed to capture captcha image: %s", e)
        return None


async def _click_change_captcha(page: Page) -> bool:
    """کلیک روی متن «تغییر کد امنیتی» برای دریافت تصویر جدید."""
    try:
        change_btn = page.locator(f"p:has-text('{CAPTCHA_CHANGE_TEXT}')").first
        if await change_btn.count() > 0 and await change_btn.is_visible():
            await change_btn.click(force=True, timeout=3000)
            await page.wait_for_timeout(1500)
            logger.debug("Clicked 'تغییر کد امنیتی' for new captcha image")
            return True
        return False
    except Exception as e:
        logger.debug("Failed to click change captcha: %s", e)
        return False


async def _submit_captcha(page: Page, code: str) -> bool:
    """وارد کردن کد حل‌شده در فیلد و کلیک روی دکمه تأیید."""
    try:
        input_el = page.locator(CAPTCHA_INPUT_SELECTOR).first
        if await input_el.count() == 0:
            return False

        await input_el.click(force=True, timeout=2000)
        await page.wait_for_timeout(300)
        await input_el.fill("")
        await page.wait_for_timeout(200)
        await input_el.fill(code)
        await page.wait_for_timeout(500)

        submit_btn = page.locator(CAPTCHA_SUBMIT_SELECTOR).first
        if await submit_btn.count() > 0:
            # دکمه ممکن است disabled باشد تا وقتی کد وارد شود
            await page.wait_for_timeout(500)
            is_disabled = await submit_btn.is_disabled()
            if not is_disabled:
                await submit_btn.click(force=True, timeout=3000)
                await page.wait_for_timeout(2000)
                return True

            # اگر همچنان disabled است، Enter بزن
            await input_el.press("Enter")
            await page.wait_for_timeout(2000)
            return True

        return False

    except Exception as e:
        logger.debug("Failed to submit captcha: %s", e)
        return False


async def solve_sheypoor_captcha(
    page: Page,
    progress_callback: Optional[Callable[[str], None]] = None,
    max_attempts: int = MAX_CAPTCHA_ATTEMPTS,
) -> bool:
    """
    تلاش برای حل خودکار کپچای شیپور.

    مراحل:
    1. بررسی وجود مودال کپچا
    2. استخراج تصویر کپچا
    3. حل با EasyOCR (Raw + Advanced)
    4. وارد کردن کد و تأیید
    5. اگر مودال همچنان باز بود → کلیک روی «تغییر کد امنیتی» و تلاش مجدد
    6. حداکثر ۶ بار تلاش

    Returns:
        True اگر کپچا با موفقیت حل شد یا اصلاً کپچایی وجود نداشت.
        False اگر پس از ۶ تلاش حل نشد.
    """
    if not HAS_EASYOCR:
        if progress_callback:
            progress_callback("⚠️ کتابخانه EasyOCR نصب نیست. حل خودکار کپچا غیرفعال است.")
        logger.warning("EasyOCR not installed; captcha solving is disabled.")
        return False

    # بررسی اولیه: آیا اصلاً کپچا وجود دارد؟
    if not await _is_captcha_visible(page):
        logger.debug("No captcha modal detected on page.")
        return True

    if progress_callback:
        progress_callback("🔐 کد امنیتی شیپور شناسایی شد! در حال حل خودکار با EasyOCR...")

    for attempt in range(1, max_attempts + 1):
        if progress_callback:
            progress_callback(f"🔍 تلاش {attempt}/{max_attempts} برای حل کد امنیتی شیپور...")

        # ۱. استخراج تصویر کپچا
        img_path = await _capture_captcha_image(page)
        if not img_path:
            logger.warning("Captcha attempt %d: Failed to capture image", attempt)
            if attempt < max_attempts:
                await _click_change_captcha(page)
                await page.wait_for_timeout(1000)
            continue

        try:
            # ۲. حل تصویر با OCR
            code = _solve_captcha_image(img_path)

            if code and len(code) >= 3:
                if progress_callback:
                    progress_callback(f"✅ کد حل شد: {code}")

                # ۳. وارد کردن کد و تأیید
                submitted = await _submit_captcha(page, code)

                # ۴. بررسی ناپدید شدن مودال
                await page.wait_for_timeout(2000)

                if not await _is_captcha_visible(page):
                    if progress_callback:
                        progress_callback(f"🎉 کد امنیتی با موفقیت در تلاش {attempt} حل شد! ({code})")
                    logger.info("Captcha solved successfully on attempt %d: %s", attempt, code)
                    return True

                # مودال همچنان باز است → کد اشتباه بوده
                if progress_callback and submitted:
                    progress_callback(f"❌ کد {code} پذیرفته نشد. تلاش مجدد...")

            else:
                if progress_callback:
                    progress_callback(f"⚠️ تلاش {attempt}: OCR نتوانست کد معتبری استخراج کند.")

        finally:
            # پاکسازی فایل موقت
            try:
                Path(img_path).unlink(missing_ok=True)
            except Exception:
                pass

        # ۵. اگر به آخرین تلاش نرسیده‌ایم، روی «تغییر کد امنیتی» کلیک کن
        if attempt < max_attempts:
            if progress_callback:
                progress_callback("🔄 کلیک روی «تغییر کد امنیتی» برای دریافت تصویر جدید...")
            await _click_change_captcha(page)
            await page.wait_for_timeout(1500)

    # تمام تلاش‌ها ناموفق
    if progress_callback:
        progress_callback(
            f"❌ پس از {max_attempts} تلاش، کد امنیتی حل نشد. لطفاً به‌صورت دستی کپچا را وارد کنید یا برنامه را متوقف نمایید."
        )
    logger.warning("Captcha solving failed after %d attempts", max_attempts)
    return False
