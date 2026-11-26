"""Shared file-type sniffing and filename helpers.

Callers keep control over which MIME types they accept (``allowed_mimes``)
and which extension map they use (``extension_map``).
"""

from pathlib import Path

import magic


def sniffed_type(data: bytes, allowed_mimes=None) -> str:
    """Detect the real payload MIME type from its bytes.

    Returns "" when detection fails or, if ``allowed_mimes`` is given, when
    the detected type is not in the allowlist.
    """
    try:
        mime = magic.from_buffer(data[:4096], mime=True) or ""
    except Exception:
        return ""
    if allowed_mimes is not None and mime not in allowed_mimes:
        return ""
    return mime


def effective_name(filename: str, content_type: str, extension_map) -> str:
    """Return ``filename`` with the canonical extension for ``content_type``.

    Unknown types leave the filename unchanged.
    """
    extension = extension_map.get(content_type)
    if extension is None:
        return filename
    return f"{Path(filename or 'document').stem}{extension}"
