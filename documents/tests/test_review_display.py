import pytest

from documents.review_display import (
    UNKNOWN_REASON,
    confidence_display,
    review_reason_items,
)


def test_known_reason_maps_to_label_and_explanation():
    items = review_reason_items(["unknown_language"])

    assert len(items) == 1
    item = items[0]
    assert item["known"] is True
    assert item["label"] == "Idioma no identificado"
    assert item["explanation"]
    assert item["code"] == "unknown_language"


def test_unknown_reason_falls_back_to_generic_message():
    items = review_reason_items(["brand_new_code_from_future"])

    assert items[0]["known"] is False
    assert items[0]["label"] == UNKNOWN_REASON[0]
    assert items[0]["explanation"] == UNKNOWN_REASON[1]
    assert items[0]["code"] == "brand_new_code_from_future"


def test_duplicate_reasons_are_deduplicated():
    items = review_reason_items(["low_confidence", "low_confidence", "ambiguous_date"])

    assert [item["code"] for item in items] == ["low_confidence", "ambiguous_date"]


def test_empty_and_none_reasons_return_empty_list():
    assert review_reason_items([]) == []
    assert review_reason_items(None) == []


@pytest.mark.parametrize(
    ("value", "percent", "band"),
    [
        (0.9, 90, "high"),
        (0.85, 85, "high"),
        (0.7, 70, "medium"),
        (0.6, 60, "medium"),
        (0.4, 40, "low"),
        (0.0, 0, "low"),
    ],
)
def test_confidence_bands(value, percent, band):
    result = confidence_display(value)

    assert result["percent"] == percent
    assert result["band"] == band
    assert result["raw"] == f"{value:.2f}"


def test_confidence_none_and_invalid():
    assert confidence_display(None) is None
    assert confidence_display("not-a-number") is None


def test_confidence_percent_scale_accepted():
    result = confidence_display(87)

    assert result["percent"] == 87
    assert result["band"] == "high"
