# -*- coding: utf-8 -*-
"""
تست‌های مربوط به استخراج آگهی‌ها، توکن‌های یکتا، فیلتر تکراری‌ها و کنترل چت.
"""

from modules.ad_extractor import (
    extract_divar_token,
    load_messaged_tokens,
    save_extracted_ads,
    save_messaged_tokens,
)


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
    assert data["ads"][0]["token"] == "gadNMKWx"
    assert data["ads"][0]["chat_url"] == "https://divar.ir/chat/gadNMKWx"
