"""Temporary staging files with randomized names."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from django.conf import settings


@contextmanager
def staged_upload(data: bytes, filename: str):
    staging_dir = Path(settings.MEDIA_ROOT) / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    path = staging_dir / f"{uuid4().hex}{suffix}"
    path.write_bytes(data)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
