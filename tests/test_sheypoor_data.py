# -*- coding: utf-8 -*-
"""
تست‌های ساختار داده‌های شهرها، محله‌ها و دسته‌بندی‌های شیپور.
"""

from fetch_sheypoor_locations import process_locations
from fetch_sheypoor_categories import process_categories


def test_sheypoor_locations_processing():
    sample_api_response = {
        "success": True,
        "data": {
            "version": 1784455470,
            "list": [
                {
                    "provinceID": 8,
                    "name": "تهران",
                    "slug": "tehran-province",
                    "cities": [
                        {
                            "cityID": 291,
                            "name": "اسلامشهر",
                            "slug": "eslamshahr",
                            "districts": [
                                {"districtID": 9145, "name": "اپرین"},
                                {"districtID": 9146, "name": "احمد آباد مستوفی"}
                            ]
                        }
                    ]
                }
            ]
        }
    }

    result = process_locations(sample_api_response)
    assert result["count"] == 1
    assert result["provinces_count"] == 1
    c = result["cities"][0]
    assert c["id"] == 291
    assert c["name"] == "اسلامشهر"
    assert c["province_name"] == "تهران"
    assert c["districts_count"] == 2
    assert c["districts"][0]["name"] == "اپرین"


def test_sheypoor_categories_root_and_sub_processing():
    sample_api_response = {
        "data": [
            {
                "id": "43626",
                "attributes": {"name": "وسایل نقلیه", "slug": "vehicles"},
                "relationships": {
                    "children": {
                        "data": [{"id": "43627"}]
                    }
                }
            }
        ],
        "included": [
            {
                "id": "43627",
                "attributes": {"name": "خودرو", "slug": "car"},
                "relationships": {
                    "parent": {
                        "data": {"id": "43626"}
                    }
                }
            }
        ]
    }

    result = process_categories(sample_api_response)
    assert result["main_count"] == 1
    assert result["sub_count"] == 1
    assert result["count"] == 2

    mains = [c for c in result["categories"] if c["type"] == "main"]
    subs = [c for c in result["categories"] if c["type"] == "sub"]

    assert len(mains) == 1
    assert mains[0]["name"] == "وسایل نقلیه"

    assert len(subs) == 1
    assert subs[0]["name"] == "خودرو"
    assert subs[0]["category"] == "وسایل نقلیه"
