"""Verifier registry: automated source checks where a programmatic
pattern exists.

v1 implements the CSV-family GET check used by tramita.gva.es-style
endpoints: fetch the stored verification URL once (bounded timeout) and
look for a success marker in the response. The GVA endpoint currently
requires a JSF POST + captcha, so the GET returns the form shell — the
check honestly reports ``not_confirmed`` instead of guessing.

Unknown domains are never fetched (SSRF allowlist).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from django.utils import timezone

from documents.models import Certificate
from documents.services.verification import verification_url_host

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 5
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


@dataclass
class VerificationOutcome:
    ok: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _csv_get_verify(url: str, code: str) -> VerificationOutcome:
    """GET the verification URL and look for a success marker."""
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
        return VerificationOutcome(False, "unreachable", evidence)

    evidence["http_status"] = response.status_code
    body = response.text[:MAX_RESPONSE_BYTES].lower()
    evidence["body_snippet"] = body[:400]
    for marker in _SUCCESS_MARKERS:
        if marker in body:
            return VerificationOutcome(
                True, f"success_marker:{marker}", evidence
            )
    return VerificationOutcome(False, "no_success_marker", evidence)


Verifier = Callable[[str, str], VerificationOutcome]

# Registry keyed by hostname (exact match or parent domain suffix).
_VERIFIERS: dict[str, Verifier] = {
    "tramita.gva.es": _csv_get_verify,
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
    if certificate.verification_status in (
        Certificate.VerificationStatus.VERIFIED_AT_SOURCE,
        Certificate.VerificationStatus.MANUALLY_CONFIRMED,
    ):
        return certificate
    if not certificate.verification_url:
        return certificate

    host = verification_url_host(certificate.verification_url)
    verifier = _resolve_verifier(host)
    if verifier is None:
        return certificate

    outcome = verifier(certificate.verification_url, certificate.verification_code)
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
