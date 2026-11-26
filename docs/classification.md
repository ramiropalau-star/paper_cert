# Classification and normalization

Classification maps the literal values extracted from a certificate to the
editable catalog. It never guesses: matching is exact after Unicode
normalization (NFKC, casefold, whitespace collapse), and unknown values stay
literal and unresolved.

## Catalog

Master data is managed in Django admin (admin role), and equivalences also
have an in-app UI at `/catalog/` for reviewers:

- **Languages** and **Language aliases** — certified language.
- **Entities** and **Entity aliases** — certifying bodies, including the
  `date_order` used to disambiguate numeric dates.
- **Exams** and **Exam aliases** — linked to an entity and optionally a
  language.
- **Equivalences** — accredited CEFR level per exam (optionally score-banded);
  browsable and editable at `/catalog/`, which can also create an entity +
  exam + aliases + equivalences in one form.
- **CEFR conversion rules** — score range → CEFR level per exam.
- **Format profiles** — learned per-entity format signatures rebuilt from
  approved certificates; see `docs/review.md`.

Adding an entity, alias, or exam takes effect on the next classification
run (reprocess the document); no code change or redeploy is needed.
Approving or validating a certificate also learns catalog entries
(aliases, missing exams, equivalences, CEFR candidates) — see
`docs/review.md` "Learning from review".

## Matching rules

- Language and entity literals are normalized and matched exactly against
  aliases first, then catalog names. Near-matches never resolve.
- Exam literals match exam names exactly; when the entity is resolved, only
  that entity's exams are considered.
- Literal printed text is always kept (`language_literal`,
  `entity_literal`, `exam_literal`, `level_literal`, `score_literal`) next
  to the resolved catalog foreign keys.
- Entity roles stay distinct: `entity` is the certifying/examining entity;
  `issuing_body_literal` and `test_center_literal` remain literal-only and
  are never invented from a single organization name.

## Unknown entities

An entity literal that matches nothing stays unresolved
(`entity = NULL`) and the record is routed to review with the
`unknown_entity` reason, displayed as **"Entidad pendiente de
identificar"**. The reviewer can fix the literal or extend the catalog and
reprocess. The same applies to unknown languages (`unknown_language`).

## CEFR levels

`cefr_level` is set only by:

1. **Explicit** — a CEFR token (A1–C2) printed in the level text
   (`cefr_source = explicit`).
2. **Approved rule** — an active `CefrConversionRule` for the resolved exam
   whose score range contains the literal score
   (`cefr_source = approved_rule`).

Rules without approval metadata or with `is_active = False` never apply
(see the guardrails enforced by `CefrConversionRule.clean`). Scores are
never converted across exams.

## Dates

Extraction returns date candidates `{text, role, page, quote}` where `text`
should contain only the date value. Each text is parsed with explicit
formats plus `dateutil` (which is only trusted when the text carries both a
day and a year — month-year strings like "SEPTEMBER 2020" are never
fabricated into a full date). Results are stored as `YYYY-MM-DD` in
`issue_date`, `exam_date`, `result_date`, or `detected_date`. Original
wording is retained in `date_texts["originals"]`.

- Candidates that embed a date inside a label (e.g. "Date of Issue:
  05/12/2020") have the date token extracted before parsing.
- `role = unknown`, ambiguous day/month order, or unparseable text →
  `detected_date` and the `ambiguous_date` review reason.
- Ambiguous numeric dates (e.g. `05/06/2024`) are disambiguated by the
  resolved entity's `date_order` field (`dmy` or `mdy`, seeded per
  catalog entity — `dmy` for European bodies, `mdy` for ETS/TOEIC/
  Duolingo/Michigan). Entities without `date_order` keep the date in
  `detected_date` for review.
- The first parseable candidate per field wins.

## Review reasons

Classification writes these codes to `certificate.review_reasons`:

| Code | Meaning |
| --- | --- |
| `missing_essential_fields` | student, language, entity, level/score, or issue date absent |
| `unknown_language` | language literal not in catalog |
| `unknown_entity` | entity literal not in catalog ("Entidad pendiente de identificar") |
| `ambiguous_date` | date role or day/month order uncertain |
| `low_confidence` | overall confidence below `APP_CONFIDENCE_REVIEW_THRESHOLD` |
| `multiple_certificates` | file appears to contain several certificates |
| `non_certificate` | document is not a language certificate |
| `equivalence_not_found` | exam resolved but no UV L2 equivalence rule applies |
| `format_mismatch` | document text does not match the issuer's known format profile |

Pipeline-stage failures (`ocr_failed`, `insufficient_text`,
`low_ocr_confidence`, `original_unavailable`, `model_unavailable`,
`invalid_extraction`, `recovery_attempts_exhausted`, and similar) are
also surfaced as review reasons with operator-readable labels; the full
code-to-label mapping lives in `documents/review_display.py`.

## `Otros` label

Documents whose language or entity cannot be resolved, that are not
language certificates, or whose processing fails get the configured
Paperless label (`APP_PAPERLESS_OTHER_TAG`, default `Otros`) while staying
in the review queue. The label is removed when a reviewer approves the
record. Label failures never block processing.

## UV L2 equivalence

The catalog includes `Equivalence` rows transcribed from the UV "Taula
d'Equivalències L2" (source `UV L2`), extracted from the published PDF by
page coordinates, that map an exam — optionally within a score band — to
its accredited CEFR level. Coverage spans the English, Spanish, German,
French, Italian, Portuguese, Russian, and Chinese sections of the table,
including score-banded exams (BULATS, IELTS, PTE, TOEFL, TOEIC, TCF,
esPro, Oxford Test of English) and level-named exams across all
languages. Exams still without equivalence (EOI school certificates,
SIELE, TEF score variants, DSD dual-level, LCCIEB/ELSA granular tests)
route to review for manual assignment. After CEFR resolution,
`apply_equivalence` stores the accredited level in
`certificate.equivalence`:

- Score-banded rules win when `score_literal` parses to a number inside the
  band; unbanded rules act as a fallback for level-named exams.
- An exam with no matching equivalence leaves `equivalence` empty and adds
  the `equivalence_not_found` review reason, keeping the record in the
  review queue.
- Reviewers can override the value manually; edits are audited like any
  other field and appear in the report column "Equivalencia UV L2".
