import os
import requests
from bs4 import BeautifulSoup

# آدرس صفحه مورد نظر (مثال: صفحه سیاوش قمیشی)
url = "https://remixbaz.com/playlist/Siavash-Ghomayshi"  # آدرس صفحه را جایگزین کنید

# دریافت محتویات صفحه
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

# پیدا کردن تمام لینک‌های دانلود با کلاس dl-320
download_links = []
for link in soup.find_all('a', class_='dl-320'):
    download_url = link.get('href')
    if download_url and download_url.endswith('.mp3'):
        download_links.append(download_url)

# ایجاد پوشه برای ذخیره فایل‌ها
os.makedirs('mp3_downloads', exist_ok=True)

# دانلود فایل‌ها
for i, mp3_url in enumerate(download_links, 1):
    filename = os.path.join('mp3_downloads', mp3_url.split('/')[-1])
    print(f"Downloading {i}/{len(download_links)}: {filename}")

    try:
        response = requests.get(mp3_url, stream=True)
        response.raise_for_status()

        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded: {filename}")
    except Exception as e:
        print(f"Failed to download {mp3_url}: {e}")

print(f"\nAll done! {len(download_links)} files downloaded.")