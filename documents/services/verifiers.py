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

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from django.utils import timezone

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


@dataclass
class VerificationOutcome:
    ok: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _get(url: str) -> tuple[httpx.Response | None, dict[str, Any], str | None]:
    evidence: dict[str, Any] = {"method": "GET", "url": url}
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
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

    body = response.content[:MAX_RESPONSE_BYTES].decode(
        "utf-8", errors="replace"
    ).lower()
    evidence["body_snippet"] = body[:400]
    for marker in _SUCCESS_MARKERS:
        if marker in body:
            return VerificationOutcome(
                True, f"success_marker:{marker}", evidence
            )
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
    if is_pdf:
        return VerificationOutcome(True, "signed_pdf_returned", evidence)
    return VerificationOutcome(False, "no_pdf_returned", evidence)


Verifier = Callable[[Certificate], VerificationOutcome]

# Registry keyed by hostname (exact match or parent domain suffix).
_VERIFIERS: dict[str, Verifier] = {
    "tramita.gva.es": _csv_get_verify,
    "seu.uv.es": _uv_verify,
    "uv.es": _uv_verify,
}


def _resolve_verifier(host: str) -> Verifier | None:
    host = host.lower()
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
    if certificate.verification_status == (
        Certificate.VerificationStatus.MANUALLY_CONFIRMED
    ):
        return certificate
    if not certificate.verification_url:
        return certificate

    host = verification_url_host(certificate.verification_url)
    verifier = _resolve_verifier(host)
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
    certificate.verification_evidence = evidence
    if outcome.ok:
        certificate.verification_status = (
            Certificate.VerificationStatus.VERIFIED_AT_SOURCE
        )
        certificate.verified_at = timezone.now()
        certificate.verified_by = None
    certificate.save(
        update_fields=[
            "verification_status",
            "verified_by",
            "verified_at",
            "verification_evidence",
            "updated_at",
        ]
    )
    return certificate
