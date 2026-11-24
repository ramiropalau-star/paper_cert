import io

import pytest
from django.conf import settings
from django.test import override_settings
from PIL import Image

from documents.services.validation import IntakeValidationError, validate_upload
from documents.tests.factories import pdf_bytes, png_bytes


def heic_bytes() -> bytes:
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="HEIF")
    return buffer.getvalue()


def test_valid_pdf_is_accepted():
    validated = validate_upload(pdf_bytes(2), "certificate.pdf", "application/pdf")

    assert validated.kind == "pdf"
    assert validated.page_count == 2
    assert validated.content_type == "application/pdf"


def test_valid_png_is_accepted():
    validated = validate_upload(png_bytes(), "certificate.png", "image/png")

    assert validated.kind == "image"
    assert validated.page_count == 1


@pytest.mark.parametrize(
    ("filename", "content_type", "code"),
    [
        ("certificate.txt", "text/plain", "unsupported_extension"),
        ("certificate.pdf", "text/plain", "unsupported_mime"),
        ("certificate.pdf", "application/pdf", "content_mismatch"),
    ],
)
def test_invalid_type_or_content_is_rejected(filename, content_type, code):
    data = b"this is not a certificate" if filename.endswith(".pdf") else b"text"

    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(data, filename, content_type)

    assert excinfo.value.code == code


def test_empty_file_is_rejected():
    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(b"", "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "empty_file"


def test_corrupt_pdf_is_rejected():
    data = b"%PDF-1.4\nthis is not a valid pdf"

    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(data, "certificate.pdf", "application/pdf")

    assert excinfo.value.code in {"invalid_pdf", "content_mismatch"}


@override_settings(APP={**settings.APP, "pdf_max_pages": 1})
def test_pdf_page_cap_is_enforced():
    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(pdf_bytes(2), "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "too_many_pages"


@override_settings(APP={**settings.APP, "upload_max_bytes": 100})
def test_file_size_cap_is_enforced():
    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(pdf_bytes(), "certificate.pdf", "application/pdf")

    assert excinfo.value.code == "file_too_large"


def test_corrupt_image_is_rejected():
    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(b"\x89PNG\r\n\x1a\nbroken", "certificate.png", "image/png")

    assert excinfo.value.code in {"invalid_image", "content_mismatch"}


def test_extensionless_pdf_gets_pdf_extension():
    validated = validate_upload(pdf_bytes(1), "certificate", "application/octet-stream")

    assert validated.filename == "certificate.pdf"
    assert validated.content_type == "application/pdf"
    assert validated.kind == "pdf"


def test_unknown_extension_is_replaced_by_detected_type():
    validated = validate_upload(png_bytes(), "certificate.txt", "text/plain")

    assert validated.filename == "certificate.png"
    assert validated.content_type == "image/png"
    assert validated.kind == "image"


def test_heic_image_is_accepted():
    validated = validate_upload(heic_bytes(), "certificate.heic", "image/heic")

    assert validated.kind == "image"
    assert validated.filename == "certificate.heic"


def test_webp_image_is_accepted():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="WEBP")

    validated = validate_upload(buffer.getvalue(), "certificate.webp", "image/webp")

    assert validated.kind == "image"
    assert validated.content_type == "image/webp"


def test_still_rejects_unsupported_content():
    with pytest.raises(IntakeValidationError) as excinfo:
        validate_upload(b"\x00\x01\x02\x03binary", "certificate", "application/octet-stream")

    assert excinfo.value.code == "unsupported_extension"
