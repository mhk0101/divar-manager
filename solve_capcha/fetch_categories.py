# -*- coding: utf-8 -*-

import sys
import subprocess
import importlib.util
import os
import time
import glob
import re
import cv2
import numpy as np

# ============================================================
# بخش ۱: خودکار نصب کتابخونه‌های مورد نیاز (فقط EasyOCR)
# ============================================================

REQUIRED_PACKAGES = [
    "opencv-python-headless",
    "easyocr",
    "pillow",
    "numpy"
]

def install_package(pkg):
    print(f"[+] نصب {pkg} ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])

def check_and_install():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        import_name = pkg
        if pkg == "opencv-python-headless":
            import_name = "cv2"
        if importlib.util.find_spec(import_name) is None:
            missing.append(pkg)
    if missing:
        print(f"[!] {len(missing)} پکیج گم شده. شروع نصب...")
        for pkg in missing:
            install_package(pkg)
        print("[+] همه نصب شدن.")
    else:
        print("[+] همه پکیج‌ها موجودند.")

check_and_install()

# ============================================================
# بخش ۲: ایمپورت‌ها
# ============================================================

import easyocr
from PIL import Image

print("[+] همه کتابخونه‌ها بار شدن.\n")

# ============================================================
# بخش ۳: توابع پیش‌پردازش (برای روش Advanced)
# ============================================================

def preprocess_image(image_path):
    """پیش‌پردازش قوی برای افزایش دقت EasyOCR"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("تصویر خوانده نشد.")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # حذف نویز
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    
    # افزایش کنتراست
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # آستانه‌سازی تطبیقی
    thresh = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    # عملیات مورفولوژی (اتصال حروف شکسته)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    return morph

# ============================================================
# بخش ۴: دو روش حل با EasyOCR
# ============================================================

def solve_easyocr_raw(image_path):
    """روش Raw: تصویر اصلی، بدون پیش‌پردازش"""
    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result = reader.readtext(
            gray,
            allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            paragraph=False
        )
        if result:
            text = ''.join([r[1] for r in result])
            return re.sub(r'[^A-Za-z0-9]', '', text.strip())
        return ""
    except Exception as e:
        return f"خطا: {e}"

def solve_easyocr_advanced(image_path):
    """روش Advanced: با پیش‌پردازش قوی و threshold پایین"""
    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        processed = preprocess_image(image_path)
        result = reader.readtext(
            processed,
            allowlist='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            paragraph=False,
            text_threshold=0.1,   # تشخیص حروف با اطمینان کمتر
            width_ths=0.7,
            height_ths=0.7
        )
        if result:
            text = ''.join([r[1] for r in result])
            return re.sub(r'[^A-Za-z0-9]', '', text.strip())
        return ""
    except Exception as e:
        return f"خطا: {e}"

# ============================================================
# بخش ۵: پردازش همه تصاویر موجود در پوشه
# ============================================================

def solve_all_images():
    # پیدا کردن فایل‌های تصویری
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']
    image_files = []
    for ext in extensions:
        image_files.extend(glob.glob(ext, recursive=False))
        image_files.extend(glob.glob(ext.upper(), recursive=False))
    
    # حذف فایل‌های تکراری و مرتب‌سازی
    image_files = sorted(list(set(image_files)))
    image_files = [f for f in image_files if not f.endswith('.py') and not f.endswith('.txt')]
    
    if not image_files:
        print("[!] هیچ فایل تصویری در پوشه جاری یافت نشد.")
        return
    
    print(f"\n[+] {len(image_files)} فایل تصویری پیدا شد:")
    for f in image_files:
        print(f"   - {f}")
    print()
    
    results = []
    for idx, img_path in enumerate(image_files, 1):
        print(f"{'='*60}")
        print(f"📸 تصویر {idx}/{len(image_files)}: {img_path}")
        print('='*60)
        
        # روش Raw
        print("\n  🔍 روش EasyOCR (Raw)")
        start = time.time()
        text_raw = solve_easyocr_raw(img_path)
        elapsed = time.time() - start
        print(f"     زمان: {elapsed:.2f} ثانیه")
        if text_raw and len(text_raw) >= 3:
            print(f"     ✅ جواب: {text_raw}")
        else:
            print(f"     ❌ {text_raw if text_raw else 'جواب نامعتبر'}")
        
        # روش Advanced
        print("\n  🔍 روش EasyOCR (Advanced)")
        start = time.time()
        text_adv = solve_easyocr_advanced(img_path)
        elapsed = time.time() - start
        print(f"     زمان: {elapsed:.2f} ثانیه")
        if text_adv and len(text_adv) >= 3:
            print(f"     ✅ جواب: {text_adv}")
        else:
            print(f"     ❌ {text_adv if text_adv else 'جواب نامعتبر'}")
        
        # مقایسه دو روش
        print("\n  📊 مقایسه:")
        if text_raw and text_adv:
            if text_raw == text_adv:
                print(f"     ✅ هر دو روش یکسان: {text_raw}")
                final = text_raw
            else:
                print(f"     ⚠️ متفاوت: Raw={text_raw}, Advanced={text_adv}")
                final = text_raw  # انتخاب Raw به‌عنوان پیش‌فرض (چون سریع‌تر است)
        elif text_raw:
            print(f"     ✅ فقط Raw جواب داد: {text_raw}")
            final = text_raw
        elif text_adv:
            print(f"     ✅ فقط Advanced جواب داد: {text_adv}")
            final = text_adv
        else:
            print("     ❌ هیچ روشی جواب نداد.")
            final = "(ناموفق)"
        
        results.append((img_path, text_raw, text_adv, final))
        print("\n" + "-"*60)
        time.sleep(1)  # فاصله بین تصاویر
    
    # ذخیره نتایج
    output_file = "easyocr_results.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("="*60 + "\n")
        f.write("نتایج حل کپچا با EasyOCR (دو روش)\n")
        f.write("="*60 + "\n\n")
        for img, raw, adv, final in results:
            f.write(f"📸 {img}:\n")
            f.write(f"   Raw:      {raw}\n")
            f.write(f"   Advanced: {adv}\n")
            f.write(f"   نهایی:    {final}\n\n")
    
    # نمایش خلاصه
    print("\n" + "="*60)
    print("📊 خلاصه نتایج:")
    for img, raw, adv, final in results:
        status = "✅" if final != "(ناموفق)" else "❌"
        print(f"   {status} {img} → {final}")
    print(f"\n[+] نتایج کامل در فایل {output_file} ذخیره شد.")

# ============================================================
# بخش ۶: اجرا
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("     🔥 حل‌کننده کپچا با EasyOCR (دو روش)")
    print("="*60 + "\n")
    solve_all_images()