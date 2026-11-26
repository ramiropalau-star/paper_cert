from __future__ import annotations

import io
import subprocess
import time
from pathlib import Path

import app as service
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

client = TestClient(service.app)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def _font(size: int = 64) -> ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def image_bytes(text: str = "LANGUAGE CERTIFICATE B2") -> bytes:
    image = Image.new("RGB", (1400, 500), "white")
    drawing = ImageDraw.Draw(image)
    drawing.text((60, 180), text, fill="black", font=_font())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def text_pdf_bytes(page_count: int = 1) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    for page in range(page_count):
        pdf.setFont("Helvetica-Bold", 28)
        pdf.drawString(50, 700, "LANGUAGE CERTIFICATE CEFR B2 ENGLISH")
        pdf.drawString(50, 660, f"PAGE {page + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def scanned_pdf_bytes(text: str = "LANGUAGE CERTIFICATE B2", pages: int = 1) -> bytes:
    image = Image.open(io.BytesIO(image_bytes(text)))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    for _ in range(pages):
        pdf.drawImage(ImageReader(image), 40, 300, width=520, height=186)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def mixed_pdf_bytes() -> bytes:
    image = Image.open(io.BytesIO(image_bytes("SCANNED PAGE TEXT")))
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792))
    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawString(50, 700, "LANGUAGE CERTIFICATE CEFR B2 ENGLISH")
    pdf.drawString(50, 660, "EMBEDDED PAGE ONE")
    pdf.showPage()
    pdf.drawImage(ImageReader(image), 40, 300, width=520, height=186)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def heic_bytes(text: str = "LANGUAGE CERTIFICATE B2") -> bytes:
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    image = Image.new("RGB", (1400, 500), "white")
    drawing = ImageDraw.Draw(image)
    drawing.text((60, 180), text, fill="black", font=_font())
    buffer = io.BytesIO()
    image.save(buffer, format="HEIF")
    return buffer.getvalue()


def _post_image(data: bytes, name: str = "certificate.png") -> object:
    return client.post(
        "/v1/ocr",
        files={"file": (name, data, "image/png")},
        data={"languages": "eng,spa"},
    )


def test_health_reports_engines() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["contract_version"] == "v1"
    assert body["engine"]["tesseract"] != "unavailable"
    assert "ocrmypdf" not in body["engine"]


def test_text_pdf_uses_embedded_text_without_ocr() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("text.pdf", text_pdf_bytes(2), "application/pdf")},
        data={"languages": "eng,spa"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2
    assert body["quality"] == "ok"
    assert [page["page_number"] for page in body["pages"]] == [1, 2]
    assert all(page["method"] == "embedded" for page in body["pages"])
    assert "LANGUAGE CERTIFICATE" in body["pages"][0]["text"]
    assert body["mean_confidence"] == 1.0


def test_scanned_pdf_runs_ocr_and_returns_confidence() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("scan.pdf", scanned_pdf_bytes(), "application/pdf")},
        data={"languages": "eng,spa"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 1
    page = body["pages"][0]
    assert page["method"] == "ocr"
    assert 0 < page["confidence"] <= 1.0
    assert "CERTIFICATE" in page["text"].upper()


def test_png_image_runs_ocr() -> None:
    response = _post_image(image_bytes())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 1
    assert body["pages"][0]["method"] == "ocr"
    assert "CERTIFICATE" in body["pages"][0]["text"].upper()


def test_heic_image_runs_ocr() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("certificate.heic", heic_bytes(), "image/heic")},
        data={"languages": "eng,spa"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 1
    assert body["pages"][0]["method"] == "ocr"
    assert "CERTIFICATE" in body["pages"][0]["text"].upper()


def test_multipage_scanned_pdf_keeps_page_order() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("scan.pdf", scanned_pdf_bytes(pages=2), "application/pdf")},
        data={"languages": "eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2
    assert [page["page_number"] for page in body["pages"]] == [1, 2]
    assert all(page["text"] for page in body["pages"])


def test_page_limit_is_enforced() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("text.pdf", text_pdf_bytes(2), "application/pdf")},
        data={"page_limit": "1", "languages": "eng"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_many_pages"


def test_unreadable_pdf_is_rejected() -> None:
    response = client.post(
        "/v1/ocr",
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        data={"languages": "eng"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable"


def test_blank_image_reports_no_text() -> None:
    image = Image.new("RGB", (600, 300), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    response = _post_image(buffer.getvalue())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_text"


def test_low_confidence_is_signalled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service.settings, "low_confidence_threshold", 1.01)
    response = _post_image(image_bytes())
    assert response.status_code == 200, response.text
    assert response.json()["quality"] == "low"


def test_request_timeout_is_signalled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "process_document_bytes", lambda *args, **kwargs: time.sleep(0.5))
    monkeypatch.setattr(service.settings, "request_timeout_seconds", 0.05)
    response = _post_image(image_bytes())
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "request_timeout"
    assert response.json()["error"]["retryable"] is True


def test_single_recognition_pass_per_scanned_page(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def counting_tesseract(
        path: Path, languages: tuple[str, ...], timeout: float, page_number: int | None = None
    ) -> tuple[str, float]:
        calls.append(page_number or 0)
        return "LANGUAGE CERTIFICATE B2", 0.9

    monkeypatch.setattr(service, "run_tesseract_tsv", counting_tesseract)
    response = client.post(
        "/v1/ocr",
        files={"file": ("scan.pdf", scanned_pdf_bytes(pages=2), "application/pdf")},
        data={"languages": "eng"},
    )
    assert response.status_code == 200, response.text
    assert calls == [1, 2]
    assert not hasattr(service, "ocrmypdf")


def test_mixed_pdf_keeps_embedded_and_ocr_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "run_tesseract_tsv", lambda *a, **k: ("SCANNED PAGE TEXT", 0.8))
    response = client.post(
        "/v1/ocr",
        files={"file": ("mixed.pdf", mixed_pdf_bytes(), "application/pdf")},
        data={"languages": "eng"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2
    assert body["pages"][0]["method"] == "embedded"
    assert body["pages"][0]["confidence"] == 1.0
    assert body["pages"][1]["method"] == "ocr"
    assert body["pages"][1]["confidence"] == 0.8


def test_page_timeout_identifies_page(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="tesseract", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(service.subprocess, "run", timeout_run)
    with pytest.raises(service.OcrFailure) as excinfo:
        service.run_tesseract_tsv(Path("page.png"), ("eng",), 5.0, page_number=3)
    assert excinfo.value.code == "page_timeout"
    assert excinfo.value.status_code == 504
    assert excinfo.value.retryable is True
    assert "page 3" in excinfo.value.message


def test_request_timeout_between_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_tesseract(*args, **kwargs) -> tuple[str, float]:
        time.sleep(0.3)
        return "LANGUAGE CERTIFICATE B2", 0.9

    monkeypatch.setattr(service, "run_tesseract_tsv", slow_tesseract)
    monkeypatch.setattr(service.settings, "request_timeout_seconds", 0.55)
    monkeypatch.setattr(service.settings, "page_timeout_seconds", 60.0)
    with pytest.raises(service.OcrFailure) as excinfo:
        service.process_pdf(scanned_pdf_bytes(pages=3), ("eng",), 100)
    assert excinfo.value.code == "request_timeout"
    assert excinfo.value.retryable is True


def test_temp_files_removed_on_success_and_failure() -> None:
    import tempfile

    temp_root = Path(tempfile.gettempdir())
    before = set(temp_root.glob("ocr-*"))
    client.post(
        "/v1/ocr",
        files={"file": ("scan.pdf", scanned_pdf_bytes(), "application/pdf")},
        data={"languages": "eng"},
    )
    client.post(
        "/v1/ocr",
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        data={"languages": "eng"},
    )
    after = set(temp_root.glob("ocr-*"))
    assert after == before


def test_configured_languages_are_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, tuple[str, ...]] = {}

    def fake_tesseract(
        path: Path,
        languages: tuple[str, ...],
        timeout: float,
        page_number: int | None = None,
    ) -> tuple[str, float]:
        captured["languages"] = languages
        return "LANGUAGE CERTIFICATE B2", 0.9

    monkeypatch.setattr(service, "run_tesseract_tsv", fake_tesseract)
    response = client.post(
        "/v1/ocr",
        files={"file": ("certificate.png", image_bytes(), "image/png")},
        data={"languages": "eng"},
    )
    assert response.status_code == 200, response.text
    assert captured["languages"] == ("eng",)
