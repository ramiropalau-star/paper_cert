"""Verifier registry: automated source checks where a programmatic
pattern exists.

Verified live contracts (2026-11):

- UV (seu.uv.es): ``GET webges.uv.es/uvEntreuWeb/visualizadorHuella.jsp
  ?identificador=<Id>&huella=<Cod.Verificació>`` returns the signed
  electronic document as ``%PDF`` on success, or the SEU login HTML on
  failure. No captcha, no session.
- GVA (tramita.gva.es): JSF POST + ptt-captcha — GET returns the form
  shell; the check honestly reports ``no_success_marker``.
- Cambridge RVS and Oxford resultsverification.oup.com require
  registered accounts / JS apps — not in the registry (manual confirm).

Unknown domains are never fetched (SSRF allowlist).
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.utils import timezone
from pypdf import PdfReader

from documents.models import Certificate
from documents.services.verification import verification_url_host

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 512_000

# Markers that indicate the source positively confirmed the document.
_SUCCESS_MARKERS = (
    "s'ha verificat",
    "documento válido",
    "documento valido",
    "certificat vàlid",
    "certificado válido",
    "verification successful",
    "certificate verified",
    "es válido",
    "es valid",
)

UV_VERIFY_URL = (
    "https://webges.uv.es/uvEntreuWeb/visualizadorHuella.jsp"
    "?identificador={document_id}&huella={code}&enviarHuella=Cercar"
    "&idiomaActual=ca_ES"
)

# Public alias for seed/configuration use.
SUCCESS_MARKERS = _SUCCESS_MARKERS


@dataclass
class VerificationOutcome:
    ok: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _get(
    url: str, timeout: float = REQUEST_TIMEOUT_SECONDS
) -> tuple[httpx.Response | None, dict[str, Any], str | None]:
    evidence: dict[str, Any] = {"method": "GET", "url": url}
    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "paperless-certs-verifier/1.0"},
            follow_redirects=True,
        ) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        evidence["error"] = str(exc)[:200]
        return None, evidence, "unreachable"
    evidence["http_status"] = response.status_code
    evidence["content_type"] = response.headers.get("content-type", "")
    return response, evidence, None


def _csv_get_verify(certificate: Certificate) -> VerificationOutcome:
    """GET the verification URL and look for a success marker."""
    url = certificate.verification_url
    response, evidence, error = _get(url)
    if response is None:
        return VerificationOutcome(False, error or "unreachable", evidence)

    body = response.content[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace").lower()
    evidence["body_snippet"] = body[:400]
    for marker in _SUCCESS_MARKERS:
        if marker in body:
            return VerificationOutcome(True, f"success_marker:{marker}", evidence)
    return VerificationOutcome(False, "no_success_marker", evidence)


def _uv_verify(certificate: Certificate) -> VerificationOutcome:
    """UV: visualizadorHuella.jsp returns the signed PDF on success."""
    document_id = (certificate.verification_evidence or {}).get("document_id")
    code = certificate.verification_code
    if not document_id or not code:
        return VerificationOutcome(
            False,
            "missing_document_id",
            {"method": "GET", "reason": "Id: or Cod. Verificació not captured"},
        )
    url = UV_VERIFY_URL.format(document_id=document_id, code=code)
    response, evidence, error = _get(url)
    if response is None:
        return VerificationOutcome(False, error or "unreachable", evidence)

    is_pdf = response.content[:5] == b"%PDF-"
    evidence["is_pdf"] = is_pdf
    if not is_pdf:
        return VerificationOutcome(False, "no_pdf_returned", evidence)

    summary = _pdf_summary(response.content, code)
    evidence["pdf"] = summary
    return VerificationOutcome(True, "signed_pdf_returned", evidence)


def _pdf_summary(content: bytes, code: str) -> dict[str, Any]:
    """Extract displayable facts from the verified source document."""
    summary: dict[str, Any] = {
        "sha256": hashlib.sha256(content).hexdigest()[:16],
        "bytes": len(content),
    }
    try:
        reader = PdfReader(io.BytesIO(content))
        summary["pages"] = len(reader.pages)
        info = reader.metadata or {}
        for key in ("Title", "Author", "Creator", "Producer"):
            value = info.get(f"/{key}") or info.get(key)
            if value:
                summary[key.lower()] = str(value)[:200]
        # Confirm the returned document actually carries the queried code.
        if code:
            text = ""
            for page in reader.pages[:3]:
                text += (page.extract_text() or "") + "\n"
            summary["code_found_in_document"] = code in text
    except Exception as exc:
        summary["parse_error"] = str(exc)[:200]
    return summary


Verifier = Callable[[Certificate], VerificationOutcome]

# Registry keyed by hostname (exact match or parent domain suffix).
_VERIFIERS: dict[str, Verifier] = {
    "tramita.gva.es": _csv_get_verify,
    "seu.uv.es": _uv_verify,
    "uv.es": _uv_verify,
}


def _host_matches(config_host: str, host: str) -> bool:
    config_host = (config_host or "").lower()
    host = (host or "").lower()
    return host == config_host or host.endswith("." + config_host)


def _config_for_host(host: str, certificate: Certificate | None = None):
    """Best active VerifierConfig for a host: entity-scoped first, then global."""
    from documents.models import VerifierConfig

    configs = [
        config
        for config in VerifierConfig.objects.filter(is_active=True).select_related("entity")
        if _host_matches(config.host, host)
    ]
    if not configs:
        return None
    entity_id = certificate.entity_id if certificate is not None else None
    for config in configs:
        if config.entity_id is not None and config.entity_id == entity_id:
            return config
    for config in configs:
        if config.entity_id is None:
            return config
    return configs[0]


def _render_url_template(template: str, certificate: Certificate) -> str:
    try:
        return template.format(
            code=certificate.verification_code or "",
            document_id=(certificate.verification_evidence or {}).get("document_id") or "",
            url=certificate.verification_url or "",
        )
    except (KeyError, IndexError, ValueError):
        return ""


def _pdf_text(content: bytes, max_pages: int = 5) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(
            (reader.pages[i].extract_text() or "") for i in range(min(len(reader.pages), max_pages))
        )
    except Exception:  # noqa: BLE001 - comparison is best-effort
        return ""


# Comparison field -> certificate attribute used as the expected value.
_COMPARISON_FIELDS = {
    "student_name": "student_name",
    "entity": "entity_literal",
    "exam": "exam_literal",
    "level": "level_literal",
    "score": "score_literal",
    "certificate_code": "certificate_code",
    "issue_date": "issue_date",
    "exam_date": "exam_date",
    "result_date": "result_date",
}

_DATE_COMPARISON_FIELDS = {"issue_date", "exam_date", "result_date"}


def _normalize_for_compare(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _compare_source_document(
    certificate: Certificate, content: bytes, patterns: dict[str, str]
) -> dict[str, Any]:
    """Compare fields extracted from a verifier-returned source document.

    Returns a comparison record stored as verification evidence; a mismatch
    never marks anything verified by itself.
    """
    comparison: dict[str, Any] = {
        "status": "unavailable",
        "fields": {},
        "checked_at": timezone.now().isoformat(),
    }
    if not patterns or not content:
        return comparison
    text = _pdf_text(content)
    if not text:
        return comparison

    matched = False
    all_match = True
    for field_name, pattern in patterns.items():
        attr = _COMPARISON_FIELDS.get(field_name)
        if attr is None:
            continue
        try:
            match = re.search(pattern, text, re.IGNORECASE)
        except re.error:
            continue
        if not match:
            continue
        matched = True
        actual = (match.group(1) if match.groups() else match.group(0)).strip()
        expected = getattr(certificate, attr, None)
        if field_name in _DATE_COMPARISON_FIELDS:
            from documents.services.classification import parse_date_text

            parsed_actual, _ = parse_date_text(actual)
            field_match = (
                parsed_actual is not None
                and hasattr(expected, "isoformat")
                and parsed_actual == expected
            )
        else:
            field_match = _normalize_for_compare(actual) == _normalize_for_compare(expected)
        comparison["fields"][field_name] = {
            "expected": str(expected or ""),
            "actual": actual[:200],
            "match": bool(field_match),
        }
        if not field_match:
            all_match = False
    if not matched:
        return comparison
    comparison["status"] = "match" if all_match else "mismatch"
    return comparison


def _config_verify(config) -> Verifier:
    """Build a verifier from a data-driven VerifierConfig row."""

    def verifier(certificate: Certificate) -> VerificationOutcome:
        url = _render_url_template(config.url_template or "", certificate)
        if not url:
            return VerificationOutcome(
                False, "missing_url_template", {"method": "GET", "config_id": config.pk}
            )
        timeout = float(config.timeout_seconds or REQUEST_TIMEOUT_SECONDS)
        response, evidence, error = _get(url, timeout=timeout)
        evidence["config_id"] = config.pk
        if response is None:
            return VerificationOutcome(False, error or "unreachable", evidence)

        criteria = config.success_criteria or {}
        markers = [str(m).lower() for m in criteria.get("markers", [])]
        body = response.content[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace").lower()
        evidence["body_snippet"] = body[:400]
        is_pdf = response.content[:5] == b"%PDF-"
        evidence["is_pdf"] = is_pdf

        ok = False
        detail = "no_success_marker"
        if criteria.get("require_pdf") and is_pdf:
            ok, detail = True, "pdf_returned"
        else:
            for marker in markers:
                if marker in body:
                    ok, detail = True, f"success_marker:{marker}"
                    break
        if not ok:
            return VerificationOutcome(False, detail, evidence)

        if config.source_document_parser == config.Parser.PDF_TEXT:
            if is_pdf:
                comparison = _compare_source_document(
                    certificate, response.content, config.source_field_patterns or {}
                )
                evidence["source_comparison"] = comparison
                if config.source_field_patterns:
                    evidence["pdf"] = _pdf_summary(response.content, certificate.verification_code)
            else:
                # Source confirmed but returned no document: comparison is
                # unavailable, not failed.
                evidence["source_comparison"] = {
                    "status": "unavailable",
                    "reason": "no_source_document",
                    "checked_at": timezone.now().isoformat(),
                }
        return VerificationOutcome(True, detail, evidence)

    return verifier


def _resolve_verifier(host: str, certificate: Certificate | None = None) -> Verifier | None:
    host = host.lower()
    config = _config_for_host(host, certificate)
    if config is not None:
        return _config_verify(config)
    if host in _VERIFIERS:
        return _VERIFIERS[host]
    for domain, verifier in _VERIFIERS.items():
        if host == domain or host.endswith("." + domain):
            return verifier
    return None


def verify_at_source(certificate: Certificate) -> Certificate:
    """Attempt automated verification for known verifier domains.

    Never marks verified without a positive source response; failures
    are recorded in ``verification_evidence`` and the status stays
    ``self_reported``.
    """
    if certificate.verification_status == (Certificate.VerificationStatus.MANUALLY_CONFIRMED):
        return certificate
    if not certificate.verification_url:
        return certificate

    host = verification_url_host(certificate.verification_url)
    verifier = _resolve_verifier(host, certificate)
    if verifier is None:
        return certificate

    outcome = verifier(certificate)
    evidence = dict(certificate.verification_evidence or {})
    evidence["auto_check"] = {
        "host": host,
        "ok": outcome.ok,
        "detail": outcome.detail,
        "evidence": outcome.evidence,
        "checked_at": timezone.now().isoformat(),
    }
    comparison = outcome.evidence.get("source_comparison")
    update_fields = [
        "verification_status",
        "verified_by",
        "verified_at",
        "verification_evidence",
        "updated_at",
    ]
    if outcome.ok:
        certificate.verification_status = Certificate.VerificationStatus.VERIFIED_AT_SOURCE
        certificate.verified_at = timezone.now()
        certificate.verified_by = None
    certificate.verification_evidence = evidence
    if comparison:
        certificate.source_comparison = comparison
        update_fields.append("source_comparison")
        if comparison.get("status") == "mismatch":
            reasons = list(certificate.review_reasons or [])
            if "source_mismatch" not in reasons:
                reasons.append("source_mismatch")
            certificate.review_reasons = reasons
            update_fields.append("review_reasons")
    certificate.save(update_fields=update_fields)
    from documents.services.veracity import maybe_compute_veracity

    maybe_compute_veracity(certificate)
    return certificate
