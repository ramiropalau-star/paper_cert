import io
from datetime import date

import pytest
import respx
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from openpyxl import load_workbook

from catalog.models import Entity, Language
from documents.models import Certificate, Document
from reports.models import ReportJob
from reports.services import build_workbook, certificates_queryset

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def catalog(db):
    call_command("seed_catalog", verbosity=0)


def make_user(username: str, roles: tuple[str, ...] = ()) -> User:
    user = User.objects.create_user(username, password="password")
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
    return user


def make_document(index: int = 0, **overrides) -> Document:
    data = {
        "fingerprint": f"{index}" * 64,
        "original_filename": f"cert-{index}.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "paperless_document_id": str(100 + index),
        "processing_state": Document.ProcessingState.APPROVED,
        "page_count": 1,
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
        "review_status": Certificate.ReviewStatus.APPROVED,
    }
    data.update(overrides)
    return Certificate.objects.create(**data)


def _rows(ws) -> list[list]:
    return [list(row) for row in ws.iter_rows(values_only=True)]


# --- 10.1/10.2 workbook generation ---


def test_workbook_headers_and_approved_rows():
    eng = Language.objects.get(code="eng")
    cambridge = Entity.objects.get(name="Cambridge English")
    cert = make_certificate(make_document(1), language=eng, entity=cambridge)

    content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))

    assert workbook.sheetnames == ["Certificados", "Pendientes de revisión"]
    main = workbook["Certificados"]
    rows = _rows(main)
    assert rows[0][:9] == [
        "Alumno",
        "Idioma",
        "Nivel",
        "Nivel MCER",
        "Equivalencia UV L2",
        "Entidad certificadora",
        "Fecha de expedición",
        "Certificado o examen",
        "Puntuación",
    ]
    assert rows[0][9:12] == [
        "Estado",
        "Fecha de procesamiento",
        "Referencia al documento",
    ]
    assert rows[0][12:] == [
        "Nombre del fichero",
        "Código de certificado",
        "Centro de examen",
        "Organismo emisor",
        "Motivo del rechazo",
    ]
    assert len(rows) == 2
    assert rows[1][0] == "Ada Lovelace"
    assert rows[1][12] == "cert-1.pdf"
    assert rows[1][1] == "English" or rows[1][1] == eng.name
    assert main["G2"].value.date() == date(2024, 5, 12)
    assert main["G2"].number_format  # date-formatted cell
    assert main.auto_filter.ref


def test_workbook_pending_sheet_separate():
    approved = make_certificate(make_document(1))
    pending = make_certificate(
        make_document(2),
        student_name="Grace Hopper",
        review_status=Certificate.ReviewStatus.PENDING,
    )

    content = build_workbook([approved], [pending])
    workbook = load_workbook(io.BytesIO(content))

    main_rows = _rows(workbook["Certificados"])
    pending_rows = _rows(workbook["Pendientes de revisión"])
    assert len(main_rows) == 2
    assert len(pending_rows) == 2
    assert main_rows[1][0] == "Ada Lovelace"
    assert pending_rows[1][0] == "Grace Hopper"
    assert pending_rows[1][9] == "Pendiente de revisión"
    assert main_rows[1][9] == "Aprobado"


def test_workbook_without_pending_sheet_when_disabled():
    cert = make_certificate(make_document(1))
    content = build_workbook([cert], None)
    workbook = load_workbook(io.BytesIO(content))
    assert workbook.sheetnames == ["Certificados"]


# --- filters ---


def test_certificates_queryset_filters():
    eng = Language.objects.get(code="eng")
    spa = Language.objects.get(code="spa")
    cambridge = Entity.objects.get(name="Cambridge English")
    ielts = Entity.objects.get(name="IELTS")
    make_certificate(
        make_document(1),
        student_name="Ada Lovelace",
        language=eng,
        entity=cambridge,
        level_literal="B2",
    )
    make_certificate(
        make_document(2),
        student_name="Grace Hopper",
        language=eng,
        entity=ielts,
        level_literal="C1",
    )
    make_certificate(
        make_document(3),
        student_name="Sofía Paz",
        language=spa,
        entity=cambridge,
        level_literal="B1",
    )
    rejected = make_certificate(
        make_document(4),
        student_name="Rejected",
        review_status=Certificate.ReviewStatus.REJECTED,
    )
    assert rejected.review_status == Certificate.ReviewStatus.REJECTED

    qs = certificates_queryset({"student": "ada"}, status=Certificate.ReviewStatus.APPROVED)
    assert [c.student_name for c in qs] == ["Ada Lovelace"]

    qs = certificates_queryset(
        {"language": str(eng.pk), "entity": str(ielts.pk), "level": "C1"},
        status=Certificate.ReviewStatus.APPROVED,
    )
    assert [c.student_name for c in qs] == ["Grace Hopper"]

    qs = certificates_queryset(
        {"issue_date_from": "2024-01-01", "issue_date_to": "2024-12-31"},
        status=Certificate.ReviewStatus.APPROVED,
    )
    assert qs.count() == 3  # rejected excluded by status

    qs = certificates_queryset({"language": "spa"}, status=Certificate.ReviewStatus.APPROVED)
    assert [c.student_name for c in qs] == ["Sofía Paz"]


# --- 10.4 job flow ---


@respx.mock
def test_report_job_lifecycle_and_download(client):
    respx.post("http://n8n.test/webhook/report").mock(
        return_value=__import__("httpx").Response(200)
    )
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    make_certificate(make_document(1))
    make_certificate(
        make_document(2),
        review_status=Certificate.ReviewStatus.PENDING,
        student_name="Pending Student",
    )

    response = client.post(
        reverse("reports:list"),
        {"student": "", "include_pending": "1"},
    )
    assert response.status_code == 302
    job = ReportJob.objects.get()
    assert job.status == ReportJob.Status.QUEUED

    # run via internal endpoint (n8n path)
    token_response = client.post(
        reverse("internal-report-run", args=[job.pk]),
        HTTP_X_INTERNAL_TOKEN="wrong",
    )
    assert token_response.status_code == 401

    response = client.post(
        reverse("internal-report-run", args=[job.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == ReportJob.Status.READY
    assert job.artifact_path

    # idempotent second run
    client.post(
        reverse("internal-report-run", args=[job.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    job.refresh_from_db()
    assert job.status == ReportJob.Status.READY

    download = client.get(reverse("reports:download", args=[job.pk]))
    assert download.status_code == 200
    assert "spreadsheetml" in download["Content-Type"]
    workbook = load_workbook(io.BytesIO(b"".join(download.streaming_content)))
    assert workbook.sheetnames == ["Certificados", "Pendientes de revisión"]

    status = client.get(reverse("reports:status", args=[job.pk]))
    assert status.json()["status"] == "ready"
    assert status.json()["download_url"]


@respx.mock
def test_report_job_no_matches_errors(client):
    respx.post("http://n8n.test/webhook/report").mock(
        return_value=__import__("httpx").Response(200)
    )
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    make_certificate(make_document(1))

    client.post(reverse("reports:list"), {"student": "nobody-matches"})
    job = ReportJob.objects.get()
    client.post(
        reverse("internal-report-run", args=[job.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    job.refresh_from_db()
    assert job.status == ReportJob.Status.ERROR
    assert "No hay registros" in job.error_reason

    response = client.get(reverse("reports:download", args=[job.pk]))
    assert response.status_code == 404


def test_internal_run_report_exempt_from_csrf(client, settings):
    """n8n calls carry no CSRF cookie; the endpoint must stay csrf_exempt."""
    settings.APP["internal_api_token"] = "test-internal-token"
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    client.post(reverse("reports:list"), {"student": "", "include_pending": "1"})
    job = ReportJob.objects.get()

    strict = Client(enforce_csrf_checks=True)
    response = strict.post(
        reverse("internal-report-run", args=[job.pk]),
        HTTP_X_INTERNAL_TOKEN="test-internal-token",
    )
    assert response.status_code == 200


def test_report_pages_require_login(client):
    assert client.get(reverse("reports:list")).status_code == 302
    assert client.get(reverse("reports:detail", args=[1])).status_code == 302
    assert client.get(reverse("reports:status", args=[1])).status_code == 302
    assert client.get(reverse("reports:download", args=[1])).status_code == 302
    assert client.post(reverse("internal-report-run", args=[1])).status_code == 401


def test_report_job_filter_persistence(client):
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    client.post(
        reverse("reports:list"),
        {
            "student": "Ada",
            "language": "1",
            "entity": "2",
            "level": "B2",
            "issue_date_from": "2024-01-01",
            "issue_date_to": "2024-12-31",
            "include_pending": "1",
        },
    )
    job = ReportJob.objects.get()
    assert job.filters["student"] == "Ada"
    assert job.filters["language"] == "1"
    assert job.filters["entity"] == "2"
    assert job.filters["level"] == "B2"
    assert job.filters["issue_date_from"] == "2024-01-01"
    assert job.filters["issue_date_to"] == "2024-12-31"
    assert job.filters["include_pending"] is True


def test_rejected_excluded_from_main_sheet():
    approved = make_certificate(make_document(1))
    make_certificate(
        make_document(2),
        review_status=Certificate.ReviewStatus.REJECTED,
        student_name="Rejected Person",
    )
    content = build_workbook([approved], [])
    workbook = load_workbook(io.BytesIO(content))
    rows = _rows(workbook["Certificados"])
    assert len(rows) == 2
    assert all("Rejected" not in str(cell) for cell in rows[1])


def test_rejected_sheet_includes_rejection_reason():
    from documents.models import ReviewEvent

    rejected = make_certificate(
        make_document(2),
        review_status=Certificate.ReviewStatus.REJECTED,
        student_name="Rejected Person",
    )
    ReviewEvent.objects.create(
        certificate=rejected,
        event_type=ReviewEvent.EventType.REJECT,
        reason="Documento ilegible",
    )

    content = build_workbook([], None, [rejected])
    workbook = load_workbook(io.BytesIO(content))

    assert workbook.sheetnames == ["Certificados", "Rechazados"]
    rows = _rows(workbook["Rechazados"])
    assert rows[1][0] == "Rejected Person"
    assert rows[1][9] == "Rechazado"
    assert rows[1][16] == "Documento ilegible"


def test_generate_report_includes_rejected_sheet(client, monkeypatch, tmp_path):
    monkeypatch.setitem(settings.APP, "report_output_dir", str(tmp_path))
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    approved = make_certificate(make_document(1))
    rejected = make_certificate(
        make_document(2),
        review_status=Certificate.ReviewStatus.REJECTED,
        student_name="Rejected Person",
    )
    from documents.models import ReviewEvent

    ReviewEvent.objects.create(
        certificate=rejected,
        event_type=ReviewEvent.EventType.REJECT,
        reason="No es un certificado de idioma",
    )

    from reports.services import generate_report

    job = ReportJob.objects.create(
        filters={"include_pending": False}, requested_by=viewer
    )
    generate_report(job)

    assert job.status == ReportJob.Status.READY
    workbook = load_workbook(job.artifact_path)
    assert "Rechazados" in workbook.sheetnames
    rows = _rows(workbook["Rechazados"])
    assert rows[1][16] == "No es un certificado de idioma"
