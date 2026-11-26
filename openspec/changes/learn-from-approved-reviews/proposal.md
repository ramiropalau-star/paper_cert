# Proposal

## Why

Every certificate that a reviewer corrects and approves contains human-verified knowledge (which entity issued it, which exam, which UV L2 equivalence applies, and what the issuer's official layout looks like) that the system currently discards after using it once. As a result, each new issuer or format variant sends the next certificate back to manual review, and a plain-text PDF with plausible fields is indistinguishable from a genuine certificate during classification.

## What Changes

- On certificate approval (and validation, where applicable), the system learns from the human-corrected record:
  - Creates missing catalog aliases (`LanguageAlias`, `EntityAlias`, `ExamAlias`) so literal variants resolve automatically next time.
  - Creates missing catalog entries (`Entity`, `Exam`) when a reviewer assigns one to a previously unknown literal.
  - Records equivalences and CEFR conversion rules derived from manually corrected values, with reviewer attribution.
- Introduces per-issuer **format profiles**: approved certificates contribute textual "anchor" signatures grouped by entity and issuance year (with exam-level granularity when enough samples exist). Issuance-year cohorting absorbs legitimate layout drift across years.
- Classification computes a `format_score` per document by matching page text against the relevant cohort profile, and blends it into certificate confidence. A new `format_mismatch` review reason routes suspicious documents to review even when extracted fields look clean.
- Format profiles require corroboration: an anchor only counts as expected when seen in at least two approved certificates of the cohort (or ≥50% of samples, whichever is stricter), so single-certificate quirks never define a format.

## Capabilities

### New Capabilities

- `catalog-learning`: Review-driven updates to the catalog — alias creation, new entity/exam entries, and equivalence/CEFR rule derivation from approved certificates, all idempotent and attributable to the approving actor.
- `certificate-format-profiles`: Temporal, cohort-based format signatures per issuer that score how well a document's text matches the expected layout of its claimed entity/year.

### Modified Capabilities

- `certificate-classification`: Classification now computes and stores a format score, blends it into confidence, and can emit the `format_mismatch` review reason.
- `review-workflow`: Approval (and validation) of a certificate triggers catalog learning as a side effect, recorded in the audit trail.

## Impact

- `catalog/`: new models for format profiles (or profile storage), possible new fields on `Entity`/`Exam`.
- `documents/services/`: new `learning.py` (catalog updates on review) and `format_profile.py` (anchor extraction + scoring); hooks in `review.py` (approve/validate) and `classification.py` (format score, new reason code).
- `documents/models.py`: `Certificate` gains format-score fields; `ReviewEvent` may record learning outcomes.
- Review UI: surface format score/mismatch warning; optionally show which catalog entries were learned.
- Tests: learning idempotency, cohort behavior across issuance years, format scoring, and review-reason integration.
- No new infrastructure or external services; all learning is deterministic text analysis over data already stored.
