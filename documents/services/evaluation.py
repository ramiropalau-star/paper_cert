"""Offline extraction evaluation: golden sets, dry runs, metrics, baselines.

The harness measures extraction quality without touching live data: golden
cases snapshot the source text and human-confirmed fields of approved or
validated certificates, dry runs go through the same model path as
production but persist nothing, and baseline comparison only reports — it
never deploys or activates anything.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone as dj_timezone

from catalog.models import FormatProfile
from documents.models import (
    Certificate,
    EvaluationCase,
    EvaluationRun,
)
from documents.services.classification import DATE_FIELD_BY_ROLE, parse_date_text
from documents.services.extraction import (
    LITERAL_FIELDS,
    PROMPT_VERSION,
    ModelExtraction,
    _norm_text,
    _quote_in_page,
    document_text,
    run_model_extraction,
)
from documents.services.field_aliases import _aliases_for_entity
from documents.services.ollama import OllamaClient, build_ollama_client

logger = logging.getLogger(__name__)

GOLDEN_SET_NAME = "default"
LEARNED_REVIEW_STATUSES = (
    Certificate.ReviewStatus.APPROVED,
    Certificate.ReviewStatus.VALIDATED,
)
MAX_VERSION_HISTORY = 20

# Canonical fields compared between golden expectations and dry-run output.
EVALUATED_FIELDS = (
    "student_name",
    "language_literal",
    "entity_literal",
    "issuing_body_literal",
    "test_center_literal",
    "exam_literal",
    "level_literal",
    "score_literal",
    "certificate_code",
    "issue_date",
    "exam_date",
    "result_date",
    "detected_date",
    "is_language_certificate",
)

_PAGE_MARKER_RE = re.compile(r"^--- Page (\d+) ---\s*$", re.MULTILINE)


def _tolerance() -> float:
    return float(settings.APP.get("eval_regression_tolerance", 0.02))


def _code_revision() -> str:
    return str(settings.APP.get("code_revision", ""))


def pages_from_source_text(source_text: str) -> dict[int, str]:
    """Rebuild ``{page_number: text}`` from ``document_text`` output."""
    pages: dict[int, str] = {}
    matches = list(_PAGE_MARKER_RE.finditer(source_text or ""))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        pages[int(match.group(1))] = source_text[start:end].strip()
    if not pages and (source_text or "").strip():
        pages[1] = source_text
    return pages


def _expected_from_certificate(certificate: Certificate) -> dict[str, Any]:
    expected: dict[str, Any] = {}
    for attribute in EVALUATED_FIELDS:
        if attribute == "is_language_certificate":
            expected[attribute] = certificate.is_language_certificate
            continue
        value = getattr(certificate, attribute, None)
        if isinstance(value, date):
            expected[attribute] = value.isoformat()
        else:
            expected[attribute] = "" if value is None else str(value).strip()
    return expected


def _profile_version_for(certificate: Certificate) -> int | None:
    if certificate.entity_id is None:
        return None
    year = None
    for field_name in ("issue_date", "exam_date", "detected_date"):
        value = getattr(certificate, field_name, None)
        if value is not None:
            year = value.year
            break
    if year is None:
        return None
    profile = (
        FormatProfile.objects.filter(
            entity_id=certificate.entity_id,
            exam_id=certificate.exam_id,
            year=year,
            is_active=True,
        )
        .order_by("-version")
        .first()
    )
    if profile is None:
        profile = (
            FormatProfile.objects.filter(
                entity_id=certificate.entity_id, exam__isnull=True, year=year, is_active=True
            )
            .order_by("-version")
            .first()
        )
    return profile.version if profile is not None else None


def build_golden_set(
    *,
    set_name: str = GOLDEN_SET_NAME,
    actor=None,
) -> dict[str, Any]:
    """Create a new immutable golden-set version from confirmed certificates.

    Approved and validated certificates contribute their stored, human-
    reviewed fields as expectations. Rejected or pending documents are never
    included, and a new version never mutates earlier versions.
    """
    latest = (
        EvaluationCase.objects.filter(set_name=set_name)
        .order_by("-set_version")
        .values_list("set_version", flat=True)
        .first()
    )
    version = (latest or 0) + 1
    certificates = (
        Certificate.objects.filter(review_status__in=LEARNED_REVIEW_STATUSES)
        .select_related("document", "entity", "exam")
        .order_by("pk")
    )
    cases: list[EvaluationCase] = []
    skipped = 0
    for certificate in certificates:
        text = document_text(certificate.document)
        if not text.strip():
            skipped += 1
            continue
        cases.append(
            EvaluationCase(
                set_name=set_name,
                set_version=version,
                certificate=certificate,
                entity=certificate.entity,
                exam=certificate.exam,
                profile_version=_profile_version_for(certificate),
                source_text=text,
                expected=_expected_from_certificate(certificate),
                evidence=dict(certificate.evidence or {}),
                context={
                    "prompt_version": certificate.prompt_version or "",
                    "review_status": certificate.review_status,
                },
            )
        )
    with transaction.atomic():
        EvaluationCase.objects.bulk_create(cases, batch_size=200)
    return {
        "set_name": set_name,
        "set_version": version,
        "cases": len(cases),
        "skipped": skipped,
        "actor": getattr(actor, "username", "") if actor else "",
    }


def latest_golden_set(set_name: str = GOLDEN_SET_NAME) -> tuple[int, int] | None:
    """Return (set_version, case_count) of the newest version, or None."""
    row = (
        EvaluationCase.objects.filter(set_name=set_name)
        .values("set_version")
        .annotate(count=Count("pk"))
        .order_by("-set_version")
        .first()
    )
    if row is None:
        return None
    return row["set_version"], row["count"]


def _actual_from_payload(
    payload, page_texts: dict[int, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map a dry-run payload to evaluated fields plus evidence stats."""
    actual: dict[str, Any] = {}
    for name, attribute in LITERAL_FIELDS.items():
        field = getattr(payload, name)
        actual[attribute] = (field.value or "").strip()
    actual["is_language_certificate"] = payload.is_language_certificate

    dates: dict[str, str] = {}
    for candidate in payload.dates:
        parsed, _ambiguous = parse_date_text(candidate.text)
        role = candidate.role if candidate.role in DATE_FIELD_BY_ROLE else "unknown"
        field_name = DATE_FIELD_BY_ROLE.get(role, "detected_date")
        if field_name in dates:
            continue
        if parsed is not None:
            dates[field_name] = parsed.isoformat()
        elif role == "unknown" and _looks_like_eval_date(candidate.text):
            dates[field_name] = candidate.text.strip()
    for name in ("issue_date", "exam_date", "result_date", "detected_date"):
        actual[name] = dates.get(name, "")
    return actual, {"dates": dates}


def _looks_like_eval_date(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


def _field_comparison(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, dict]:
    """Per-field exact/normalized accuracy, missing and fabricated counts."""
    results: dict[str, dict] = {}
    for name in EVALUATED_FIELDS:
        exp = expected.get(name)
        act = actual.get(name)
        exp_empty = exp is None or exp == "" or exp is False
        act_empty = act is None or act == "" or act is False
        exact = False
        normalized = False
        if not exp_empty and not act_empty:
            exact = str(exp).strip() == str(act).strip()
            normalized = _norm_text(str(exp)) == _norm_text(str(act))
        results[name] = {
            "expected": exp,
            "actual": act,
            "exact": exact,
            "normalized": normalized,
            "missing": bool(not exp_empty and act_empty),
            "fabricated": bool(exp_empty and not act_empty),
            "expected_present": not exp_empty,
            "actual_present": not act_empty,
        }
    return results


def _evidence_stats(payload, page_texts: dict[int, str]) -> dict[str, int]:
    """Count evidence quotes that verify against the cited page."""
    valid = 0
    total = 0
    for name in LITERAL_FIELDS:
        field = getattr(payload, name)
        if field.evidence is None or not (field.value or "").strip():
            continue
        total += 1
        page_text = page_texts.get(field.evidence.page)
        if page_text is not None and _quote_in_page(field.evidence.quote, page_text):
            valid += 1
    for candidate in payload.dates:
        if candidate.page is None or not candidate.quote:
            continue
        total += 1
        page_text = page_texts.get(candidate.page)
        if page_text is not None and _quote_in_page(candidate.quote, page_text):
            valid += 1
    return {"valid": valid, "total": total}


def _aggregate_case(
    case: EvaluationCase, result: dict[str, Any], bucket: dict[str, dict[str, Any]]
) -> None:
    """Fold one case's field comparison into an aggregate bucket."""
    agg = bucket.setdefault(
        "_fields",
        {
            name: {"exact": 0, "normalized": 0, "expected": 0, "missing": 0, "fabricated": 0}
            for name in EVALUATED_FIELDS
        },
    )
    for name, comp in result["fields"].items():
        entry = agg[name]
        if not comp["expected_present"]:
            if comp["fabricated"]:
                entry["fabricated"] += 1
            continue
        entry["expected"] += 1
        if comp["exact"]:
            entry["exact"] += 1
        if comp["normalized"]:
            entry["normalized"] += 1
        if comp["missing"]:
            entry["missing"] += 1
        if comp["fabricated"]:
            entry["fabricated"] += 1


def _finish_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    fields = bucket.pop("_fields", {})
    out: dict[str, Any] = dict(bucket)
    per_field: dict[str, Any] = {}
    totals = {"exact": 0, "normalized": 0, "expected": 0, "missing": 0, "fabricated": 0}
    for name, entry in fields.items():
        expected = entry["expected"]
        per_field[name] = {
            "expected": expected,
            "exact_correct": entry["exact"],
            "normalized_correct": entry["normalized"],
            "exact_accuracy": round(entry["exact"] / expected, 4) if expected else None,
            "normalized_accuracy": (round(entry["normalized"] / expected, 4) if expected else None),
            "missing": entry["missing"],
            "missing_rate": round(entry["missing"] / expected, 4) if expected else None,
            "fabricated": entry["fabricated"],
        }
        for key in totals:
            totals[key] += entry[key]
    out["fields"] = per_field
    expected_total = totals["expected"]
    out["totals"] = {
        **totals,
        "exact_accuracy": round(totals["exact"] / expected_total, 4) if expected_total else None,
        "normalized_accuracy": (
            round(totals["normalized"] / expected_total, 4) if expected_total else None
        ),
        "missing_rate": round(totals["missing"] / expected_total, 4) if expected_total else None,
        "fabricated_rate": (
            round(totals["fabricated"] / max(1, totals["exact"] + totals["normalized"]), 4)
            if expected_total
            else None
        ),
    }
    return out


def _new_bucket() -> dict[str, Any]:
    return {
        "cases": 0,
        "schema_valid": 0,
        "evidence_valid": 0,
        "evidence_total": 0,
        "latency_total_ms": 0.0,
        "latencies": [],
    }


def _accumulate(bucket: dict[str, Any], case_result: dict[str, Any]) -> None:
    bucket["cases"] += 1
    if case_result.get("schema_valid"):
        bucket["schema_valid"] += 1
    bucket["evidence_valid"] += case_result["evidence"]["valid"]
    bucket["evidence_total"] += case_result["evidence"]["total"]
    bucket["latency_total_ms"] += case_result["latency_ms"]
    bucket["latencies"].append(case_result["latency_ms"])
    _aggregate_case(None, case_result, bucket)


def _finalize(bucket: dict[str, Any]) -> dict[str, Any]:
    latencies = sorted(bucket.pop("latencies", []))
    out = _finish_bucket(bucket)
    count = max(1, out["cases"])
    out["schema_validity"] = round(out["schema_valid"] / count, 4) if out["cases"] else None
    out["evidence_validity"] = (
        round(out["evidence_valid"] / out["evidence_total"], 4) if out["evidence_total"] else None
    )
    out["latency"] = {
        "total_ms": round(out.pop("latency_total_ms"), 1),
        "mean_ms": round(sum(latencies) / count, 1) if latencies else None,
        "p95_ms": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        if latencies
        else None,
    }
    out.pop("schema_valid", None)
    out.pop("evidence_valid", None)
    out.pop("evidence_total", None)
    return out


def _empty_metrics() -> dict[str, Any]:
    return {"overall": _new_bucket(), "by_entity": {}, "by_exam": {}}


def _group_key(case: EvaluationCase, kind: str) -> str:
    if kind == "entity":
        return case.entity.name if case.entity_id else "unknown"
    return case.exam.name if case.exam_id else (case.entity.name if case.entity_id else "unknown")


def run_evaluation(
    run: EvaluationRun,
    *,
    llm: OllamaClient | None = None,
    entity_id: int | None = None,
) -> EvaluationRun:
    """Execute a dry-run evaluation. Persists only the run record."""
    cases = EvaluationCase.objects.filter(
        set_name=run.set_name, set_version=run.set_version
    ).select_related("entity", "exam")
    if entity_id is not None:
        cases = cases.filter(entity_id=entity_id)
    cases = list(cases)

    run.status = EvaluationRun.Status.RUNNING
    run.started_at = dj_timezone.now()
    run.save(update_fields=["status", "started_at"])

    owns_llm = llm is None
    selected_llm = llm or build_ollama_client()
    metrics = _empty_metrics()
    case_results: list[dict[str, Any]] = []
    try:
        for case in cases:
            started = time.monotonic()
            page_texts = pages_from_source_text(case.source_text)
            text = "\n\n".join(
                f"--- Page {number} ---\n{body}" for number, body in sorted(page_texts.items())
            )
            alias_map = _aliases_for_entity(case.entity_id)
            outcome: ModelExtraction = run_model_extraction(
                text, page_texts, alias_map, selected_llm
            )
            latency_ms = (time.monotonic() - started) * 1000
            result: dict[str, Any] = {
                "case_id": case.pk,
                "entity": _group_key(case, "entity"),
                "exam": _group_key(case, "exam"),
                "latency_ms": round(latency_ms, 1),
                "schema_valid": outcome.payload is not None,
                "error": outcome.error,
            }
            if outcome.payload is not None:
                actual, _extra = _actual_from_payload(outcome.payload, page_texts)
                result["fields"] = _field_comparison(case.expected or {}, actual)
                result["evidence"] = _evidence_stats(outcome.payload, page_texts)
            else:
                result["fields"] = _field_comparison(
                    case.expected or {}, {name: "" for name in EVALUATED_FIELDS}
                )
                result["evidence"] = {"valid": 0, "total": 0}
            case_results.append(result)

            _accumulate(metrics["overall"], result)
            for kind, group in (("entity", "by_entity"), ("exam", "by_exam")):
                key = _group_key(case, kind)
                bucket = metrics[group].setdefault(key, _new_bucket())
                _accumulate(bucket, result)

        run.metrics = {
            "overall": _finalize(metrics["overall"]),
            "by_entity": {key: _finalize(bucket) for key, bucket in metrics["by_entity"].items()},
            "by_exam": {key: _finalize(bucket) for key, bucket in metrics["by_exam"].items()},
            "cases": case_results,
            "case_count": len(case_results),
        }
        run.status = EvaluationRun.Status.COMPLETED
        run.finished_at = dj_timezone.now()
        run.error = ""
    except Exception as exc:  # noqa: BLE001 - run record must capture failures
        logger.exception("Evaluation run %s failed", run.pk)
        run.status = EvaluationRun.Status.FAILED
        run.error = str(exc)[:2000]
        run.finished_at = dj_timezone.now()
    finally:
        if owns_llm:
            selected_llm.close()
    run.save()
    return run


def compare_metrics(
    baseline: dict[str, Any], current: dict[str, Any], *, tolerance: float | None = None
) -> dict[str, Any]:
    """Compare per-field normalized accuracy between two run metrics."""
    tol = _tolerance() if tolerance is None else tolerance
    base_fields = (baseline.get("overall") or {}).get("fields") or {}
    curr_fields = (current.get("overall") or {}).get("fields") or {}
    names = sorted(set(base_fields) | set(curr_fields))
    fields_out: dict[str, Any] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    for name in names:
        base = (base_fields.get(name) or {}).get("normalized_accuracy")
        curr = (curr_fields.get(name) or {}).get("normalized_accuracy")
        if base is None or curr is None:
            continue
        delta = round(curr - base, 4)
        if delta < -tol:
            status = "regression"
            regressions.append(name)
        elif delta > tol:
            status = "improvement"
            improvements.append(name)
        else:
            status = "same"
        fields_out[name] = {
            "baseline": base,
            "current": curr,
            "delta": delta,
            "status": status,
        }
    base_totals = (baseline.get("overall") or {}).get("totals") or {}
    curr_totals = (current.get("overall") or {}).get("totals") or {}
    return {
        "tolerance": tol,
        "fields": fields_out,
        "regressions": regressions,
        "improvements": improvements,
        "totals": {
            "baseline_normalized_accuracy": base_totals.get("normalized_accuracy"),
            "current_normalized_accuracy": curr_totals.get("normalized_accuracy"),
        },
    }


def run_evaluation_with_baseline(
    run: EvaluationRun, *, baseline_run: EvaluationRun | None = None, **kwargs
) -> EvaluationRun:
    """Run an evaluation and compare it against a baseline run."""
    baseline = baseline_run or (
        EvaluationRun.objects.filter(status=EvaluationRun.Status.COMPLETED)
        .exclude(pk=run.pk)
        .order_by("-created_at")
        .first()
    )
    run = run_evaluation(run, **kwargs)
    if run.status == EvaluationRun.Status.COMPLETED and baseline is not None:
        run.baseline_run = baseline
        run.comparison = compare_metrics(baseline.metrics or {}, run.metrics or {})
        run.save(update_fields=["baseline_run", "comparison"])
    return run


def evaluation_config(run: EvaluationRun | None = None) -> dict[str, Any]:
    """Snapshot the configuration an evaluation run measures."""
    app = settings.APP
    return {
        "model": app.get("ollama_model", ""),
        "prompt_version": PROMPT_VERSION,
        "fallback_model": app.get("extraction_fallback_model", ""),
        "pre_detection_enabled": bool(app.get("pre_detection_enabled", True)),
        "code_revision": _code_revision(),
        **((run.config or {}) if run is not None else {}),
    }


def create_evaluation_run(
    *,
    set_name: str = GOLDEN_SET_NAME,
    set_version: int | None = None,
    actor=None,
    entity_id: int | None = None,
    baseline_run: EvaluationRun | None = None,
    config: dict[str, Any] | None = None,
) -> EvaluationRun:
    """Create (and immediately queue metadata for) an evaluation run record."""
    if set_version is None:
        latest = latest_golden_set(set_name)
        if latest is None:
            raise ValueError(f"No golden set '{set_name}' exists; build one first.")
        set_version = latest[0]
    merged = evaluation_config()
    merged.update(config or {})
    if entity_id is not None:
        merged["entity_id"] = entity_id
    run = EvaluationRun.objects.create(
        set_name=set_name,
        set_version=set_version,
        actor=actor,
        baseline_run=baseline_run,
        config=merged,
        code_revision=_code_revision(),
    )
    return run
