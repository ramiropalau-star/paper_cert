import io
from datetime import UTC, date

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
    cert = make_certificate(
        make_document(
            1,
            original_filename="2027ERASMUSWF29402_I.Certificado_Idioma_E.pdf",
        ),
        language=eng,
        entity=cambridge,
    )

    content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))

    assert workbook.sheetnames == ["Certificados", "Pendientes de revisión"]
    main = workbook["Certificados"]
    rows = _rows(main)
    assert rows[0][:10] == [
        "Alumno",
        "NPA",
        "Idioma",
        "Nivel",
        "Nivel MCER",
        "Equivalencia UV L2",
        "Entidad certificadora",
        "Fecha de expedición",
        "Certificado o examen",
        "Puntuación",
    ]
    assert rows[0][10:13] == [
        "Estado",
        "Fecha de procesamiento",
        "Referencia al documento",
    ]
    assert rows[0][13:] == [
        "Nombre del fichero",
        "Código de certificado",
        "Centro de examen",
        "Organismo emisor",
        "Motivo del rechazo",
    ]
    assert len(rows) == 2
    assert rows[1][0] == "Ada Lovelace"
    assert rows[1][1] == "WF29402"
    assert rows[1][13] == "2027ERASMUSWF29402_I.Certificado_Idioma_E.pdf"
    assert rows[1][2] == "English" or rows[1][2] == eng.name
    assert main["H2"].value.date() == date(2024, 5, 12)
    assert main["H2"].number_format  # date-formatted cell
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
    assert pending_rows[1][10] == "Pendiente de revisión"
    assert main_rows[1][10] == "Aprobado"


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
    assert rows[1][10] == "Rechazado"
    assert rows[1][17] == "Documento ilegible"


def test_generate_report_includes_rejected_sheet(client, monkeypatch, tmp_path):
    monkeypatch.setitem(settings.APP, "report_output_dir", str(tmp_path))
    viewer = make_user("viewer", ("viewer",))
    client.force_login(viewer)
    make_certificate(make_document(1))
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

    job = ReportJob.objects.create(filters={"include_pending": False}, requested_by=viewer)
    generate_report(job)

    assert job.status == ReportJob.Status.READY
    workbook = load_workbook(job.artifact_path)
    assert "Rechazados" in workbook.sheetnames
    rows = _rows(workbook["Rechazados"])
    assert rows[1][17] == "No es un certificado de idioma"


# --- reporting integrity ---


def test_processing_date_uses_processed_at_in_local_timezone():
    from datetime import datetime

    from django.utils import timezone

    document = make_document(
        5,
        processed_at=datetime(2024, 5, 13, 2, 30, tzinfo=UTC),
    )
    cert = make_certificate(document)

    with timezone.override("America/New_York"):
        content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))
    # 2024-05-13 02:30 UTC is 2024-05-12 22:30 in New York.
    assert workbook["Certificados"]["L2"].value.date() == date(2024, 5, 12)

    content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))
    assert workbook["Certificados"]["L2"].value.date() == date(2024, 5, 13)


def test_processing_date_survives_later_document_edits():
    from datetime import datetime

    document = make_document(
        6,
        processed_at=datetime(2024, 5, 10, 12, 0, tzinfo=UTC),
    )
    cert = make_certificate(document)
    Document.objects.filter(pk=document.pk).update(
        updated_at=datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    )

    content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))
    assert workbook["Certificados"]["L2"].value.date() == date(2024, 5, 10)


def test_processing_date_falls_back_to_updated_at_for_legacy_rows():
    document = make_document(7)
    assert document.processed_at is None
    cert = make_certificate(document)

    content = build_workbook([cert], [])
    workbook = load_workbook(io.BytesIO(content))
    cell = workbook["Certificados"]["L2"].value
    assert cell.date() == document.updated_at.date()


def test_generate_report_persists_counts_matching_sheets(client, monkeypatch, tmp_path):
    monkeypatch.setitem(settings.APP, "report_output_dir", str(tmp_path))
    viewer = make_user("viewer-counts", ("viewer",))
    client.force_login(viewer)
    make_certificate(make_document(1))
    make_certificate(
        make_document(2),
        review_status=Certificate.ReviewStatus.PENDING,
        student_name="Pending One",
    )
    make_certificate(
        make_document(3),
        review_status=Certificate.ReviewStatus.VALIDATED,
        student_name="Validated One",
    )
    make_certificate(
        make_document(4),
        review_status=Certificate.ReviewStatus.REJECTED,
        student_name="Rejected One",
    )

    from reports.services import generate_report

    job = ReportJob.objects.create(filters={"include_pending": True}, requested_by=viewer)
    generate_report(job)

    assert job.status == ReportJob.Status.READY
    assert job.counts == {"approved": 1, "pending": 2, "rejected": 1, "total": 4}

    workbook = load_workbook(job.artifact_path)
    assert len(_rows(workbook["Certificados"])) - 1 == job.counts["approved"]
    assert len(_rows(workbook["Pendientes de revisión"])) - 1 == job.counts["pending"]
    assert len(_rows(workbook["Rechazados"])) - 1 == job.counts["rejected"]


def test_report_detail_shows_counts_unavailable_for_legacy_job(client):
    viewer = make_user("viewer-legacy", ("viewer",))
    client.force_login(viewer)
    job = ReportJob.objects.create(
        filters={}, status=ReportJob.Status.READY, artifact_path="/tmp/old.xlsx"
    )

    response = client.get(reverse("reports:detail", args=[job.pk]))

    assert response.status_code == 200
    assert b"No disponible" in response.content


def test_report_creation_rejects_invalid_date_filter(client):
    viewer = make_user("viewer-filter", ("viewer",))
    client.force_login(viewer)

    response = client.post(reverse("reports:list"), {"issue_date": "not-a-date"})

    assert response.status_code == 302
    assert ReportJob.objects.count() == 0


def test_report_creation_rejects_ambiguous_date_filter(client):
    viewer = make_user("viewer-ambig", ("viewer",))
    client.force_login(viewer)

    response = client.post(reverse("reports:list"), {"issue_date_from": "05/06/2024"})

    assert response.status_code == 302
    assert ReportJob.objects.count() == 0


def test_generate_report_marks_error_on_invalid_filters(monkeypatch, tmp_path):
    monkeypatch.setitem(settings.APP, "report_output_dir", str(tmp_path))
    from reports.services import generate_report

    job = ReportJob.objects.create(filters={"issue_date_to": "bogus"})
    generate_report(job)

    assert job.status == ReportJob.Status.ERROR
    assert "issue_date_to" in job.error_reason


def test_ready_job_artifact_is_immutable(client, monkeypatch, tmp_path):
    monkeypatch.setitem(settings.APP, "report_output_dir", str(tmp_path))
    from reports.services import generate_report, run_report_job

    viewer = make_user("viewer-snap", ("viewer",))
    cert = make_certificate(make_document(1))
    job = ReportJob.objects.create(filters={}, requested_by=viewer)
    generate_report(job)
    first_path = job.artifact_path
    first_bytes = open(first_path, "rb").read()

    cert.student_name = "Changed Name"
    cert.save()

    again = run_report_job(job.pk)
    assert again.status == ReportJob.Status.READY
    assert again.artifact_path == first_path
    assert open(first_path, "rb").read() == first_bytes

    job2 = ReportJob.objects.create(filters={}, requested_by=viewer)
    generate_report(job2)
    assert job2.artifact_path != first_path
    assert open(first_path, "rb").read() == first_bytes
    workbook = load_workbook(job2.artifact_path)
    assert "Changed Name" in [row[0] for row in _rows(workbook["Certificados"])[1:]]
