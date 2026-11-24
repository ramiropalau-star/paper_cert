from unittest.mock import patch

from documents.services.inbox import scan_inbox_once
from documents.services.intake import IntakeResult


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4 fake"


def test_scan_inbox_processes_and_moves_file(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    (tmp_path / "cert.pdf").write_bytes(_pdf_bytes())

    with patch(
        "documents.services.inbox.process_upload",
        return_value=IntakeResult(document=None),
    ) as mock_process:
        handled = scan_inbox_once()

    assert handled == ["cert.pdf"]
    mock_process.assert_called_once()
    args = mock_process.call_args.args
    assert args[1] == "cert.pdf"
    assert (tmp_path / "processed" / "cert.pdf").exists()
    assert not (tmp_path / "cert.pdf").exists()


def test_scan_inbox_moves_failures_to_failed_dir(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    (tmp_path / "bad.pdf").write_bytes(_pdf_bytes())

    with patch(
        "documents.services.inbox.process_upload",
        return_value=IntakeResult(document=None, error="boom", error_code="x"),
    ):
        scan_inbox_once()

    assert (tmp_path / "failed" / "bad.pdf").exists()


def test_scan_inbox_ignores_non_certificate_files(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    (tmp_path / "notes.txt").write_text("hello")

    with patch("documents.services.inbox.process_upload") as mock_process:
        assert scan_inbox_once() == []

    mock_process.assert_not_called()
    assert (tmp_path / "notes.txt").exists()
