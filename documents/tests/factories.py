from io import BytesIO

from PIL import Image
from reportlab.pdfgen import canvas


def pdf_bytes(pages: int = 1) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_number in range(1, pages + 1):
        pdf.drawString(72, 720, f"Certificate page {page_number}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    return buffer.getvalue()
