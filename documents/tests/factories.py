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


_counter = 0


def make_document(**overrides):
    """Create a Document in a given processing state."""
    global _counter
    from documents.models import Document

    _counter += 1
    data = {
        "fingerprint": f"{_counter:064x}",
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "processing_state": Document.ProcessingState.TEXT_READY,
        "text_method": Document.TextMethod.EMBEDDED,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def add_page(document, number: int = 1, text: str = "page text", method: str = "embedded"):
    from documents.models import DocumentPage

    return DocumentPage.objects.create(
        document=document,
        page_number=number,
        text=text,
        method=method,
    )


def make_certificate(document=None, **overrides):
    """Create a Certificate attached to a document."""
    from documents.models import Certificate

    if document is None:
        document = make_document()
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity_literal": "Cambridge English",
        "level_literal": "B2",
        "score_literal": "180",
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


def make_extraction_run(document=None, certificate=None, **overrides):
    from documents.models import ExtractionRun

    if document is None:
        document = make_document()
    data = {
        "document": document,
        "certificate": certificate,
        "status": ExtractionRun.Status.COMPLETED,
        "model": "test-model",
        "prompt_version": "extraction-v9",
        "latency_ms": 123.4,
    }
    data.update(overrides)
    return ExtractionRun.objects.create(**data)


def make_verifier_config(entity=None, **overrides):
    from documents.models import VerifierConfig

    data = {
        "entity": entity,
        "host": "verify.example.org",
        "code_pattern": r"[A-Z0-9-]{8,}",
        "url_template": "https://verify.example.org/check?code={code}",
        "timeout_seconds": 5.0,
    }
    data.update(overrides)
    config = VerifierConfig(**data)
    config.full_clean()
    config.save()
    return config


def make_evaluation_run(**overrides):
    from documents.models import EvaluationRun

    data = {
        "status": EvaluationRun.Status.COMPLETED,
        "set_name": "default",
        "set_version": 1,
        "metrics": {"overall": {"exact_accuracy": 0.9}},
    }
    data.update(overrides)
    return EvaluationRun.objects.create(**data)


def make_evaluation_case(certificate=None, **overrides):
    from documents.models import EvaluationCase

    if certificate is None:
        certificate = make_certificate()
    data = {
        "set_name": "default",
        "set_version": 1,
        "certificate": certificate,
        "source_text": "Ada Lovelace B2 180 Cambridge English",
        "expected": {"student_name": "Ada Lovelace", "score_literal": "180"},
    }
    data.update(overrides)
    return EvaluationCase.objects.create(**data)


def make_field_alias(**overrides):
    from documents.models import FieldLabelAlias

    data = {
        "field": FieldLabelAlias.Field.STUDENT_NAME,
        "alias": "Test Taker Name",
    }
    data.update(overrides)
    return FieldLabelAlias.objects.create(**data)


def make_format_profile(entity, **overrides):
    from catalog.models import FormatProfile

    data = {
        "entity": entity,
        "year": 2024,
        "anchors": [{"text": "cambridge english", "df": 2}],
        "sample_count": 2,
    }
    data.update(overrides)
    return FormatProfile.objects.create(**data)
