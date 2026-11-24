"""Upload validation for PDFs and image certificates."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import magic
from django.conf import settings
from PIL import Image
from pypdf import PdfReader

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

ALLOWED_EXTENSIONS = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".tif": "image",
    ".tiff": "image",
    ".webp": "image",
    ".bmp": "image",
    ".gif": "image",
    ".heic": "image",
    ".heif": "image",
    ".avif": "image",
}

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/bmp",
    "image/gif",
    "image/heic",
    "image/heif",
    "image/avif",
}

# Canonical stored content type for each MIME that libmagic may report.
_TYPE_BY_MAGIC = {
    "application/pdf": "application/pdf",
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/tiff": "image/tiff",
    "image/webp": "image/webp",
    "image/bmp": "image/bmp",
    "image/x-ms-bmp": "image/bmp",
    "image/gif": "image/gif",
    "image/heic": "image/heic",
    "image/heif": "image/heif",
    "image/avif": "image/avif",
}

EXTENSION_BY_TYPE = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/avif": ".avif",
}

MAGIC_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
    ".gif": {"image/gif"},
    ".heic": {"image/heic", "image/heif"},
    ".heif": {"image/heic", "image/heif"},
    ".avif": {"image/avif"},
}


class IntakeValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    data: bytes
    filename: str
    content_type: str
    kind: str
    page_count: int


def _extension(filename: str) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return suffix


def _sniffed_mime(data: bytes) -> str:
    try:
        return magic.from_buffer(data[:4096], mime=True) or ""
    except Exception:
        return ""


def preprocess_upload(data: bytes, filename: str, content_type: str) -> tuple[str, str]:
    """Detect the real payload type and repair a missing or unknown extension.

    Returns the (possibly renamed) filename and the canonical content type.
    Files whose extension is already supported are returned unchanged; the
    strict extension/content match is enforced later by ``validate_upload``.
    """
    detected = _sniffed_mime(data)
    canonical = _TYPE_BY_MAGIC.get(detected)
    if canonical is None:
        return filename, content_type
    if _extension(filename) in ALLOWED_EXTENSIONS:
        return filename, canonical
    stem = Path(filename or "document").stem or "document"
    return f"{stem}{EXTENSION_BY_TYPE[canonical]}", canonical


def validate_upload(data: bytes, filename: str, content_type: str) -> ValidatedUpload:
    if not data:
        raise IntakeValidationError("empty_file", "El archivo está vacío.")

    max_bytes = int(settings.APP["upload_max_bytes"])
    if len(data) > max_bytes:
        raise IntakeValidationError(
            "file_too_large",
            f"El archivo supera el máximo de {max_bytes} bytes.",
        )

    filename, sniffed_type = preprocess_upload(data, filename, content_type)

    extension = _extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise IntakeValidationError(
            "unsupported_extension",
            "Solo se aceptan PDF e imágenes (JPG, PNG, TIFF, WebP, BMP, GIF, HEIC, HEIF, AVIF).",
        )

    if sniffed_type not in ALLOWED_CONTENT_TYPES and (
        (content_type or "").split(";", 1)[0].strip().lower()
        not in ALLOWED_CONTENT_TYPES
    ):
        raise IntakeValidationError(
            "unsupported_mime",
            "El tipo de contenido declarado no está permitido.",
        )

    detected = _sniffed_mime(data)
    if detected not in MAGIC_BY_EXTENSION[extension]:
        raise IntakeValidationError(
            "content_mismatch",
            "El contenido del archivo no coincide con su extensión.",
        )

    stored_type = _TYPE_BY_MAGIC.get(detected) or sniffed_type
    if stored_type not in ALLOWED_CONTENT_TYPES:
        raise IntakeValidationError(
            "unsupported_mime",
            "El tipo de contenido declarado no está permitido.",
        )

    kind = ALLOWED_EXTENSIONS[extension]
    if kind == "pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise IntakeValidationError(
                    "encrypted_pdf", "El PDF está protegido con contraseña."
                )
            page_count = len(reader.pages)
        except IntakeValidationError:
            raise
        except Exception as exc:
            raise IntakeValidationError("invalid_pdf", "El PDF no se puede leer.") from exc
        max_pages = int(settings.APP["pdf_max_pages"])
        if page_count < 1:
            raise IntakeValidationError("invalid_pdf", "El PDF no tiene páginas.")
        if page_count > max_pages:
            raise IntakeValidationError(
                "too_many_pages",
                f"El PDF supera el máximo de {max_pages} páginas.",
            )
        return ValidatedUpload(data, filename, stored_type, kind, page_count)

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise IntakeValidationError("invalid_image", "La imagen no se puede leer.") from exc

    return ValidatedUpload(data, filename, stored_type, kind, 1)
