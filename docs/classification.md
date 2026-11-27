# Classification and normalization

Classification maps the literal values extracted from a certificate to the
editable catalog. It never guesses: matching is exact after Unicode
normalization (NFKC, casefold, whitespace collapse), and unknown values stay
literal and unresolved.

## Catalog

Master data is browsable in-app at `/catalog/` for every authenticated
user, with write controls for reviewers and admins:

Catalog UI pages:

- **Entity detail** (`/catalog/entities/<id>/`) — canonical name, active
  flag, `date_order`, aliases, exams (language + equivalences), per-exam
  equivalence add/update/deactivate, and exam creation.
- **Resolve** (`/catalog/resolve/`) — assigns an unresolved certificate
  literal to an existing entry or creates a new entity/exam from it; see
  `docs/review.md` "Catalog resolution".
- **Equivalence table** (`/catalog/`) — browses and edits equivalence
  rules, and can also create an entity + exam + aliases + equivalences in
  one form.

Catalog data:

- **Languages** and **Language aliases** — certified language.
- **Entities** and **Entity aliases** — certifying bodies, including the
  `date_order` used to disambiguate numeric dates.
- **Exams** and **Exam aliases** — linked to an entity and optionally a
  language.
- **Equivalences** — accredited CEFR level per exam (optionally score-banded).
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
identificar"**. The reviewer resolves it inline from the detail page
(catalog resolution, see `docs/review.md`) or fixes the literal and
reprocesses. The same applies to unknown languages (`unknown_language`).

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
| `entity_mismatch` | resolved entity/exam disagrees with issuer pre-detection |
| `source_mismatch` | source-document field comparison disagrees with extraction |

After resolving catalog references, classification runs a consistency
check (`documents/services/consistency.py`) comparing the resolved
entity/exam with the stored pre-detection result; a material mismatch adds
`entity_mismatch` and may trigger one bounded re-extraction with the
resolved issuer's profile (see `docs/extraction.md`). Source verification
(`verify_at_source`) can add `source_mismatch` when the issuer's returned
document disagrees with extracted fields.

Classification also computes the veracity score
(`documents/services/veracity.py`, flag `APP_VERACITY_ENABLED`) on every
classified certificate; it is a review aid only and never changes the
review state. See `docs/review.md` for the displayed breakdown.

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

## Format profile quality, drift, and versioning

Format profiles are rebuilt from approved/validated certificates by
`learn_format_profile` (on review approval) or manually with
`manage.py rebuild_format_profiles [--entity ID]`.

Each profile cohort `(entity, exam, year)` tracks:

- **Anchors** — corroborated boilerplate lines (`df` = distinct samples;
  `wdf` = verified-sample-weighted count used for ranking only). Layout
  anchors (`kind: "layout"`) capture recurring structural features —
  position-bucketed text lines and image regions such as logos — learned
  from per-page layout captured at ingestion. Lines that look like
  extracted metadata (lowercase `key: value` noise) are never anchor
  candidates.
- **Entity pool** — every approval also refreshes a `year=NULL` pool
  profile spanning all of the entity's approved samples, so anchors can
  emerge even when no single year reaches the sample threshold. Pool
  anchors must additionally appear in at least two distinct issuance
  years (unless the whole pool is single-year), keeping year-specific
  boilerplate out. Scoring prefers the most specific cohort: exam+year →
  entity+year → exam pool → entity pool → union of year cohorts.
- **Value shapes** — learned date order per date role, score/code shape,
  and level vocabulary (`value_shapes`).
- **Quality** — `anchor_precision`, `anchor_recall`, `anchor_churn`, and
  `sample_count`, measured on the cohort itself.
- **Drift** — `drift_detected`/`drift_detail` fire when the previous
  version's anchors are barely present in the most recent approved
  samples (below `APP_PROFILE_DRIFT_THRESHOLD`).
- **Versioning** — `version` bumps whenever anchors or value shapes
  change (and on every explicit rebuild); the prior state is preserved in
  `version_history` (bounded) and `provenance` records the learning
  source, sample years, and verified-sample count.

Source-verified certificates (`verified_at_source`, `manually_confirmed`)
weight anchors and value shapes by `APP_FORMAT_VERIFIED_WEIGHT` (default
2.0) without relaxing the distinct-sample corroboration threshold — one
verified sample alone still cannot create an anchor.

A profile whose measured `anchor_precision` falls below
`APP_PROFILE_QUALITY_FLOOR` (default 0.5), or that is flagged as drifting,
contributes reduced *positive* evidence to `format_score` via
`profile_quality_weight` (down to a 0.2 floor; drifting caps at 0.5). It
never contributes negative evidence: missing anchors are never treated as
a penalty, and the anchors are not required during extraction.
