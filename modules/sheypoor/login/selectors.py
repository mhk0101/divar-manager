"""
SheypoorLoginSelectors - تعریف تمام Selectorهای مورد نیاز ماژول Login شیپور.

قواعد (طبق مستندات پروژه):
  اولویت: data-test-id > name > aria-label > text > selector پایدار
  از selectorهای شکننده (کلاس‌های تصادفی/dynamic) اجتناب شده است.

تمام selectorها بر اساس Element‌های ارسالی کاربر ساخته شده‌اند.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginSelectors:
    """
    مجموعه‌ای از Selectorهای پایدار برای مراحل مختلف Login شیپور.
    هر فیلد یک دستور Playwright-compatible locator string است.
    """

    # ------------------------------------------------------------------
    # 1) فیلد ورودی شماره موبایل
    #    Element:
    #      <input name="username" data-test-id="login-field-tel"
    #             inputmode="numeric" fieldtype="numberInput">
    #    انتخاب: data-test-id (پایدارترین) و name (backup)
    # ------------------------------------------------------------------
    PHONE_INPUT: str = "input[data-test-id='login-field-tel']"

    # ------------------------------------------------------------------
    # 2) دکمه «ورود یا ثبت نام در شیپور» (ارسال شماره)
    #    Element:
    #      <button data-test-id="login-submit-tel">
    #        ورود یا ثبت نام در شیپور
    #      </button>
    #    انتخاب: data-test-id
    # ------------------------------------------------------------------
    SUBMIT_PHONE_BUTTON: str = "button[data-test-id='login-submit-tel']"

    # ------------------------------------------------------------------
    # 3) فیلدهای ۴‌گانه کد تأیید (OTP)
    #    Element:
    #      <input data-test-id="otpInput-0" maxlength="1">
    #      <input data-test-id="otpInput-1" maxlength="1">
    #      <input data-test-id="otpInput-2" maxlength="1">
    #      <input data-test-id="otpInput-3" maxlength="1">
    #    انتخاب: data-test-id
    # ------------------------------------------------------------------
    OTP_DIGIT_0: str = "input[data-test-id='otpInput-0']"
    OTP_DIGIT_1: str = "input[data-test-id='otpInput-1']"
    OTP_DIGIT_2: str = "input[data-test-id='otpInput-2']"
    OTP_DIGIT_3: str = "input[data-test-id='otpInput-3']"

    # ------------------------------------------------------------------
    # 4) دکمه «تائید نهایی و ورود به شیپور» (ثبت کد)
    #    Element:
    #      <button data-test-id="verfication-submit">
    #        تائید نهایی و ورود به شیپور
    #      </button>
    #    انتخاب: data-test-id
    # ------------------------------------------------------------------
    SUBMIT_OTP_BUTTON: str = "button[data-test-id='verfication-submit']"

    # ------------------------------------------------------------------
    # 5) دکمه دریافت مجدد کد (در صورت نیاز)
    #    Element:
    #      <button data-test-id="resend-otp">
    #        دریافت مجدد کد چهار رقمی ورود
    #      </button>
    # ------------------------------------------------------------------
    RESEND_OTP_BUTTON: str = "button[data-test-id='resend-otp']"

    # ------------------------------------------------------------------
    # 6) دکمه اصلاح شماره (بازگشت به صفحه قبل)
    #    Element:
    #      <button data-test-id="change-number">
    #        اصلاح شماره تلفن همراه
    #      </button>
    # ------------------------------------------------------------------
    CHANGE_NUMBER_BUTTON: str = "button[data-test-id='change-number']"

    # ------------------------------------------------------------------
    # 7) پیام‌های خطا (placeholder - بعد از مشاهده تکمیل می‌شود)
    # ------------------------------------------------------------------
    ERROR_MESSAGE: str = ""  # توسط کاربر در مراحل بعد ارسال می‌شود

    # ------------------------------------------------------------------
    # کمکی
    # ------------------------------------------------------------------
    def otp_digit(self, index: int) -> str:
        """
        بازگرداندن selector مربوط به رقم iام (0-indexed).
        """
        if not 0 <= index <= 3:
            raise ValueError("OTP digit index must be between 0 and 3")
        return (
            self.OTP_DIGIT_0,
            self.OTP_DIGIT_1,
            self.OTP_DIGIT_2,
            self.OTP_DIGIT_3,
        )[index]


# یک نمونه پیش‌فرض برای استفاده در کل پروژه
login_selectors = LoginSelectors()
