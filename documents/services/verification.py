"""Deterministic capture and source verification of issuer artifacts.

Harvest runs over extracted page text looking for label-anchored
verification codes and URLs. Automated verification only runs for
issuers whose endpoint follows a known programmatic pattern (registry in
``verifiers.py``); everything else stays ``self_reported`` for manual
reviewer confirmation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from documents.models import Certificate

logger = logging.getLogger(__name__)

MAX_URL_LENGTH = 500

# Code shapes seen on real certificates: CSV groups, alphanumeric codes.
_CODE_VALUE = r"[A-Z0-9][A-Z0-9\-]{5,40}"

_CODE_PATTERNS = (
    # "CSV 9613SQ59-DUKRFULT-YG7CRNFK" / "CSV: XXXX-..."
    re.compile(rf"\bcsv\b[\s:–—-]*({_CODE_VALUE})", re.IGNORECASE),
    # "Cod. Verificació: H480...", "Código de verificación", "Cod. Verificacio"
    re.compile(
        rf"(?:cod\.?\s*verificaci[oó]|c[oó]digo\s+de\s+verificaci[oó]n)"
        rf"[\s:–—-]*({_CODE_VALUE})",
        re.IGNORECASE,
    ),
    # "Verification Number\nD7952856", "Verification Code: ..."
    re.compile(
        rf"verification\s+(?:number|code|id)[\s:–—-]*({_CODE_VALUE})",
        re.IGNORECASE,
    ),
    # "Código de validación", "código de seguimiento"
    re.compile(
        rf"c[oó]digo\s+de\s+(?:validaci[oó]n|seguimiento|certificado)"
        rf"[\s:–—-]*({_CODE_VALUE})",
        re.IGNORECASE,
    ),
)

_URL_RE = re.compile(r"https?://[^\s)\]>\"'”’]+", re.IGNORECASE)
_DOMAIN_PATH_RE = re.compile(
    r"\b((?:[a-z0-9-]+\.)+(?:com|es|org|net|edu|gob|gov))"
    r"(/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
    re.IGNORECASE,
)
_VERIFIER_HINT_RE = re.compile(r"verif|csv|valida", re.IGNORECASE)

# Bare domains that host issuer verification portals (no scheme printed).
_KNOWN_VERIFIER_DOMAINS = (
    "go.oup.com",
    "cambridgeenglish.org",
    "seu.uv.es",
    "tramita.gva.es",
    "trinitycert.com",
    "ielts.org",
    "toefl.org",
)


@dataclass
class VerificationArtifacts:
    code: str = ""
    url: str = ""
    evidence: dict[str, Any] | None = None

    @property
    def found(self) -> bool:
        return bool(self.code or self.url)


def _clean_url(url: str) -> str:
    url = url.strip().rstrip(".,;:)")
    return url[:MAX_URL_LENGTH]


def _looks_like_verifier_url(url: str) -> bool:
    return bool(_VERIFIER_HINT_RE.search(url))


def _find_code(page_texts: dict[int, str]) -> tuple[str, str]:
    """Return (code, matched_line). First pattern hit wins."""
    for page_number in sorted(page_texts):
        text = page_texts[page_number] or ""
        for pattern in _CODE_PATTERNS:
            match = pattern.search(text)
            if match:
                code = match.group(1).strip().rstrip(".,;")
                line = text[max(0, match.start() - 40) : match.end() + 40]
                return code, " ".join(line.split())
    return "", ""


def _find_url(page_texts: dict[int, str]) -> tuple[str, str]:
    """Return (url, matched_line).

    Preference order: labeled verifier URL, https URL on a line that
    mentions verification/csv, bare known verifier domain.
    """
    labeled_re = re.compile(
        r"(?:url\s+verif|verify\s+at|verifica(?:r|ció)\s+en|en)"
        r"[\s:–—-]*(https?://[^\s)\]>\"'”’]+)",
        re.IGNORECASE,
    )
    for page_number in sorted(page_texts):
        text = page_texts[page_number] or ""
        match = labeled_re.search(text)
        if match:
            return _clean_url(match.group(1)), " ".join(
                text[max(0, match.start() - 40) : match.end() + 40].split()
            )
    for page_number in sorted(page_texts):
        text = page_texts[page_number] or ""
        for line in text.splitlines():
            if not _VERIFIER_HINT_RE.search(line):
                continue
            match = _URL_RE.search(line)
            if match:
                return _clean_url(match.group(0)), " ".join(line.split())[:300]
    for page_number in sorted(page_texts):
        text = page_texts[page_number] or ""
        for domain in _KNOWN_VERIFIER_DOMAINS:
            idx = text.lower().find(domain)
            if idx == -1:
                continue
            tail = _DOMAIN_PATH_RE.search(text[idx:])
            if tail:
                raw = tail.group(0).strip().rstrip(".,;)")
                if raw.lower().startswith(domain):
                    return _clean_url(f"https://{raw}"), " ".join(
                        text[max(0, idx - 40) : idx + len(raw) + 40].split()
                    )[:300]
    return "", ""


# Issuer document identifier printed next to the verification code
# (e.g. UV "Id: UV-REDFirma-4751635" + "Cod. Verificació: ...").
_DOC_ID_RE = re.compile(r"\bId:\s*(UV-[A-Za-z]+-[A-Za-z0-9]+)\b")


def _find_document_id(page_texts: dict[int, str]) -> str:
    for page_number in sorted(page_texts):
        text = page_texts[page_number] or ""
        match = _DOC_ID_RE.search(text)
        if match:
            return match.group(1)
    return ""


def harvest_verification(page_texts: dict[int, str]) -> VerificationArtifacts:
    """Extract verification code/URL from page texts (deterministic)."""
    code, code_line = _find_code(page_texts)
    url, url_line = _find_url(page_texts)
    document_id = _find_document_id(page_texts)
    if not (code or url):
        return VerificationArtifacts()
    evidence = {
        "code_line": code_line or None,
        "url_line": url_line or None,
    }
    if document_id:
        evidence["document_id"] = document_id
    return VerificationArtifacts(code=code, url=url, evidence=evidence)


def apply_verification_artifacts(
    certificate: Certificate, page_texts: dict[int, str]
) -> Certificate:
    """Store harvested artifacts on the certificate and set status.

    A ``manually_confirmed`` status is preserved across re-extraction —
    the reviewer's confirmation is not silently reverted.
    """
    artifacts = harvest_verification(page_texts)
    certificate.verification_code = artifacts.code
    certificate.verification_url = artifacts.url
    evidence = dict(certificate.verification_evidence or {})
    if artifacts.evidence:
        harvest_evidence = dict(artifacts.evidence)
        document_id = harvest_evidence.pop("document_id", None)
        evidence["harvest"] = harvest_evidence
        if document_id:
            evidence["document_id"] = document_id
    certificate.verification_evidence = evidence
    if certificate.verification_status == Certificate.VerificationStatus.MANUALLY_CONFIRMED:
        pass
    elif artifacts.found:
        certificate.verification_status = Certificate.VerificationStatus.SELF_REPORTED
    else:
        certificate.verification_status = Certificate.VerificationStatus.NONE
        certificate.verified_by = None
        certificate.verified_at = None
    certificate.save(
        update_fields=[
            "verification_code",
            "verification_url",
            "verification_status",
            "verified_by",
            "verified_at",
            "verification_evidence",
            "updated_at",
        ]
    )
    return certificate


def verification_url_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
