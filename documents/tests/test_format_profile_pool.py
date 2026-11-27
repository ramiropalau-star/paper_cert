"""Tests for entity pool profiles, layout anchors, metadata filtering and
the anonymized profile preview."""

from datetime import date

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.urls import reverse

from catalog.models import Entity, FormatProfile, Language
from documents.models import Certificate, Document, DocumentPage
from documents.services.format_profile import learn_format_profile, score_document_format
from documents.services.profile_preview import render_profile_preview

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


BOILERPLATE = (
    "cambridge assessment english\nthis is to certify that\ncertificate of proficiency in english"
)


def make_document(**overrides) -> Document:
    data = {
        "fingerprint": "a" * 64,
        "original_filename": "certificate.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": "42",
        "processing_state": Document.ProcessingState.PENDING_REVIEW,
    }
    data.update(overrides)
    return Document.objects.create(**data)


def make_certificate(document: Document, **overrides) -> Certificate:
    data = {
        "document": document,
        "student_name": "Ada Lovelace",
        "language_literal": "English",
        "entity_literal": "Cambridge English",
        "exam_literal": "B2 First",
        "level_literal": "B2",
        "score_literal": "180",
        "issue_date": date(2024, 5, 12),
        "is_language_certificate": True,
        "confidence": 0.9,
        "review_status": Certificate.ReviewStatus.PENDING,
    }
    data.update(overrides)
    cert = Certificate.objects.create(**data)
    cert.language = Language.objects.get(code="eng")
    cert.entity = Entity.objects.get(name="Cambridge English")
    cert.save()
    return cert


def add_page(document: Document, text: str, number: int = 1, layout: dict | None = None) -> None:
    DocumentPage.objects.create(
        document=document,
        page_number=number,
        text=text,
        method=DocumentPage.Method.EMBEDDED,
        layout=layout,
    )


def approved_cert(document: Document, year: int = 2024, **overrides) -> Certificate:
    cert = make_certificate(
        document,
        issue_date=date(year, 5, 12),
        review_status=Certificate.ReviewStatus.APPROVED,
        **overrides,
    )
    document.processing_state = Document.ProcessingState.APPROVED
    document.save(update_fields=["processing_state"])
    return cert


IMAGE_LAYOUT = {
    "page": {"w": 595.0, "h": 842.0},
    "lines": [{"text": "Cambridge Assessment", "bbox": [100, 700, 300, 720]}],
    "images": [{"bbox": [400, 60, 560, 160], "width": 160, "height": 100}],
}


def test_pool_profile_spans_years_and_filters_single_year_anchors():
    docs = []
    for i, year in enumerate([2020, 2020, 2024, 2024]):
        doc = make_document(fingerprint=f"{i:064x}")
        marker = "old layout marker phrase" if year == 2020 else "new layout marker phrase"
        add_page(doc, f"{BOILERPLATE}\n{marker}")
        docs.append((doc, year))
    for doc, year in docs:
        learn_format_profile(approved_cert(doc, year=year))

    pool = FormatProfile.objects.get(
        entity__name="Cambridge English", year__isnull=True, exam__isnull=True
    )
    assert pool.sample_count == 4
    texts = {a["text"] for a in pool.anchors if a.get("text")}
    assert "this is to certify that" in texts
    # Single-year boilerplate must not leak into the multi-year pool.
    assert "old layout marker phrase" not in texts
    assert "new layout marker phrase" not in texts

    # Per-year profiles still exist for drift detection.
    assert FormatProfile.objects.filter(
        entity__name="Cambridge English", year=2020, exam__isnull=True
    ).exists()


def test_metadata_lines_never_become_anchors():
    docs = []
    for i in range(2):
        doc = make_document(fingerprint=f"{i + 20:064x}")
        add_page(doc, f"{BOILERPLATE}\nlanguage: english\nissuer_id: cambridge")
        docs.append(doc)
    for doc in docs:
        learn_format_profile(approved_cert(doc))

    profile = FormatProfile.objects.get(
        entity__name="Cambridge English", year=2024, exam__isnull=True
    )
    texts = {a["text"] for a in profile.anchors if a.get("text")}
    assert "language: english" not in texts
    assert "issuer_id: cambridge" not in texts
    assert "this is to certify that" in texts


def test_layout_anchors_learned_and_improve_score():
    docs = []
    for i in range(2):
        doc = make_document(fingerprint=f"{i + 40:064x}")
        add_page(doc, BOILERPLATE, layout=IMAGE_LAYOUT)
        docs.append(doc)
    for doc in docs:
        learn_format_profile(approved_cert(doc))

    profile = FormatProfile.objects.get(
        entity__name="Cambridge English", year=2024, exam__isnull=True
    )
    layout_anchors = [a for a in profile.anchors if a.get("kind") == "layout"]
    features = {a["feature"] for a in layout_anchors}
    assert "image:2:0:m" in features
    assert any(f.startswith("tline:") for f in features)

    # A document matching the layout scores higher than one without it.
    with_layout = make_document(fingerprint="9" * 64)
    add_page(with_layout, BOILERPLATE, layout=IMAGE_LAYOUT)
    probe_with = make_certificate(with_layout, review_status=Certificate.ReviewStatus.PENDING)

    without_layout = make_document(fingerprint="8" * 64)
    add_page(without_layout, BOILERPLATE)
    probe_without = make_certificate(without_layout, review_status=Certificate.ReviewStatus.PENDING)

    score_with, _ = score_document_format(probe_with)
    score_without, _ = score_document_format(probe_without)
    assert score_with is not None and score_without is not None
    assert score_with > score_without


def _fitz_pdf(text: str) -> bytes:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 100), "Cambridge Assessment English")
    page.insert_text((72, 140), text)
    data = pdf.tobytes()
    pdf.close()
    return data


class _FakeStore:
    def __init__(self, data: bytes):
        self.data = data
        self.closed = False

    def download_original(self, document_id):
        return self.data

    def close(self):
        self.closed = True


def test_profile_preview_renders_redacted_png(monkeypatch):
    document = make_document(fingerprint="7" * 64)
    add_page(document, BOILERPLATE)
    document.paperless_document_id = "99"
    document.save(update_fields=["paperless_document_id"])
    approved_cert(document)
    profile = FormatProfile.objects.create(
        entity=Entity.objects.get(name="Cambridge English"),
        year=2024,
        sample_count=1,
        anchors=[],
    )

    store = _FakeStore(_fitz_pdf("This is to certify that Ada Lovelace passed."))
    monkeypatch.setattr("documents.services.profile_preview.build_document_store", lambda: store)

    png = render_profile_preview(profile)

    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_profile_preview_refuses_when_name_not_found(monkeypatch):
    document = make_document(fingerprint="6" * 64)
    add_page(document, BOILERPLATE)
    document.paperless_document_id = "98"
    document.save(update_fields=["paperless_document_id"])
    approved_cert(document)
    profile = FormatProfile.objects.create(
        entity=Entity.objects.get(name="Cambridge English"),
        year=2024,
        sample_count=1,
        anchors=[],
    )

    # PDF has text but NOT the student name: cannot prove anonymization.
    store = _FakeStore(_fitz_pdf("This is to certify that the candidate passed."))
    monkeypatch.setattr("documents.services.profile_preview.build_document_store", lambda: store)

    assert render_profile_preview(profile) is None


def test_profile_preview_endpoint_returns_image(client, monkeypatch):
    user = User.objects.create_user("prev", password="password")
    group, _ = Group.objects.get_or_create(name="reviewer")
    user.groups.add(group)
    client.force_login(user)

    document = make_document(fingerprint="5" * 64)
    add_page(document, BOILERPLATE)
    document.paperless_document_id = "97"
    document.save(update_fields=["paperless_document_id"])
    approved_cert(document)
    profile = FormatProfile.objects.create(
        entity=Entity.objects.get(name="Cambridge English"),
        year=2024,
        sample_count=1,
        anchors=[],
    )
    store = _FakeStore(_fitz_pdf("Certificate issued to Ada Lovelace"))
    monkeypatch.setattr("documents.services.profile_preview.build_document_store", lambda: store)

    response = client.get(reverse("documents:format_profile_preview", args=[profile.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_scoring_falls_back_to_entity_pool():
    docs = []
    for i, year in enumerate([2020, 2020, 2024, 2024]):
        doc = make_document(fingerprint=f"{i + 60:064x}")
        add_page(doc, BOILERPLATE)
        docs.append((doc, year))
    for doc, year in docs:
        learn_format_profile(approved_cert(doc, year=year))

    # Probe from a year with no cohort profile: pool profile must score it.
    probe_doc = make_document(fingerprint="3" * 64)
    add_page(probe_doc, BOILERPLATE)
    probe = make_certificate(
        probe_doc,
        issue_date=date(2025, 1, 10),
        review_status=Certificate.ReviewStatus.PENDING,
    )

    score, cohort = score_document_format(probe)

    assert score is not None and score > 0.8
    assert "todos los años" in cohort
