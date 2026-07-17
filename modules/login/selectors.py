"""
LoginSelectors - تعریف تمام Selectorهای مورد نیاز ماژول Login.

قواعد (طبق مستندات پروژه):
  اولویت: name > aria-label > text > placeholder > selector پایدار
  از selectorهای شکننده (کلاس‌های تصادفی/dynamic) اجتناب شده است.

تمام selectorها بر اساس Element‌های ارسالی کاربر ساخته شده‌اند.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginSelectors:
    """
    مجموعه‌ای از Selectorهای پایدار برای مراحل مختلف Login دیوار.
    هر فیلد یک دستور Playwright-compatible locator string است.
    """

    # ------------------------------------------------------------------
    # 1) دکمه «ورود به حساب کاربری»
    #    Element:
    #      <div class="kt-base-row__start">
    #        <i class="kt-icon kt-icon-exit-to-app"></i>
    #        <p>ورود به حساب کاربری</p>
    #      </div>
    #    انتخاب: text (پایدارترین گزینه در دسترس)
    # ------------------------------------------------------------------
    LOGIN_ENTRY_BUTTON: str = "text=ورود به حساب کاربری"

    # ------------------------------------------------------------------
    # 2) فیلد ورودی شماره موبایل
    #    Element:
    #      <input name="phone" type="tel" autocomplete="tel-national"
    #             placeholder="۰۹۱۲ ۱۲۳ ۴۵۶۷">
    #    انتخاب: name (بالاترین اولویت)
    # ------------------------------------------------------------------
    PHONE_INPUT: str = "input[name='phone']"

    # ------------------------------------------------------------------
    # 3) دکمه «بعدی» (ارسال شماره)
    #    Element:
    #      <button class="kt-button kt-button--primary">
    #        <span>بعدی</span>
    #      </button>
    #    انتخاب: ترکیب text + دکمه primary تا از کلیک روی دکمه‌های دیگر
    #    جلوگیری شود.
    # ------------------------------------------------------------------
    NEXT_BUTTON: str = "button.kt-button--primary:has-text('بعدی')"

    # ------------------------------------------------------------------
    # 4) فیلدهای ۶‌گانه کد تأیید
    #    Element:
    #      <div role="group" aria-label="کد تأیید">
    #        <input aria-label="رقم ۱"> ... <input aria-label="رقم ۶">
    #      </div>
    #    انتخاب: aria-label (اولویت دوم، بسیار پایدار)
    # ------------------------------------------------------------------
    CODE_DIGIT_1: str = "input[aria-label='رقم ۱']"
    CODE_DIGIT_2: str = "input[aria-label='رقم ۲']"
    CODE_DIGIT_3: str = "input[aria-label='رقم ۳']"
    CODE_DIGIT_4: str = "input[aria-label='رقم ۴']"
    CODE_DIGIT_5: str = "input[aria-label='رقم ۵']"
    CODE_DIGIT_6: str = "input[aria-label='رقم ۶']"

    # کانتینر کلی فیلدهای کد (برای بررسی وجود صفحه کد)
    CODE_INPUT_GROUP: str = "div[role='group'][aria-label='کد تأیید']"

    # ------------------------------------------------------------------
    # 5) دکمه «ورود» (ثبت کد تأیید)
    #    Element:
    #      <button class="kt-button kt-button--primary">
    #        <span>ورود</span>
    #      </button>
    # ------------------------------------------------------------------
    SUBMIT_CODE_BUTTON: str = "button.kt-button--primary:has-text('ورود')"

    # ------------------------------------------------------------------
    # 6) پیام‌های خطا (در صورت نیاز در آینده استفاده می‌شود)
    #    فعلاً placeholder - بعد از مشاهده‌ی صفحه خطا تکمیل خواهد شد.
    # ------------------------------------------------------------------
    ERROR_MESSAGE: str = ""  # توسط کاربر در مراحل بعد ارسال می‌شود

    # ------------------------------------------------------------------
    # کمکی
    # ------------------------------------------------------------------
    def code_digit(self, index: int) -> str:
        """
        بازگرداندن selector مربوط به رقم iام (1-indexed).
        """
        if not 1 <= index <= 6:
            raise ValueError("code digit index must be between 1 and 6")
        return (
            self.CODE_DIGIT_1,
            self.CODE_DIGIT_2,
            self.CODE_DIGIT_3,
            self.CODE_DIGIT_4,
            self.CODE_DIGIT_5,
            self.CODE_DIGIT_6,
        )[index - 1]


# یک نمونه پیش‌فرض برای استفاده در کل پروژه
login_selectors = LoginSelectors()
