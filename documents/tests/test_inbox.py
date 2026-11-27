from unittest.mock import patch

import pytest

from documents.services import inbox as inbox_service
from documents.services.inbox import scan_inbox_once
from documents.services.intake import IntakeResult


@pytest.fixture(autouse=True)
def _clear_settle_state():
    inbox_service._settle_seen.clear()
    yield
    inbox_service._settle_seen.clear()


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


def test_scan_inbox_waits_for_file_to_settle(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    settings.APP["inbox_settle_seconds"] = 60.0
    target = tmp_path / "cert.pdf"
    target.write_bytes(_pdf_bytes())

    with patch(
        "documents.services.inbox.process_upload",
        return_value=IntakeResult(document=None),
    ) as mock_process:
        assert scan_inbox_once() == []
        mock_process.assert_not_called()
        assert target.exists()

        # Still inside the window on the next scan.
        assert scan_inbox_once() == []
        mock_process.assert_not_called()
        assert target.exists()

        # Once the signature has been stable for the window it is processed.
        key = str(target)
        size, mtime_ns, _ = inbox_service._settle_seen[key]
        inbox_service._settle_seen[key] = (size, mtime_ns, 0.0)
        assert scan_inbox_once() == ["cert.pdf"]
        mock_process.assert_called_once()
        assert (tmp_path / "processed" / "cert.pdf").exists()


def test_scan_inbox_settle_window_resets_on_change(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    settings.APP["inbox_settle_seconds"] = 60.0
    target = tmp_path / "cert.pdf"
    target.write_bytes(_pdf_bytes())

    with patch(
        "documents.services.inbox.process_upload",
        return_value=IntakeResult(document=None),
    ) as mock_process:
        scan_inbox_once()
        # Simulate the file still being written: size changes between scans,
        # which resets the settle timer.
        target.write_bytes(_pdf_bytes() + b"more")
        assert scan_inbox_once() == []
        mock_process.assert_not_called()
        assert target.exists()


def test_scan_inbox_settle_window_is_configurable(tmp_path, settings):
    settings.APP["inbox_dir"] = str(tmp_path)
    settings.APP["inbox_settle_seconds"] = 0.0
    (tmp_path / "cert.pdf").write_bytes(_pdf_bytes())

    with patch(
        "documents.services.inbox.process_upload",
        return_value=IntakeResult(document=None),
    ):
        assert scan_inbox_once() == ["cert.pdf"]
