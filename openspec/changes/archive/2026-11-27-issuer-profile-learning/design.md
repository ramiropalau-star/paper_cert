# Design

## Context

See `proposal.md` for motivation and `specs/` for behavior contracts. The current pipeline acquires text, sends one global prompt to Ollama, classifies the result, scores format after classification, harvests verification artifacts deterministically, and routes uncertain records to review. The document list shows a format badge whose color is derived from the format score; the review detail renders the original in an iframe but the list still requires a preview click to see an image. Verifier support is hardcoded for two issuers, and there is no offline way to compare extraction changes.

Constraints: Django 5 and PostgreSQL; Ollama remains the only model runtime; no new external service; the local 7B model has a limited context budget; reviewer roles and auditability must be preserved; certificate images and extracted data contain personal data.

## Goals / Non-Goals

**Goals:**

- Improve extraction precision and recall for issuer-specific labels without per-issuer code changes.
- Make verification evidence and its limits visible to reviewers as a numeric score, not color alone.
- Remove redundant image-reveal clicks in the review flow.
- Make every learning and scoring change measurable and reversible.

**Non-Goals:**

- Proving certificate authenticity or detecting visual forgery.
- Replacing Ollama, fine-tuning the model, or adding a second production model by default.
- Auto-approving, auto-rejecting, or auto-delivering certificates.
- Building a general document-classification system beyond language certificates.

## Decisions

### 1. Two passes: deterministic detection, then profile-guided extraction

Pass 1 is a deterministic pre-detection over document text, active aliases, profile anchors, exam/language vocabulary, and verifier domains. It returns candidate issuers/types with scores, a confidence, and a margin. If confidence or margin is below threshold, it returns `ambiguous` and does not force an issuer.

Pass 2 uses the detected issuer's profile to build the extraction instruction: learned labels, value shapes, expected anchors, and anonymized exemplars. A deterministic candidate pre-pass extracts label-to-value pairs, score candidates, and date candidates; the model validates them with verbatim quotes. If pass 1 is ambiguous or no profile exists, pass 2 uses the existing global instruction.

A classifier LLM fallback for pass 1 is optional and off by default. It is enabled only after evaluation shows a benefit, and it is bounded to one call.

Alternative considered: a first LLM call that classifies the certificate. Rejected as the default because it doubles latency, adds cost, and lets a classification error poison the second pass. The deterministic pass is cheaper, explainable, and testable.

### 2. Post-classification consistency check, not an open loop

After classification, the resolved entity/exam is compared with the pre-detection result. A mismatch records `entity_mismatch` and may trigger at most one re-extraction with the resolved issuer's profile. The re-run passes the same evidence validation. There is no loop until agreement; the reviewer sees both values.

This bounds the main risk of two passes: a wrong pass 1 producing a confidently wrong pass 2. The fallback path is global extraction, and the mismatch is visible.

### 3. Veracity is a component score, not an authenticity claim

The veracity score is a weighted combination of:

- source verification status (`verified_at_source`/`manually_confirmed` strongest; `self_reported` weak; `none` lowest);
- format/profile match, including profile quality and drift;
- label-value consistency against learned labels and value shapes;
- extraction evidence coverage and field verification.

The score stores its component values and the weights version. Weights are configuration, calibrated with the evaluation harness. The UI labels the score as a review aid, never as proof. A high score does not approve or hide review reasons.

Alternative considered: a single boolean "verified". Rejected because it hides partial evidence and cannot distinguish a well-formatted unverified document from a source-verified one.

### 4. Veracity UI: numeric value, band, and breakdown

The document list shows a numeric veracity value and a high/medium/low band. The row color derives from the veracity band. The format score remains a separate badge so reviewers can see layout quality independently. The review detail shows the score, the band, and a breakdown with human labels.

This directly addresses the current gap: color exists but the criterion and value are not visible. The color now encodes the stated criterion.

### 5. Review shows the source document by default

The review detail keeps the source document rendered on initial load, side by side with the data on wide screens and stacked on narrow screens. The existing iframe behavior is kept, but the layout must not hide it behind a click. The list replaces the preview-only eye action with a lazy-loaded inline thumbnail; activating the thumbnail opens the review detail, and a separate zoom action opens the modal for enlargement.

Alternative considered: keep the modal-only preview. Rejected because the reviewer is already going to inspect the image; an extra click adds no information.

### 6. Alias lifecycle and pre-detection scoping

Aliases gain `candidate`, `active`, and `rejected` states, support count, confidence, provenance, and scope. Manual aliases are authoritative. Learned aliases activate only after corroboration or reviewer confirmation; conflicts stay candidates. Pre-detection makes issuer-scoped aliases available before a certificate exists, removing the current chicken-and-egg dependency on classification.

### 7. Per-issuer verifier configuration as data

Verifier configuration moves from code to data: host, code pattern, URL template, success criteria, and optional source-document parser. Authorized reviewers manage it; viewers cannot. URLs are validated and restricted to configured hosts with timeouts, avoiding an SSRF surface. Existing UV/GVA behavior is migrated as seed data.

### 8. Evaluation harness before tuning

The golden set is built from approved/validated certificates with human-confirmed fields, versioned, and excluded from rejected documents. Dry runs do not mutate live certificates. Metrics cover schema validity, per-field exact/normalized accuracy, missing and fabricated values, evidence validity, and latency, grouped by issuer and type. Baseline comparison reports regressions but never deploys.

### 9. Data model and migration shape

Additive fields and new tables:

- `FormatProfile`: value shapes, quality metrics, drift state, version, provenance.
- `FieldLabelAlias`: lifecycle, support, confidence, provenance.
- `Certificate`: pre-detection result/confidence, extraction run reference, veracity score/components, source-comparison result.
- New `ExtractionRun`, `VerifierConfig`, `EvaluationRun`, `EvaluationCase` (or equivalent) tables.

Migrations are additive. Backfills are separate commands so deployment does not block on rebuilding profiles or scores. Feature flags gate pre-detection, trust scoring, and the UI changes.

### 10. Security and privacy

- Verifier configuration is reviewer/admin-only, validated, and restricted to configured hosts with timeouts.
- Evaluation data and golden sets contain personal data; access is role-restricted and retention is documented.
- Anonymized exemplars strip names, codes, and dates before entering a prompt.
- No raw document text is sent to a new external service.

## Risks / Trade-offs

- **Wrong pre-detection locks extraction into the wrong profile** → confidence/margin thresholds, global fallback, post-classification mismatch flag, at most one bounded re-run, reviewer-visible values.
- **Veracity score is over-trusted** → numeric value with breakdown, explicit "review aid" wording, source verification shown separately, no auto-approval, high score never hides warnings.
- **Profile drift penalizes legitimate layout changes** → drift detection, quality down-weighting, no negative evidence from drifting profiles, rebuild command.
- **Alias pollution from corrections** → candidate lifecycle, corroboration, manual authority, rejected documents excluded, reviewer confirmation.
- **Verifier configuration creates SSRF or abuse risk** → host allowlist, URL validation, timeouts, reviewer/admin permissions, no arbitrary redirects.
- **Evaluation data leaks personal information** → role-restricted access, anonymized prompts, documented retention, no external service.
- **Two passes increase latency** → pass 1 is deterministic and cheap; pass 2 remains one model call; classifier fallback is opt-in and bounded; re-run is at most once.
- **Migration and backfill complexity** → additive schema, separate backfill commands, feature flags, rollback by disabling flags without dropping data.

## Migration Plan

1. Add schema fields/tables and seed the existing UV/GVA verifier configuration.
2. Build the golden set and record a baseline with the current prompt/model.
3. Ship pre-detection, profile-guided extraction, and metadata behind a feature flag; compare against baseline.
4. Backfill format profile versions and veracity scores; keep old scores readable during rollout.
5. Enable the list/detail UI changes with the score feature flag; verify accessibility and responsive layout.
6. Roll back by disabling flags; schema remains additive and no data is deleted.

## Open Questions

None that change the specs or task breakdown. Exact veracity weights and the classifier-fallback default are configuration decisions to be calibrated with evaluation results.
