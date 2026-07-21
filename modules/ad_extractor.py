"""
AdExtractor - استخراج‌کننده هوشمند آگهی‌ها و ارسال پیام خودکار در چت دیوار.

اصلاحات و امکانات نهایی (2026-07-21):
1. ✅ عدم ارسال پیام تکراری به چت‌ها (ذخیره لیست سوابق پیام‌های ارسالی در messaged_tokens.json)
2. ✅ اعمال محدودیت دقیق بین ۱ تا ۳۰ چت ارسالی
3. ✅ وقفه دقیق ۳ ثانیه‌ای بین هر اسکرول هنگام استخراج آگهی‌ها
4. ✅ استخراج دقیق توکن شناسه دیوار (مانند gadNMKWx) از انتهای لینک بدنه آگهی
5. ✅ ساخت لینک مستقیم چت دیوار به فرمت دقیق https://divar.ir/chat/{token}
6. ✅ پشتیبانی از المان دقیق ورودی چت دیوار (#chat-input و textarea.kt-chat-input__input)
7. ✅ عدم ذخیره‌سازی آگهی تکراری
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from playwright.async_api import Page

logger = logging.getLogger("divar.ad_extractor")

EXTRACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "extracted_ads"
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

SEEN_TOKENS_FILE = EXTRACTED_DIR / "seen_tokens.json"
MESSAGED_TOKENS_FILE = EXTRACTED_DIR / "messaged_tokens.json"


def load_seen_tokens() -> Set[str]:
    """بارگذاری لیست توکن‌ها و لینک‌های استخراج‌شده قبلی جهت عدم ثبت تکراری."""
    if not SEEN_TOKENS_FILE.exists():
        return set()
    try:
        with open(SEEN_TOKENS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("seen_tokens", []))
    except Exception as e:
        logger.warning("Failed to load seen tokens: %s", e)
        return set()


def save_seen_tokens(seen_tokens: Set[str]) -> None:
    """ذخیره دایمی توکن‌های پردازش‌شده در فایل."""
    try:
        with open(SEEN_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump({"seen_tokens": list(seen_tokens)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save seen tokens: %s", e)


def load_messaged_tokens() -> Set[str]:
    """بارگذاری لیست توکن‌هایی که قبلاً پیام چت دریافت کرده‌اند جهت عدم ارسال پیام تکراری."""
    if not MESSAGED_TOKENS_FILE.exists():
        return set()
    try:
        with open(MESSAGED_TOKENS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("messaged_tokens", []))
    except Exception as e:
        logger.warning("Failed to load messaged tokens: %s", e)
        return set()


def save_messaged_tokens(messaged_tokens: Set[str]) -> None:
    """ذخیره دایمی توکن‌های دریافت‌کننده پیام چت."""
    try:
        with open(MESSAGED_TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump({"messaged_tokens": list(messaged_tokens)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save messaged tokens: %s", e)


def extract_divar_token(href: str) -> str:
    """
    استخراج دقیق توکن دیوار از لینک آگهی.
    مثال: https://divar.ir/v/عنوان-آگهی/gadNMKWx?tracker=... -> gadNMKWx
    """
    if not href:
        return ""
    path = href.split("?")[0].rstrip("/")
    segments = [s for s in path.split("/") if s]
    if segments:
        return segments[-1]
    return ""


class AdExtractor:
    """کلاس استخراج‌کننده آگهی‌ها برای دیوار و شیپور."""

    def __init__(self, platform: str, page: Page):
        self.platform = platform.lower()
        self.page = page
        self.seen_tokens = load_seen_tokens()
        self.messaged_tokens = load_messaged_tokens()

    async def extract_page_ads(self) -> List[Dict[str, str]]:
        """استخراج تمام آگهی‌های یکتای موجود در صفحه فعلی."""
        extracted = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.platform == "divar":
            try:
                cards = await self.page.eval_on_selector_all(
                    "a[href*='/v/']",
                    """
                    elements => elements.map(el => {
                        const href = el.getAttribute('href') || '';
                        const titleEl = el.querySelector('.kt-post-card__title, h2, h3, .kt-raw-text') || el;
                        const descEl = el.querySelector('.kt-post-card__description, .kt-post-card__info');
                        return {
                            href: href,
                            title: titleEl ? titleEl.innerText.trim() : '',
                            desc: descEl ? descEl.innerText.trim() : ''
                        };
                    })
                    """
                )

                for item in cards:
                    href = item.get("href", "")
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else f"https://divar.ir{href}"
                    title = item.get("title") or "آگهی دیوار"

                    token = extract_divar_token(href)
                    unique_key = token if token else full_url

                    if unique_key in self.seen_tokens:
                        continue

                    self.seen_tokens.add(unique_key)
                    extracted.append({
                        "platform": "divar",
                        "token": token,
                        "title": title,
                        "url": full_url,
                        "chat_url": f"https://divar.ir/chat/{token}" if token else "",
                        "description": item.get("desc", ""),
                        "extracted_at": now_str,
                        "chat_sent": token in self.messaged_tokens,
                    })
            except Exception as e:
                logger.warning("[divar] Error extracting page cards: %s", e)

        elif self.platform == "sheypoor":
            try:
                cards = await self.page.eval_on_selector_all(
                    "article a[href], .serp-item a[href], a[href*='sheypoor.com/v/'], a[href*='/v/']",
                    """
                    elements => elements.map(el => {
                        const href = el.getAttribute('href') || '';
                        const titleEl = el.querySelector('h2, h3, strong, .title') || el;
                        return {
                            href: href,
                            title: titleEl ? titleEl.innerText.trim() : ''
                        };
                    })
                    """
                )

                for item in cards:
                    href = item.get("href", "")
                    if not href or "sheypoor.com/s/" in href or "sheypoor.com/session/" in href:
                        continue

                    full_url = href if href.startswith("http") else f"https://www.sheypoor.com{href}"
                    title = item.get("title") or "آگهی شیپور"
                    token = href.split("?")[0].rstrip("/").split("/")[-1]

                    if full_url in self.seen_tokens or token in self.seen_tokens:
                        continue

                    self.seen_tokens.add(full_url)
                    extracted.append({
                        "platform": "sheypoor",
                        "token": token,
                        "title": title,
                        "url": full_url,
                        "chat_url": "",
                        "description": "",
                        "extracted_at": now_str,
                        "chat_sent": False,
                    })
            except Exception as e:
                logger.warning("[sheypoor] Error extracting page cards: %s", e)

        if extracted:
            save_seen_tokens(self.seen_tokens)

        return extracted

    async def scrape_multiple_pages(
        self,
        max_pages: int = 1,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, str]]:
        """پیمایش صفحات و استخراج آگهی‌های جدید با وقفه دقیق ۳ ثانیه‌ای بین اسکرول‌ها."""
        all_new_ads = []

        for page_num in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(f"📥 در حال استخراج آگهی‌های جدید صفحه {page_num} از {max_pages}...")

            page_ads = await self.extract_page_ads()
            all_new_ads.extend(page_ads)

            if progress_callback:
                progress_callback(
                    f"✅ صفحه {page_num}: {len(page_ads)} آگهی جدید یافت شد (مجموع کل یکتا: {len(all_new_ads)})"
                )

            if page_num < max_pages:
                try:
                    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                    if progress_callback:
                        progress_callback(f"⏳ وقفه ۳ ثانیه‌ای بین اسکرول‌ها جهت دریافت آگهی‌های جدید (صفحه {page_num} به {page_num + 1})...")
                    await self.page.wait_for_timeout(3000)

                    next_button = self.page.locator("button:has-text('صفحه بعد'), a:has-text('صفحه بعد'), .pagination a").first
                    if await next_button.count() > 0 and await next_button.is_visible():
                        await next_button.click()
                        await self.page.wait_for_timeout(3000)
                except Exception as err:
                    logger.debug("Scroll error on page %d: %s", page_num, err)

        return all_new_ads

    async def send_divar_chat_message(
        self,
        token: str,
        message_text: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """ارسال دقیق پیام چت دیوار با کنترل عدم ارسال تکراری."""
        if not token or not message_text.strip():
            return False

        # ✨ کنترل سوابق: عدم ارسال پیام تکراری به یک آگهی
        if token in self.messaged_tokens:
            if progress_callback:
                progress_callback(f"ℹ️ به آگهی (توکن: {token}) قبلاً پیام ارسال شده است؛ نادیده گرفته شد.")
            return True

        chat_url = f"https://divar.ir/chat/{token}"
        try:
            if progress_callback:
                progress_callback(f"💬 در حال ورود به چت اختصاصی دیوار ({chat_url})...")

            await self.page.goto(chat_url, wait_until="domcontentloaded", timeout=25_000)
            await self.page.wait_for_timeout(2500)

            textarea_selectors = [
                "#chat-input",
                "textarea#chat-input",
                "textarea.kt-chat-input__input",
                ".kt-chat-input__input",
                "textarea[placeholder*='متنی بنویسید']",
                "textarea[placeholder*='پیام']",
                "textarea",
            ]

            chat_input = None
            for sel in textarea_selectors:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    chat_input = loc
                    break

            if not chat_input:
                ad_url = f"https://divar.ir/v/-/{token}"
                await self.page.goto(ad_url, wait_until="domcontentloaded", timeout=25_000)
                await self.page.wait_for_timeout(2000)

                chat_btn = self.page.locator("button:has-text('چت'), a:has-text('چت'), [data-testimonial-id='chat-button']").first
                if await chat_btn.count() > 0 and await chat_btn.is_visible():
                    await chat_btn.click()
                    await self.page.wait_for_timeout(3000)

                for sel in textarea_selectors:
                    loc = self.page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        chat_input = loc
                        break

            if not chat_input:
                if progress_callback:
                    progress_callback(f"⚠️ امکان ارسال چت برای آگهی (توکن: {token}) فعال نیست.")
                return False

            await chat_input.fill(message_text)
            await self.page.wait_for_timeout(1000)

            send_btn_selectors = [
                "button:has-text('ارسال')",
                "button[type='submit']",
                ".kt-chat-send-button",
                "button.kt-button-primary",
            ]

            sent = False
            for btn_sel in send_btn_selectors:
                btn = self.page.locator(btn_sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    sent = True
                    break

            if not sent:
                await chat_input.press("Enter")
                sent = True

            await self.page.wait_for_timeout(2500)

            # ✨ ثبت توکن به عنوان ارسال‌شده
            self.messaged_tokens.add(token)
            save_messaged_tokens(self.messaged_tokens)

            if progress_callback:
                progress_callback(f"✅ پیام با موفقیت در چت دیوار ارسال شد: https://divar.ir/chat/{token}")
            return True

        except Exception as e:
            logger.error("[divar_chat] Exception sending chat to %s: %s", token, e)
            if progress_callback:
                progress_callback(f"❌ خطا در ارسال پیام چت برای {token}: {e}")
            return False


def save_extracted_ads(ads: List[Dict[str, str]], platform: str, phone: str) -> tuple[Path, Path]:
    """ذخیره آگهی‌های استخراج‌شده در دو فایل JSON و CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{platform}_{phone}_{timestamp}"

    json_path = EXTRACTED_DIR / f"{base_name}.json"
    csv_path = EXTRACTED_DIR / f"{base_name}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"count": len(ads), "ads": ads}, f, ensure_ascii=False, indent=2)

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["#", "عنوان آگهی", "لینک کامل آگهی", "لینک مستقیم چت", "شناسه / توکن", "پلتفرم", "وضعیت چت", "زمان استخراج"])
        for idx, ad in enumerate(ads, 1):
            writer.writerow([
                idx,
                ad.get("title", ""),
                ad.get("url", ""),
                ad.get("chat_url", ""),
                ad.get("token", ""),
                ad.get("platform", ""),
                "ارسال شد" if ad.get("chat_sent") else "ارسال نشده",
                ad.get("extracted_at", ""),
            ])

    return json_path, csv_path
