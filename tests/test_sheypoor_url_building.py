# -*- coding: utf-8 -*-
"""
تست ساخت URL های خروجی شیپور طبق الگوهای مختلف (تک‌شهری، چندشهری، دسته‌بندی‌ها).
"""

from typing import List, Optional


def build_sheypoor_url(cities_data: List[dict], category_slug: Optional[str]) -> str:
    cat_part = f"/{category_slug}" if category_slug else ""

    if not cities_data:
        return f"https://www.sheypoor.com/s/iran{cat_part}"

    if len(cities_data) == 1:
        city_slug = cities_data[0].get("slug") or "iran"
        return f"https://www.sheypoor.com/s/{city_slug}{cat_part}"

    query_params = "&".join(
        f"cities[{i}]={c.get('id')}"
        for i, c in enumerate(cities_data)
        if c.get("id") is not None
    )
    return f"https://www.sheypoor.com/s/iran{cat_part}?{query_params}"


def test_single_city_no_cat():
    c = [{"id": 4, "name": "کرج", "slug": "karaj"}]
    assert build_sheypoor_url(c, None) == "https://www.sheypoor.com/s/karaj"


def test_single_city_with_cat():
    c = [{"id": 1, "name": "تهران", "slug": "tehran"}]
    assert build_sheypoor_url(c, "vehicles") == "https://www.sheypoor.com/s/tehran/vehicles"
    assert build_sheypoor_url(c, "car-auction") == "https://www.sheypoor.com/s/tehran/car-auction"
    assert build_sheypoor_url(c, "house-apartment-for-rent") == "https://www.sheypoor.com/s/tehran/house-apartment-for-rent"


def test_multiple_cities_no_cat():
    cities = [
        {"id": 291, "name": "شهر ۱", "slug": "c1"},
        {"id": 292, "name": "شهر ۲", "slug": "c2"},
        {"id": 297, "name": "شهر ۳", "slug": "c3"},
    ]
    expected = "https://www.sheypoor.com/s/iran?cities[0]=291&cities[1]=292&cities[2]=297"
    assert build_sheypoor_url(cities, None) == expected


def test_multiple_cities_with_cat():
    cities = [
        {"id": 177, "name": "شهر A", "slug": "a"},
        {"id": 127, "name": "شهر B", "slug": "b"},
        {"id": 131, "name": "شهر C", "slug": "c"},
    ]
    expected = "https://www.sheypoor.com/s/iran/real-estate?cities[0]=177&cities[1]=127&cities[2]=131"
    assert build_sheypoor_url(cities, "real-estate") == expected
