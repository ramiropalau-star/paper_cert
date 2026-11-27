"""Deterministic candidate pre-pass for profile-guided extraction.

Scans page texts for label-value pairs, score candidates, and date
candidates *before* the model call. Candidates are injected into the prompt
as hints the model must validate with verbatim evidence; afterwards,
``apply_candidates`` fills still-empty fields only when the stored quote
verifies against the cited page, marking them unverified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _extraction():
    """Lazy import to avoid a circular dependency with extraction.py."""
    from documents.services import extraction

    return extraction


MAX_VALUE_LEN = 120
MAX_DATE_CANDIDATES = 10

# Conservative builtin label vocabulary per extraction field. Alias-map
# entries are added on top at scan time.
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "student_name": (
        "student name",
        "candidate name",
        "test taker",
        "obtained by",
        "obtenido por",
        "obtingut per",
        "nombre del estudiante",
        "nombre del alumno",
        "nom i cognoms",
        "nom et prenom",
        "nom du candidat",
    ),
    "language": ("language", "idioma", "llengua", "langue", "sprache", "lingua"),
    "entity": (
        "entity",
        "entidad",
        "entite",
        "organisme",
        "issuer",
        "certifying body",
        "emisor",
    ),
    "issuing_body": (
        "issued by",
        "organisme issuer",
        "organismo emisor",
        "entidad emisora",
        "emisor",
    ),
    "test_center": (
        "test center",
        "test centre",
        "centro de examen",
        "centre d'examen",
        "centro examinador",
    ),
    "exam": ("exam", "examen", "examination", "prova", "certification", "titulo"),
    "level": ("level", "nivel", "niveau", "cefr"),
    "score": (
        "score",
        "puntuacio",
        "nota",
        "qualificacio",
        "calificacion",
        "grade",
        "result",
        "marks",
    ),
    "certificate_code": (
        "certificate code",
        "certificate number",
        "certificado",
        "code",
        "reference",
        "referencia",
        "numero de certificado",
    ),
}

_LABEL_SEPARATORS = " \t:;.-–—·|"
_VALUE_STOP_TOKENS = ("http", "www.", "@")


@dataclass(frozen=True)
class Candidate:
    """A deterministic extraction candidate with its verbatim source quote."""

    field: str
    value: str
    page: int
    quote: str
    kind: str = "label_value"  # label_value | score | date
    role: str = ""  # date role when kind == "date"


@dataclass
class CandidateSet:
    fields: dict[str, Candidate] = field(default_factory=dict)
    dates: list[Candidate] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.fields or self.dates)


def _fold(text: str) -> str:
    return _extraction()._alias_fold(text)


def _label_re(label: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(_fold(label)) + r"(?!\w)")


def _clean_value(raw: str) -> str:
    return " ".join(raw.split()).strip(_LABEL_SEPARATORS)


def _plausible_value(value: str) -> bool:
    if not value or len(value) > MAX_VALUE_LEN:
        return False
    folded = _fold(value)
    return not any(token in folded for token in _VALUE_STOP_TOKENS)


def _line_value(page_text: str, line_index: int, col: int, label_len: int) -> str | None:
    """Value after a label: same-line tail, else next non-empty line."""
    lines = page_text.splitlines()
    line = lines[line_index]
    tail = _clean_value(line[col + label_len :])
    if _plausible_value(tail):
        return tail
    for follow in lines[line_index + 1 : line_index + 4]:
        follow = follow.strip()
        if not follow:
            continue
        candidate = _clean_value(follow)
        if _plausible_value(candidate):
            return candidate
        return None
    return None


def _scan_label_value(
    page_texts: dict[int, str],
    field_name: str,
    labels: tuple[str, ...],
) -> Candidate | None:
    patterns = [_label_re(label) for label in labels if label.strip()]
    if not patterns:
        return None
    for page_number in sorted(page_texts):
        text = page_texts[page_number]
        folded_lines = [_fold(line) for line in text.splitlines()]
        raw_lines = text.splitlines()
        for index, folded in enumerate(folded_lines):
            best_col = -1
            best_len = 0
            for pattern in patterns:
                match = pattern.search(folded)
                if match and (best_col < 0 or match.start() < best_col):
                    best_col = match.start()
                    best_len = len(match.group(0))
            if best_col < 0:
                continue
            value = _line_value(text, index, best_col, best_len)
            if value is None:
                continue
            quote = raw_lines[index].strip()
            return Candidate(
                field=field_name,
                value=value,
                page=page_number,
                quote=quote or value,
            )
    return None


def _scan_scores(page_texts: dict[int, str]) -> Candidate | None:
    ext = _extraction()
    _SCORE_LABEL_RE = ext._SCORE_LABEL_RE
    _SCORE_OVER_RE = ext._SCORE_OVER_RE
    _SCORE_OVERALL_RE = ext._SCORE_OVERALL_RE
    _SCORE_TRAIL_RE = ext._SCORE_TRAIL_RE
    _line_for = ext._line_for

    for page_number in sorted(page_texts):
        text = page_texts[page_number]
        for pattern in (_SCORE_OVER_RE, _SCORE_OVERALL_RE, _SCORE_TRAIL_RE, _SCORE_LABEL_RE):
            match = pattern.search(text)
            if match is None:
                continue
            value = match.group(0) if pattern is _SCORE_OVER_RE else match.group(1)
            value = " ".join(value.split()).strip()
            if not _plausible_value(value):
                continue
            return Candidate(
                field="score",
                value=value,
                page=page_number,
                quote=_line_for(text, match.start(), match.end()),
                kind="score",
            )
    return None


def _scan_dates(page_texts: dict[int, str]) -> list[Candidate]:
    ext = _extraction()
    _DATE_VALUE_RE = ext._DATE_VALUE_RE
    _HARVEST_NUMERIC_RES = ext._HARVEST_NUMERIC_RES
    _harvest_role = ext._harvest_role
    _line_for = ext._line_for
    from documents.services.months import (
        DAY_MONTH_YEAR_RE,
        MONTH_DAY_YEAR_RE,
        MONTH_YEAR_RE,
    )

    candidates: list[Candidate] = []
    seen: set[tuple[int, str]] = set()
    for page_number in sorted(page_texts):
        text = page_texts[page_number]
        matches: list[tuple[int, int, str]] = []
        for pattern in (*_HARVEST_NUMERIC_RES, _DATE_VALUE_RE):
            for match in pattern.finditer(text):
                matches.append((match.start(), match.end(), match.group(0)))
        for pattern in (DAY_MONTH_YEAR_RE, MONTH_DAY_YEAR_RE, MONTH_YEAR_RE):
            for match in pattern.finditer(text):
                matches.append((match.start(), match.end(), match.group(0)))
        for start, end, value in sorted(matches):
            if len(candidates) >= MAX_DATE_CANDIDATES:
                return candidates
            value = value.strip(" .,;")
            key = (page_number, _fold(value))
            if key in seen or not _plausible_value(value):
                continue
            seen.add(key)
            candidates.append(
                Candidate(
                    field="dates",
                    value=value,
                    page=page_number,
                    quote=_line_for(text, start, end),
                    kind="date",
                    role=_harvest_role(text, start),
                )
            )
    return candidates


def extract_candidates(page_texts: dict[int, str], alias_map: dict[str, list[str]]) -> CandidateSet:
    """Run the deterministic pre-pass over page texts."""
    result = CandidateSet()
    for field_name in _extraction().LITERAL_FIELDS:
        labels = _FIELD_LABELS.get(field_name, ()) + tuple(alias_map.get(field_name, ()))
        candidate = _scan_label_value(page_texts, field_name, labels)
        if candidate is not None:
            result.fields[field_name] = candidate
    score = _scan_scores(page_texts)
    if score is not None:
        result.fields["score"] = score
    result.dates = _scan_dates(page_texts)
    return result


def candidates_hint(candidates: CandidateSet) -> str:
    """Render candidates as a prompt section for the model to validate."""
    if not candidates:
        return ""
    lines = [
        "Deterministic candidates found in the document (validate each "
        "against the text; keep a value only with a verbatim quote):"
    ]
    for name, candidate in sorted(candidates.fields.items()):
        lines.append(f"  - {name}: {candidate.value!r} (page {candidate.page})")
    for candidate in candidates.dates[:MAX_DATE_CANDIDATES]:
        role = f", role: {candidate.role}" if candidate.role else ""
        lines.append(f"  - date: {candidate.value!r} (page {candidate.page}{role})")
    return "\n".join(lines) + "\n\n"


def _quote_verifies(quote: str, page_text: str) -> bool:
    return _extraction()._quote_in_page(quote, page_text)


def apply_candidates(
    payload,  # ExtractionPayload
    candidates: CandidateSet,
    page_texts: dict[int, str],
) -> set[str]:
    """Fill empty payload fields from verified candidates.

    A candidate is applied only when its stored quote appears verbatim on
    the cited page; applied values carry low confidence and are reported in
    the returned set so the caller marks them unverified. Date candidates
    are appended to ``payload.dates`` when not already present.
    """
    ext = _extraction()
    unverified: set[str] = set()
    for name, candidate in candidates.fields.items():
        attribute = _extraction().LITERAL_FIELDS.get(name)
        if attribute is None:
            continue
        target = getattr(payload, name, None)
        if target is None or (target.value or "").strip():
            continue
        page_text = page_texts.get(candidate.page, "")
        if not _quote_verifies(candidate.quote, page_text):
            continue
        setattr(
            payload,
            name,
            ext.FieldValue(
                value=candidate.value,
                evidence=ext.FieldEvidence(page=candidate.page, quote=candidate.quote),
                confidence=0.4,
            ),
        )
        unverified.add(attribute)

    known = {candidate.text for candidate in payload.dates}
    for candidate in candidates.dates:
        page_text = page_texts.get(candidate.page, "")
        if not _quote_verifies(candidate.quote, page_text):
            continue
        if candidate.value in known:
            continue
        payload.dates.append(
            _extraction().DateCandidate(
                text=candidate.value,
                role=candidate.role or "unknown",  # type: ignore[arg-type]
                page=candidate.page,
                quote=candidate.quote,
            )
        )
        known.add(candidate.value)
    return unverified
