"""Unit tests for the shared pipeline helpers (reason merge, file type)."""

import pytest

from documents.services.classification import CLASSIFICATION_REASON_CODES
from documents.services.extraction import EXTRACTION_REASON_CODES
from documents.services.filetype import effective_name, sniffed_type
from documents.services.review_reasons import merge_review_reasons
from documents.services.text import TEXT_REASON_CODES
from documents.services.validation import EXTENSION_BY_TYPE
from documents.tests.factories import pdf_bytes, png_bytes

# --- merge_review_reasons ---


def test_merge_drops_owned_codes_and_appends_fresh():
    existing = ["unknown_language", "low_confidence", "custom_reason"]
    fresh = ["missing_essential_fields", "low_confidence"]

    merged = merge_review_reasons(existing, fresh, CLASSIFICATION_REASON_CODES)

    assert merged == ["custom_reason", "missing_essential_fields", "low_confidence"]


def test_merge_preserves_order_and_dedupes():
    existing = ["b_reason", "a_reason", "b_reason"]
    fresh = ["c_reason", "a_reason"]

    merged = merge_review_reasons(existing, fresh, set())

    assert merged == ["b_reason", "a_reason", "c_reason"]


def test_merge_handles_empty_inputs():
    assert merge_review_reasons(None, [], {"x"}) == []
    assert merge_review_reasons([], ["a", "a"], set()) == ["a"]


@pytest.mark.parametrize(
    "owned_codes",
    [TEXT_REASON_CODES, EXTRACTION_REASON_CODES, CLASSIFICATION_REASON_CODES],
)
def test_merge_stage_ownership(owned_codes):
    owned = sorted(owned_codes)[0]
    foreign = "definitely_not_owned_reason"
    existing = [foreign, owned]
    fresh = [owned]

    merged = merge_review_reasons(existing, fresh, owned_codes)

    assert merged == [foreign, owned]
    assert foreign in merged


# --- sniffed_type ---


def test_sniffed_type_detects_pdf():
    assert sniffed_type(pdf_bytes()) == "application/pdf"


def test_sniffed_type_detects_png():
    assert sniffed_type(png_bytes()) == "image/png"


def test_sniffed_type_allowlist_filters():
    text_types = set(EXTENSION_BY_TYPE) | {"image/x-ms-bmp"}
    assert sniffed_type(png_bytes(), allowed_mimes=text_types) == "image/png"
    assert sniffed_type(pdf_bytes(), allowed_mimes={"image/png"}) == ""


def test_sniffed_type_undetectable_data():
    assert isinstance(sniffed_type(b""), str)
    assert sniffed_type(b"\x00" * 64, allowed_mimes={"image/png"}) == ""


# --- effective_name ---


def test_effective_name_swaps_extension():
    assert effective_name("certificado.bin", "application/pdf", EXTENSION_BY_TYPE) == (
        "certificado.pdf"
    )
    assert effective_name("photo", "image/png", EXTENSION_BY_TYPE) == "photo.png"


def test_effective_name_unknown_type_unchanged():
    assert effective_name("archive.zip", "application/zip", EXTENSION_BY_TYPE) == "archive.zip"
