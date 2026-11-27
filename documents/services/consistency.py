"""Post-classification issuer consistency check and bounded re-extraction.

After classification resolves the catalog entity/exam, the resolved values
are compared with the deterministic pre-detection stored on the certificate.
A material mismatch records the ``entity_mismatch`` review reason and may
trigger at most one re-extraction with the resolved issuer's profile —
marked on the new ``ExtractionRun`` so it can never loop.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from documents.models import Certificate, Document, ExtractionRun
from documents.services.field_aliases import aliases_for_document
from documents.services.ollama import OllamaClient, build_ollama_client
from documents.services.profile_context import profile_context_for

logger = logging.getLogger(__name__)

RERUN_MARKER = "issuer_consistency"


def issuer_consistency(certificate: Certificate) -> dict[str, Any]:
    """Compare pre-detection with the resolved catalog values.

    Returns a JSON-safe dict stored under ``pre_detection["consistency"]``.
    Ambiguous or unmatched pre-detection never produces a mismatch.
    """
    pre = certificate.pre_detection or {}
    result: dict[str, Any] = {
        "pre_detected_entity_id": pre.get("entity_id"),
        "pre_detected_exam_id": pre.get("exam_id"),
        "resolved_entity_id": certificate.entity_id,
        "resolved_exam_id": certificate.exam_id,
        "entity_mismatch": False,
        "exam_mismatch": False,
        "rerun": ExtractionRun.objects.filter(
            document_id=certificate.document_id, fallback_used=RERUN_MARKER
        ).exists(),
    }
    if pre.get("result") != "match":
        return result
    pre_entity = pre.get("entity_id")
    if (
        pre_entity is not None
        and certificate.entity_id is not None
        and pre_entity != certificate.entity_id
    ):
        result["entity_mismatch"] = True
    pre_exam = pre.get("exam_id")
    if pre_exam is not None and certificate.exam_id is not None and pre_exam != certificate.exam_id:
        result["exam_mismatch"] = True
    return result


def consistency_reasons(certificate: Certificate) -> list[str]:
    """Fresh review reasons owned by the consistency check."""
    check = issuer_consistency(certificate)
    if check["entity_mismatch"] or check["exam_mismatch"]:
        return ["entity_mismatch"]
    return []


def record_consistency(certificate: Certificate) -> dict[str, Any]:
    """Store the comparison on the certificate's pre_detection payload."""
    check = issuer_consistency(certificate)
    pre = dict(certificate.pre_detection or {})
    pre["consistency"] = check
    certificate.pre_detection = pre
    return check


def rerun_with_resolved_profile(
    document: Document,
    certificate: Certificate,
    *,
    llm: OllamaClient | None = None,
) -> bool:
    """Re-run extraction once with the resolved issuer's profile.

    Bounded: skipped when a consistency re-run already exists for the
    document, when there is no resolved entity, or when the resolved issuer
    has no active profile. The new ``ExtractionRun`` carries the
    ``issuer_consistency`` marker in ``fallback_used``.
    """
    if ExtractionRun.objects.filter(document=document, fallback_used=RERUN_MARKER).exists():
        return False
    if certificate.entity_id is None:
        return False
    profile, profile_context = profile_context_for(certificate.entity_id, certificate.exam_id)
    if profile is None:
        return False

    # Lazy import: extraction imports classification, which imports this
    # module — a top-level import would be circular.
    from documents.services.extraction import (
        PROMPT_VERSION,
        _page_texts,
        _persist_certificate,
        document_text,
        run_model_extraction,
    )

    owns_llm = llm is None
    selected = llm or build_ollama_client()
    run = ExtractionRun.objects.create(
        document=document,
        certificate=certificate,
        fallback_used=RERUN_MARKER,
        profile=profile,
        profile_version=profile.version,
        pre_detection=certificate.pre_detection or {},
    )
    try:
        text = document_text(document)
        page_texts = _page_texts(document)
        alias_map = aliases_for_document(document)
        try:
            outcome = run_model_extraction(
                text, page_texts, alias_map, selected, profile_context=profile_context
            )
        except Exception as exc:  # noqa: BLE001 - record and keep primary result
            run.status = ExtractionRun.Status.FAILED
            run.error = str(exc)[:500]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            return False
        if outcome.error_code:
            run.status = ExtractionRun.Status.FAILED
            run.error = outcome.error
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            return False
        _persist_certificate(
            document,
            outcome.payload,
            outcome.unverified_fields,
            pre_detection=certificate.pre_detection or {},
            extraction_run=run,
        )
        run.status = ExtractionRun.Status.COMPLETED
        run.model = str(settings.APP.get("ollama_model", ""))
        run.prompt_version = PROMPT_VERSION
        run.pass_count = outcome.pass_count
        run.fallback_used = RERUN_MARKER
        run.latency_ms = outcome.latency_ms
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "model",
                "prompt_version",
                "pass_count",
                "fallback_used",
                "latency_ms",
                "finished_at",
            ]
        )
        return True
    finally:
        if owns_llm:
            selected.close()
