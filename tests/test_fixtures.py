"""Determinism and size checks for the certificate fixtures (task 13.1)."""

import io

from pypdf import PdfReader

from tests import fixturegen


def test_fixture_generation_is_deterministic():
    for name, (builder, _content_type) in fixturegen.FIXTURES.items():
        assert builder() == builder(), f"{name} is not deterministic"


def test_fixtures_are_small():
    for name, (builder, _content_type) in fixturegen.FIXTURES.items():
        assert len(builder()) < 512 * 1024, f"{name} exceeds 512 KiB"


def test_text_pdf_has_embedded_text():
    reader = PdfReader(io.BytesIO(fixturegen.text_pdf_bytes()))
    assert "Ada Lovelace" in reader.pages[0].extract_text()


def test_scanned_pdf_has_no_text_layer():
    reader = PdfReader(io.BytesIO(fixturegen.scanned_pdf_bytes()))
    assert not (reader.pages[0].extract_text() or "").strip()


def test_multipage_pdf_page_count():
    reader = PdfReader(io.BytesIO(fixturegen.multipage_pdf_bytes()))
    assert len(reader.pages) == 3


def test_committed_fixture_files_match_generator():
    """Files under tests/fixtures/files/ must match the generator output."""
    directory = fixturegen.OUTPUT_DIR
    for name, (builder, _content_type) in fixturegen.FIXTURES.items():
        path = directory / name
        assert path.is_file(), f"missing committed fixture {name}"
        assert path.read_bytes() == builder(), f"{name} is stale; rerun fixturegen"
