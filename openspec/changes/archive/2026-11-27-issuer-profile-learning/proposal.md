# Proposal

## Why

Extraction, format validation, and source verification are three learning loops that do not share what they know: extraction uses one static global prompt, format profiles only score text after classification, and verifier support is hardcoded per host. As a result, every new issuer needs prompt or code changes, the local 7B model misses issuer-specific labels, and certificates verified at source do not improve future extraction or validation.

## What Changes

- **Measure before tuning.** Add an offline extraction evaluation harness: a versioned golden set built from approved/validated certificates with human-confirmed fields; a dry-run runner that measures schema validity, per-field accuracy (exact and normalized), evidence-quote validity, missing-field rate, fabricated-value rate, and latency for a given model/prompt/profile; persist run summaries and compare against a baseline. No automatic deployment or approval.
- **Learn issuer formats, not just anchors.** Extend format profiles from whole-line text anchors to per-issuer knowledge: learned field-label patterns, value shapes (date order, score/code shape, level vocabulary), profile quality (precision/recall on approved samples, sample counts, anchor churn), and drift signals. Learning only from approved/validated and verified certificates; corroboration thresholds; conflicts never auto-activate; rejected documents never teach.
- **Turn labels into first-class learned data.** Use `FieldLabelAlias` as the canonical label-to-field store, adding support counts, confidence, provenance, and lifecycle (candidate/active/rejected). Learn aliases automatically from approved certificates and reviewer corrections, scoped to the issuer; manual aliases remain authoritative; reviewers can inspect, deactivate, and confirm candidates.
- **Make extraction issuer-aware with two passes.** Pass 1 is a deterministic pre-detection of issuer and certificate type/exam from text, aliases, profile anchors, and verifier domains, returning confidence and a margin; when ambiguous it does not force an issuer, and an optional bounded classifier fallback runs only when configured. Pass 2 injects the detected issuer's learned labels, value shapes, and anonymized layout exemplars into the extraction instruction, runs a deterministic candidate pre-pass (label-to-value pairs, score/date candidates), and requires verbatim evidence. After classification, a mismatch between the pre-detected and resolved issuer is flagged and may trigger at most one bounded re-extraction with the resolved profile. Record model, prompt, profile, and pre-detection versions per extraction run. Optionally escalate missing critical fields to a configured fallback model, bounded.
- **Upgrade verification from capture to comparison.** Decode QR payloads when present; move verifier configuration from code into per-issuer data (host, code pattern, URL template, success criteria, source-document parsing); when a verifier returns a source document, compare its fields with the extracted certificate and record matches/mismatches. Expose a reviewer-facing veracity score (0-1) that combines source verification, format/profile match, label-value consistency, and extraction evidence; show the numeric value and quality band in the document list and review detail, and derive the row color from that score rather than from format alone. Source verification remains a separate badge and the score never auto-approves. Verified samples strengthen format profiles.
- **Close the review loop.** Show learned-label provenance, profile version, verification evidence, veracity breakdown, and source-comparison results in review; reviewer corrections can propose label aliases and profile updates for confirmation. Show the source document by default in the review screen with the extracted data, replace the list's preview-only eye action with an inline thumbnail, and keep the lightbox only for zoom. Keep all learning additive and auditable.

**Phasing.** Phase 1: evaluation harness, learned labels, and issuer-aware extraction. Phase 2: profile quality/drift, label-consistency validation, and review surfacing. Phase 3: QR, per-issuer verifier configuration, source comparison, and verified-sample learning. Each phase is independently shippable; no phase auto-approves a certificate.

## Capabilities

### New Capabilities

- `extraction-evaluation`: versioned golden sets, offline dry-run evaluation, per-field/evidence/latency metrics, run history, and baseline regression reporting for extraction models, prompts, and issuer profiles.

### Modified Capabilities

- `certificate-format-profiles`: profiles gain learned field-label patterns, value shapes, quality/drift metrics, verified-sample weighting, profile versions, and use in extraction and validation, not only post-classification scoring.
- `field-label-mapping`: aliases gain learned provenance, support/confidence, candidate/active/rejected lifecycle, corroboration, conflict handling, automatic learning from approved certificates and reviewer corrections, and issuer pre-detection scoping before extraction.
- `certificate-extraction`: two-pass issuer/type pre-detection, profile-guided prompt context, anonymized exemplars, deterministic candidate pre-pass, post-extraction issuer consistency checks, per-run metadata, and bounded fallback-model escalation.
- `certificate-source-verification`: QR payload decoding, per-issuer verifier configuration, source-document field comparison, a numeric veracity score with component breakdown, and verified samples as learning input.
- `review-experience`: review surfaces learned-label provenance, profile version/quality, numeric veracity and its breakdown, source-comparison results, a source document visible by default, and an inline document-list thumbnail, with confirm/reject actions for learned knowledge.

## Impact

- **Data model/migrations**: `FormatProfile` (value shapes, quality, version), `FieldLabelAlias` (support, confidence, lifecycle, provenance), `Certificate` (extraction-run metadata, pre-detection result/confidence, veracity score/components, source comparison), per-issuer verifier configuration, and evaluation run/case storage.
- **Services**: new `pre_detection.py`, `trust.py`, and `evaluation.py`; changes to `format_profile.py`, `field_aliases.py`, `extraction.py`, `verification.py`, `verifiers.py`, `learning.py`, `classification.py`, `review.py`, `review_reasons.py`.
- **Commands**: new evaluation command(s); backfill/rebuild command for issuer profiles, learned aliases, and veracity scores.
- **Views/templates**: format-profile admin, field-alias admin, review detail/list, filters for learned/verification/veracity states; `documents/templates/documents/list.html` gains an inline thumbnail and numeric veracity badge; `detail.html` shows the source document by default and the veracity breakdown; `static/core/app.css` layout adjustments.
- **Dependencies**: optional QR decoder (`zxing-cpp` or `pyzbar`) behind a feature flag; no new external service; Ollama remains the only model runtime.
- **Docs/tests**: extraction, classification, review, configuration, and data model docs; unit/integration tests for learning, pre-detection, two-pass extraction, prompt context, evaluation metrics, veracity scoring, QR, source comparison, default-visible document review, inline thumbnails, and permissions.
- **Out of scope**: model fine-tuning, replacing Ollama, visual logo/seal verification, automatic approval from format, veracity, or verification, and automatic activation of conflicting learned knowledge.
