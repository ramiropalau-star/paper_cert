"""Deterministic certificate fixture generator.

Generates small sample files used by the end-to-end tests and the compose
smoke test. Running the module writes the files to ``tests/fixtures/files/``:

    .venv/bin/python -m tests.fixturegen
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from reportlab import rl_config
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

rl_config.invariant = 1  # deterministic PDF output (no timestamps/IDs)

OUTPUT_DIR = Path(__file__).resolve().parent / "fixtures" / "files"

CERTIFICATE_LINES = [
    "CERTIFICATE OF PROFICIENCY IN ENGLISH",
    "This is to certify that",
    "Student Name: Ada Lovelace",
    "Language: English",
    "Certifying Entity: Cambridge English",
    "Exam: B2 First",
    "Level: B2",
    "Score: 180",
    "Date of Issue: 12 May 2024",
    "Certificate Code: CERT-2024-001",
]

INCOMPLETE_LINES = [
    "LANGUAGE CERTIFICATE",
    "Student Name: Grace Hopper",
    "Language: English",
    "Certifying Entity: IELTS",
    "Date of Issue: 2024",
]

AMBIGUOUS_DATE_LINES = [
    "LANGUAGE CERTIFICATE",
    "Student Name: Alan Turing",
    "Language: English",
    "Certifying Entity: Cambridge English",
    "Exam: C1 Advanced",
    "Level: C1",
    "Score: 190",
    "Date of Issue: 05/06/2024",
]

UNKNOWN_ENTITY_LINES = [
    "LANGUAGE CERTIFICATE",
    "Student Name: Katherine Johnson",
    "Language: English",
    "Certifying Entity: Acme Language Board",
    "Exam: Proficiency Test",
    "Level: C2",
    "Score: 92",
    "Date of Issue: 2024-03-01",
]

NON_CERTIFICATE_LINES = [
    "INVOICE No. 2024-77",
    "Bill to: Language School",
    "Description: Course fees",
    "Total: 150.00 EUR",
    "Due date: 2024-06-30",
]


def _text_pdf(lines_per_page: list[list[str]]) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for lines in lines_per_page:
        y = 780
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _image_with_text(lines: list[str], size: tuple[int, int] = (600, 800)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    y = 40
    for line in lines:
        draw.text((30, y), line, fill="black")
        y += 28
    return image


def _image_bytes(image: Image.Image, fmt: str) -> bytes:
    buffer = BytesIO()
    if fmt == "TIFF":
        image.save(buffer, format="TIFF", compression="tiff_lzw")
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


def text_pdf_bytes() -> bytes:
    return _text_pdf([CERTIFICATE_LINES])


def multipage_pdf_bytes() -> bytes:
    return _text_pdf(
        [
            CERTIFICATE_LINES[:5],
            CERTIFICATE_LINES[5:],
            ["This certificate is issued by Cambridge English."],
        ]
    )


def incomplete_pdf_bytes() -> bytes:
    return _text_pdf([INCOMPLETE_LINES])


def ambiguous_date_pdf_bytes() -> bytes:
    return _text_pdf([AMBIGUOUS_DATE_LINES])


def unknown_entity_pdf_bytes() -> bytes:
    return _text_pdf([UNKNOWN_ENTITY_LINES])


def non_certificate_pdf_bytes() -> bytes:
    return _text_pdf([NON_CERTIFICATE_LINES])


def scanned_pdf_bytes() -> bytes:
    """PDF whose only page is a raster image: no embedded text layer."""
    image = _image_with_text(CERTIFICATE_LINES)
    buffer = BytesIO()
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    pdf = canvas.Canvas(buffer)
    pdf.drawImage(ImageReader(image_buffer), 0, 0, width=595, height=842, preserveAspectRatio=True)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def jpg_bytes() -> bytes:
    return _image_bytes(_image_with_text(CERTIFICATE_LINES, (800, 1100)), "JPEG")


def png_bytes() -> bytes:
    return _image_bytes(_image_with_text(CERTIFICATE_LINES, (800, 1100)), "PNG")


def tiff_bytes() -> bytes:
    return _image_bytes(_image_with_text(CERTIFICATE_LINES, (500, 650)), "TIFF")


def heic_bytes() -> bytes:
    return _image_bytes(_image_with_text(CERTIFICATE_LINES, (500, 650)), "HEIF")


FIXTURES = {
    "text-certificate.pdf": (text_pdf_bytes, "application/pdf"),
    "scanned-certificate.pdf": (scanned_pdf_bytes, "application/pdf"),
    "multipage-certificate.pdf": (multipage_pdf_bytes, "application/pdf"),
    "incomplete-certificate.pdf": (incomplete_pdf_bytes, "application/pdf"),
    "ambiguous-date.pdf": (ambiguous_date_pdf_bytes, "application/pdf"),
    "unknown-entity.pdf": (unknown_entity_pdf_bytes, "application/pdf"),
    "non-certificate.pdf": (non_certificate_pdf_bytes, "application/pdf"),
    "certificate.jpg": (jpg_bytes, "image/jpeg"),
    "certificate.png": (png_bytes, "image/png"),
    "certificate.tiff": (tiff_bytes, "image/tiff"),
    "certificate.heic": (heic_bytes, "image/heic"),
}


def write_fixtures(directory: Path = OUTPUT_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (builder, _content_type) in FIXTURES.items():
        path = directory / name
        path.write_bytes(builder())
        written.append(path)
    return written


def main() -> None:
    for path in write_fixtures():
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
