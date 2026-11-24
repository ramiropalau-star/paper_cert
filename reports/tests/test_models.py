import pytest

from reports.models import ReportJob

pytestmark = pytest.mark.django_db


def test_report_job_defaults_and_state_progression():
    job = ReportJob.objects.create(filters={"language": "eng"})

    assert job.status == ReportJob.Status.QUEUED
    assert job.filters == {"language": "eng"}
    assert job.artifact_path == ""
    assert job.completed_at is None

    job.status = ReportJob.Status.READY
    job.artifact_path = "reports/example.xlsx"
    job.save()

    job.refresh_from_db()
    assert job.status == ReportJob.Status.READY
    assert job.artifact_path == "reports/example.xlsx"
