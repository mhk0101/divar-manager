# -*- coding: utf-8 -*-
"""
تست‌های مربوط به استخراج آگهی‌ها، توکن‌های یکتا، فیلتر تکراری‌ها، پارسر شماره تلفن و ساخت ساختار پوشه اکسل.
"""

from modules.ad_extractor import (
    extract_divar_token,
    extract_sheypoor_listing_id,
    load_messaged_tokens,
    normalize_phone_number,
    organize_and_save_phone_excel,
    save_extracted_ads,
    save_messaged_tokens,
)


def test_normalize_phone_number():
    assert normalize_phone_number("tel:09039971530") == "09039971530"
    assert normalize_phone_number("۰۹۰۳۹۹۷۱۵۳۰") == "09039971530"
    assert normalize_phone_number("۱۲۸ گیگابایت") is None
    assert normalize_phone_number("قیمت ۵۰,۰۰۰ تومان") is None


def test_extract_sheypoor_listing_id():
    url = "https://www.sheypoor.com/v/%D9%81%D8%B1%D9%88%D8%B4-3150-%D9%85%D8%AA%D8%B1-%D8%B2%D9%85-%D9%86-%D8%A8%D8%A7-%D9%82-%D9%85%D8%AA-%D8%A7%D8%B3%D8%AA%D8%AB%D9%86%D8%A7-465146913.html"
    assert extract_sheypoor_listing_id(url) == "465146913"


def test_organize_and_save_phone_excel_exact_folder_format(tmp_path):
    file_path = organize_and_save_phone_excel(
        phone_number="09177741849",
        title="فروش هندزفری",
        location_name="بوشهر",
        category_name="کالای دیجیتال",
        platform="divar",
        url="https://divar.ir/v/123",
    )

    assert file_path.exists()
    folder_name = file_path.parent.name
    assert folder_name == "0917_ بوشهر_ دسته کالای دیجیتال"


def test_extract_divar_token():
    url1 = "https://divar.ir/v/%D9%85%D9%88%D8%A8%D8%A7%DB%8C%D9%84-%D9%87%D8%A7%D9%86%D8%B1-x5-b-plus/gadNMKWx?tracker_session_id=6f2f7aca_gadNMKWx_N"
    url2 = "https://divar.ir/v/خانه-باغ-یاسوج/wX998877"
    url3 = "/v/some-slug/abc123XYZ?query=1"

    assert extract_divar_token(url1) == "gadNMKWx"
    assert extract_divar_token(url2) == "wX998877"
    assert extract_divar_token(url3) == "abc123XYZ"


def test_messaged_tokens_saving(tmp_path):
    tokens = {"gadNMKWx", "wX998877"}
    save_messaged_tokens(tokens)
    loaded = load_messaged_tokens()
    assert "gadNMKWx" in loaded
    assert "wX998877" in loaded


def test_save_extracted_ads(tmp_path):
    sample_ads = [
        {
            "platform": "divar",
            "token": "gadNMKWx",
            "title": "موبایل هانر",
            "phone_number": "09039971530",
            "url": "https://divar.ir/v/mobile/gadNMKWx",
            "chat_url": "https://divar.ir/chat/gadNMKWx",
            "description": "تهران",
            "extracted_at": "2026-07-21 12:00:00",
            "chat_sent": True,
        },
    ]

    json_path, csv_path = save_extracted_ads(sample_ads, "divar", "09023808876")

    assert json_path.exists()
    assert csv_path.exists()

    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["count"] == 1
    assert data["ads"][0]["phone_number"] == "09039971530"
    assert data["ads"][0]["token"] == "gadNMKWx"
    assert data["ads"][0]["chat_url"] == "https://divar.ir/chat/gadNMKWx"
