# Design

## Context

See proposal.md for motivation. Relevant current state:

- Classification (`documents/services/classification.py`) resolves `language_literal`, `entity_literal`, `exam_literal` to catalog FKs via normalized exact match against `*Alias` tables; unknowns route to review with `unknown_entity`/`unknown_language` reasons.
- `Certificate.confidence` is the LLM-reported extraction confidence, persisted in `extraction.py` and only compared against `APP_CONFIDENCE_REVIEW_THRESHOLD` in `aggregate_reasons`.
- `DocumentPage` rows store per-page text + OCR confidence; page images are not persisted locally.
- Review approval (`documents/services/review.py::approve_certificate`) and validation (`validate_certificate`) are the human-trust boundaries; `manual_fields` records which fields a human touched.
- `Certificate.equivalence` stores a CEFR code (`A1`–`C2`) chosen from `CefrLevel` in the review form; `Equivalence` rules map `exam` (+ optional score band) → accredited level.
- The review form only selects existing catalog `Entity`/`Exam` rows; new issuers enter the catalog through the Django admin (`catalog/admin.py`).
- Normalization for matching is `catalog.normalization.normalize_catalog_text` (NFKC, casefold, whitespace collapse).

## Goals / Non-Goals

**Goals:**

- Turn every approved/validated certificate into durable catalog knowledge (aliases, equivalence rules, format anchors) with full idempotency and actor attribution.
- Score each classified document against the format profile of its claimed issuer/year cohort and feed that score into confidence and review routing.
- Tolerate legitimate per-year layout drift via cohort segmentation.

**Non-Goals:**

- Visual/logo verification (phase 2; requires page rendering and a vision model — explicitly deferred).
- Auto-creating `Entity`/`Exam` rows from free text. Reviewers pick existing catalog entries; genuinely new issuers are created via admin, then learning attaches aliases. (The spec's "creates missing catalog entries" is satisfied for `Exam` only when a resolved entity exists and the exam literal is unambiguous — see Decisions.)
- Catalog models for `issuing_body` and `test_center` roles (currently literal-only fields); no new role entities in this change.
- Fuzzy/ML matching — all matching stays exact-after-normalization, consistent with existing catalog semantics.

## Decisions

### D1. Learning runs as a post-commit side effect of approve/validate

`approve_certificate` and `validate_certificate` call `documents/services/learning.py::learn_from_certificate(certificate, actor)` **after** the state transition commits, wrapped in try/except. A learning failure logs and records a `ReviewEvent` note but never blocks or rolls back the approval (spec: "Learning failure does not block approval").

- *Alternative considered*: learning inside the approval transaction — rejected because a catalog error would then block approvals, violating the spec.

### D2. Alias learning covers literal→FK pairs only

For each of `language`, `entity`, `exam`: if the FK is set, the corresponding `*_literal` is non-empty, and no alias with that `normalized_alias` exists, create the `*Alias` via `get_or_create`. If `normalized_alias` already exists pointing to a **different** catalog entry, skip and record the conflict in the learning outcome (never overwrite — spec: "never overrides human catalog decisions").

- Fields manually edited (`manual_fields`) are preferred sources; auto-resolved literals are also learned since approval ratifies them.

### D3. Equivalence learning creates unbanded rules only when safe

On approval, if `certificate.exam_id` is set, `certificate.equivalence` is a valid `CefrLevel`, and **no** `Equivalence` (active or not) exists for that exam with the same `accredited_level`, create `Equivalence(exam=…, accredited_level=…, source="review", label=<certificate_code or document ref>, is_active=True)`.

- Unbanded (null score range) so it acts as fallback; `matching_equivalence` already prefers banded rules, so a future precise banded rule wins automatically.
- `source="review"` distinguishes learned rules for audit; admin can deactivate.
- *Risk accepted*: a one-off manual equivalence becomes active for all scores of that exam. Mitigation: `source` marker + the review UI shows provenance; rejected-certificate guard prevents junk.

### D4. CEFR learning creates inactive candidate rules

If `cefr_source == MANUAL` and `score_literal` parses to a number, create `CefrConversionRule(exam=…, score_min=score, score_max=score, cefr_level=…, approved_by=<actor>, approved_at=now, reference="review:<certificate pk>", is_active=False)`.

- Inactive because a point band only matches the exact observed score; a human must widen the band and activate — the rule's own `clean()` already requires approver/reference for activation, and we pre-fill them from the actor/certificate.
- *Alternative*: auto-activate with a heuristic band — rejected; guessing score ranges is exactly the kind of silent wrongness this system avoids.

### D5. Exam auto-creation is limited to unambiguous literals

If `entity_id` and `language_id` are resolved, `exam_id` is null, and `exam_literal` is non-empty: create `Exam(name=<literal as printed, trimmed>, entity=…, language=…, is_active=True)` **only if** no active exam already has that normalized name under the entity. The literal becomes both the exam name and its alias implicitly (exact-name matching covers it). If the literal is empty or matches nothing sensible, skip.

- This is the only catalog-entry creation learning performs; `Entity` creation stays manual via admin (form requires selecting an existing entity anyway).

### D6. Format profiles are cohort-segmented catalog models

New model in `catalog` (issuer knowledge belongs with the catalog):

```python
class FormatProfile(TimestampedModel):
    entity = FK(Entity, related_name="format_profiles")
    exam = FK(Exam, null=True, blank=True)   # granular cohort when samples suffice
    year = PositiveIntegerField()            # issuance year cohort
    anchors = JSONField(default=list)        # [{"text": normalized_anchor, "df": int}]
    sample_count = PositiveIntegerField(default=0)
    class Meta: constraints = [UniqueConstraint(fields=["entity","exam","year"])]
```

- Cohort key = `(entity, year)`; `exam` is populated only when ≥ `APP_FORMAT_MIN_EXAM_SAMPLES` (default 3) approved certs share entity+exam+year — below that, the entity-level profile is used.
- An entity-wide aggregate is **not** stored separately; scoring falls back to the union of that entity's year cohorts (see D8).

### D7. Anchors are normalized text lines, corroboration-gated

Anchor extraction from `DocumentPage.text`:

1. Normalize each line with `normalize_catalog_text`; drop lines < 8 or > 160 chars, or with < 4 alphabetic characters (removes pure numbers/codes that vary per certificate).
2. Additionally strip lines that are mostly the variable fields? — No: keep it simple. Boilerplate like "This is to certify that" survives; student names/dates rarely recur verbatim across certificates, so document-frequency filtering removes them naturally.
3. A candidate becomes an anchor only when its document frequency within the cohort is `>= max(2, ceil(0.5 * sample_count))` — the spec's "two or ≥50%, whichever is stricter".
4. `anchors` stores `[{"text": anchor, "df": n}]`, capped at 200 entries by df desc.

- *Alternative considered*: n-gram/TF-IDF weighting — rejected as overkill; line-level DF is deterministic, inspectable, and enough for layout signatures.

### D8. Format scoring prefers year cohort, falls back to entity

`format_profile.py::score_document_format(certificate)`:

1. Resolve cohort: `(entity, issue_date.year)`; if `issue_date` is null use `exam_date`/`detected_date` year; if still unknown, score against the entity-wide union of all its cohort anchors.
2. `score = Σ df(matched anchors) / Σ df(all cohort anchors)` — recall-weighted, 0..1. If the cohort has < `APP_FORMAT_MIN_SAMPLES` (default 2) samples, return `None` (no evidence — spec: insufficient samples are neutral).
3. Cross-entity penalty: if the document matches anchors belonging **exclusively** to a different entity's cohorts better than its claimed entity's, cap the score at `APP_FORMAT_MAX_SCORE` (default 0.5). Implemented as: compute the same recall against the best-scoring *other* entity; if `other_score > score + 0.2`, apply cap.
4. Persist `certificate.format_score` (float) and `certificate.format_cohort` (string like `"entity:12/year:2023"` or `"entity:12"`).

- Scoring runs inside `classify_certificate` **after** `apply_dates` (needs the year) and before `aggregate_reasons`, so `format_mismatch` can join the reason set.

### D9. Confidence blend and the new review reason

- New `Certificate.format_score` (FloatField, null) + `format_cohort` (CharField).
- Blended confidence stored back on `certificate.confidence`:
  `confidence = round(0.7 * extraction_confidence + 0.3 * format_score, 4)` when `format_score` is not None; unchanged otherwise. The raw LLM value stays visible via `field_confidence`/`prompt_version` provenance.
- New reason code `format_mismatch` added to `CLASSIFICATION_REASON_CODES`, `REVIEW_REASON_DETAILS` (label "Formato no reconocido"), emitted when `entity_id` is set and `format_score < APP_FORMAT_SCORE_THRESHOLD` (default 0.4).
- Thresholds in `config/settings.py` under `APP`: `format_min_samples`, `format_min_exam_samples`, `format_score_threshold`, `format_max_score`.

### D10. Learning outcome is auditable

`learn_from_certificate` returns a summary dict `{aliases_created, exams_created, equivalences_created, cefr_rules_created, format_anchors_added, conflicts: [...]}`. `review.py` appends it to the approval `ReviewEvent.after["learning"]` (and creates a `ReviewEvent` with a new `LEARN` event type only when learning runs outside approve/validate, e.g. backfill command). Add `EventType.LEARN = "learn"`.

## Risks / Trade-offs

- [OCR noise fragments boilerplate lines] → Mitigation: normalization + DF≥2/50% corroboration + 200-anchor cap; noisy anchors simply never reach threshold.
- [A wrongly approved certificate poisons aliases/rules] → Mitigation: learning only adds, never modifies; `source="review"` provenance; admin can deactivate; ReviewEvent audit trail.
- [Unbanded learned equivalence misapplies to all scores of an exam] → Mitigation: banded rules take precedence in `matching_equivalence`; `source` marker for audit.
- [Year cohort with 1 sample] → Neutral by design (`format_score=None`); entity fallback still applies when other cohorts exist? — No: if the specific year cohort is insufficient we fall back to entity-union only when *no* cohort reaches threshold; documented in D8 step 2.
- [Learning on every approve adds latency] → Bounded: a few indexed queries + JSON update per certificate; runs post-commit.

## Migration Plan

1. `catalog` migration: `FormatProfile` model.
2. `documents` migration: `Certificate.format_score`, `Certificate.format_cohort`; `ReviewEvent.EventType.LEARN` choice.
3. Settings additions with safe defaults (feature is inert until profiles accumulate ≥2 approved certs per cohort).
4. Optional backfill management command `learn_from_history` to seed profiles/aliases from already-approved certificates — included as a task, run manually.
5. Rollback: profiles and learned rows are additive; deactivating learned `Equivalence`/`CefrConversionRule` rows reverts behavior without code deploy.

## Open Questions

- Exact blend weights (0.7/0.3) and thresholds (0.4) are initial guesses — tune after observing real distributions; both are settings, not code.
