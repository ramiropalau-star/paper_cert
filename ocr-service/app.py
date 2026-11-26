from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Annotated

import pypdfium2 as pdfium
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageSequence
from pypdf import PdfReader

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

CONTRACT_VERSION = "v1"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_languages() -> tuple[str, ...]:
    raw = os.environ.get("OCR_LANGUAGES", "eng,spa")
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or ("eng",)


@dataclass
class Settings:
    page_timeout_seconds: float = _env_float("OCR_PAGE_TIMEOUT_SECONDS", 60.0)
    request_timeout_seconds: float = _env_float("OCR_REQUEST_TIMEOUT_SECONDS", 600.0)
    page_limit: int = _env_int("OCR_PAGE_LIMIT", 100)
    min_text_chars: int = _env_int("OCR_MIN_TEXT_CHARS", 20)
    low_confidence_threshold: float = _env_float("OCR_LOW_CONFIDENCE_THRESHOLD", 0.55)
    max_upload_bytes: int = _env_int("OCR_MAX_UPLOAD_BYTES", 26_214_400)
    default_languages: tuple[str, ...] = _env_languages()


settings = Settings()


class OcrFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable

    def payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


@lru_cache
def _version(command: tuple[str, ...]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
    return first_line or "unavailable"


@lru_cache
def engine_info() -> dict:
    return {
        "name": "tesseract",
        "tesseract": _version(("tesseract", "--version")),
    }


def parse_languages(raw: str | None) -> tuple[str, ...]:
    if raw:
        values = tuple(item.strip() for item in raw.split(",") if item.strip())
        if values:
            return values
    return settings.default_languages


def tesseract_language_arg(languages: Iterable[str]) -> str:
    values = tuple(languages)
    return "+".join(values) if values else "eng"


def _parse_tsv(output: str) -> tuple[str, float]:
    lines: dict[tuple[str, str, str, str], list[str]] = {}
    confidences: list[float] = []
    for row in output.splitlines()[1:]:
        columns = row.split("\t", 11)
        if len(columns) < 12:
            continue
        text = columns[11].strip()
        if not text:
            continue
        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        if confidence < 0:
            continue
        key = (columns[1], columns[2], columns[3], columns[4])
        lines.setdefault(key, []).append(text)
        confidences.append(confidence)
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    mean = round(sum(confidences) / len(confidences) / 100.0, 4) if confidences else 0.0
    return text, mean


def run_tesseract_tsv(
    image_path: Path,
    languages: tuple[str, ...],
    timeout: float,
    page_number: int | None = None,
) -> tuple[str, float]:
    command = [
        "tesseract",
        str(image_path),
        "stdout",
        "-l",
        tesseract_language_arg(languages),
        "--psm",
        "6",
        "tsv",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=True
        )
    except subprocess.TimeoutExpired as exc:
        where = f" on page {page_number}" if page_number is not None else ""
        raise OcrFailure(
            "page_timeout",
            f"OCR exceeded the per-page timeout{where}",
            status_code=504,
            retryable=True,
        ) from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OcrFailure("unreadable", "Tesseract could not read the input") from exc
    return _parse_tsv(completed.stdout)


def render_pdf_page(pdf_path: Path, page_index: int, output_path: Path) -> None:
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[page_index]
        bitmap = page.render(scale=2.0)
        image = bitmap.to_pil()
        image.save(output_path)
    finally:
        document.close()


def _page(page_number: int, text: str, method: str, confidence: float) -> dict:
    return {
        "page_number": page_number,
        "text": text.strip(),
        "method": method,
        "confidence": round(float(confidence), 4),
    }


def _result(pages: list[dict]) -> dict:
    ocr_confidences = [page["confidence"] for page in pages if page["method"] == "ocr"]
    mean_confidence = (
        round(sum(ocr_confidences) / len(ocr_confidences), 4) if ocr_confidences else 1.0
    )
    low_quality = bool(ocr_confidences) and mean_confidence < settings.low_confidence_threshold
    return {
        "contract_version": CONTRACT_VERSION,
        "engine": engine_info(),
        "page_count": len(pages),
        "mean_confidence": mean_confidence,
        "quality": "low" if low_quality else "ok",
        "pages": pages,
    }


def _remaining_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise OcrFailure(
            "request_timeout",
            "OCR request exceeded the total timeout",
            status_code=504,
            retryable=True,
        )
    return remaining


def process_pdf(data: bytes, languages: tuple[str, ...], page_limit: int) -> dict:
    deadline = time.monotonic() + settings.request_timeout_seconds
    with tempfile.TemporaryDirectory(prefix="ocr-pdf-") as temp_dir:
        input_path = Path(temp_dir) / "input.pdf"
        input_path.write_bytes(data)

        try:
            reader = PdfReader(str(input_path))
            page_count = len(reader.pages)
            original_texts = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise OcrFailure("unreadable", "The PDF could not be parsed") from exc

        if page_count == 0:
            raise OcrFailure("unreadable", "The PDF has no pages")
        if page_count > page_limit:
            raise OcrFailure(
                "too_many_pages",
                f"PDF has {page_count} pages; the limit is {page_limit}",
            )

        if all(len(text.strip()) >= settings.min_text_chars for text in original_texts):
            pages = [
                _page(index + 1, text, "embedded", 1.0) for index, text in enumerate(original_texts)
            ]
            return _result(pages)

        pages: list[dict] = []
        for index, original in enumerate(original_texts):
            if len(original.strip()) >= settings.min_text_chars:
                pages.append(_page(index + 1, original, "embedded", 1.0))
                continue
            page_image = Path(temp_dir) / f"page-{index + 1}.png"
            render_pdf_page(input_path, index, page_image)
            tesseract_text, confidence = run_tesseract_tsv(
                page_image,
                languages,
                min(settings.page_timeout_seconds, _remaining_time(deadline)),
                page_number=index + 1,
            )
            pages.append(_page(index + 1, tesseract_text, "ocr", confidence))

        if len("\n".join(page["text"] for page in pages).strip()) < settings.min_text_chars:
            raise OcrFailure("no_text", "OCR produced too little usable text")
        return _result(pages)


def process_image(data: bytes, languages: tuple[str, ...], page_limit: int) -> dict:
    try:
        image = Image.open(BytesIO(data))
        frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(image)]
    except Exception as exc:
        raise OcrFailure("unreadable", "The image could not be parsed") from exc

    if not frames:
        raise OcrFailure("unreadable", "The image has no frames")
    if len(frames) > page_limit:
        raise OcrFailure(
            "too_many_pages",
            f"Image has {len(frames)} frames; the limit is {page_limit}",
        )

    deadline = time.monotonic() + settings.request_timeout_seconds
    pages: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ocr-image-") as temp_dir:
        for index, frame in enumerate(frames):
            image_path = Path(temp_dir) / f"page-{index + 1}.png"
            frame.save(image_path, format="PNG")
            text, confidence = run_tesseract_tsv(
                image_path,
                languages,
                min(settings.page_timeout_seconds, _remaining_time(deadline)),
                page_number=index + 1,
            )
            pages.append(_page(index + 1, text, "ocr", confidence))

    if len("\n".join(page["text"] for page in pages).strip()) < settings.min_text_chars:
        raise OcrFailure("no_text", "OCR produced too little usable text")
    return _result(pages)


def process_document_bytes(
    data: bytes,
    filename: str,
    content_type: str,
    languages: tuple[str, ...],
    page_limit: int,
) -> dict:
    if not data:
        raise OcrFailure("empty_file", "Uploaded file is empty", status_code=400)
    if len(data) > settings.max_upload_bytes:
        raise OcrFailure(
            "file_too_large",
            f"Upload exceeds {settings.max_upload_bytes} bytes",
            status_code=413,
        )

    suffix = Path(filename or "").suffix.lower()
    is_pdf = suffix == ".pdf" or content_type == "application/pdf"
    allowed_images = {
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
        ".bmp",
        ".gif",
        ".heic",
        ".heif",
        ".avif",
    }
    if not is_pdf and suffix not in allowed_images and not content_type.startswith("image/"):
        raise OcrFailure(
            "unsupported_file", "Only PDF and image files are supported", status_code=400
        )

    if is_pdf:
        return process_pdf(data, languages, page_limit)
    return process_image(data, languages, page_limit)


app = FastAPI(title="Certificate OCR service", version=CONTRACT_VERSION)


@app.get("/health")
def health() -> JSONResponse:
    info = engine_info()
    healthy = info["tesseract"] != "unavailable"
    return JSONResponse(
        {
            "status": "healthy" if healthy else "degraded",
            "contract_version": CONTRACT_VERSION,
            "engine": info,
        },
        status_code=200 if healthy else 503,
    )


@app.post("/v1/ocr")
async def ocr_endpoint(
    file: Annotated[UploadFile, File()],
    languages: Annotated[str, Form()] = "",
    page_limit: Annotated[int, Form()] = 0,
) -> JSONResponse:
    data = await file.read()
    selected_languages = parse_languages(languages)
    limit = page_limit if page_limit > 0 else settings.page_limit

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                process_document_bytes,
                data,
                file.filename or "upload",
                file.content_type or "application/octet-stream",
                selected_languages,
                limit,
            ),
            timeout=settings.request_timeout_seconds,
        )
    except OcrFailure as exc:
        return JSONResponse(exc.payload(), status_code=exc.status_code)
    except TimeoutError:
        failure = OcrFailure(
            "request_timeout",
            "OCR exceeded the total request timeout",
            status_code=504,
            retryable=True,
        )
        return JSONResponse(failure.payload(), status_code=failure.status_code)
    return JSONResponse(result)
