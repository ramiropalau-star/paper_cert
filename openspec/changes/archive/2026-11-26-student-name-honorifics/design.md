# Design

## Context

See proposal.md — Why. `student_name` is a literal field persisted by
`_persist_certificate` in `documents/services/extraction.py`. Extraction
runs per document; page text and payload are available at persist time.

## Goals / Non-Goals

Goals:

- Deterministic, auditable removal of leading honorifics on
  `student_name`.
- Multilingual coverage for the languages certificates actually arrive in.
- Prompt guidance so the model stops emitting titles in the first place.

Non-goals:

- Stripping titles from non-name fields.
- Translating or expanding abbreviations.
- Handling titles in the middle/end of names (preserved by design).
- A configurable per-issuer title list (fixed curated list is enough; rare
  misses are handled by manual edit).

## Decisions

### D1: Deterministic post-process at persist time

A `_strip_name_honorifics(value) -> (stripped, removed_token | None)` helper
applied to `student_name` inside `_persist_certificate` before defaults are
written. Rationale: the LLM is unreliable at edge-case token decisions and
evidence quotes are verbatim — a regex over a closed list is predictable,
testable, and fast. The prompt also gets one guidance line so most cases
never reach the strip.

Alternative considered: prompt-only ("exclude titles") — rejected, small
models miss it intermittently; deterministic layer guarantees the
invariant.

### D2: Conservative multilingual title list

Two tiers:

- **Always strip** (unambiguous titles): Doña, Dña, Señora, Srta, Señor,
  Sr., Sra., Mr., Mrs., Ms., Miss, Mme, Mlle, Herr, Frau, Senhora, Senhor,
  Signora, Signor, Dottoressa? (no — keep list tight), plus accented forms.
- **Never strip** (ambiguous): Don, bare "D.", "M.", "Dr."? — decision:
  include "Dr./Dra." only when followed by ≥2 name words? Simpler: exclude
  medical/academic titles entirely (Dr. could be part of registered name on
  some certs) — they are rare on student certificates. Documented in code.

Matching rules: case-insensitive, accent-folded via existing `_norm_text`
folding; token must be followed by at least two remaining name words
(avoids stripping a one-word name edge); only leading tokens, repeatedly
("Sr. Don José" → strip both? — loop while next token is in always-strip
list, max 3 iterations).

### D3: Auditability

When a token is stripped, store the original literal in the certificate's
extraction metadata (e.g. `evidence` entry or a `name_title_stripped`
marker listing removed tokens). Keeps the pipeline honest: reviewer can see
the cert said "Doña X" but we stored "X".

### D4: Prompt version bump

`PROMPT_VERSION` → `extraction-v8` (or next free) since model-visible
instruction changes.

## Risks / Trade-offs

- [Real given name collides with a title] → conservative list + ≥2-word
  remainder rule + audit marker; residual risk accepted (manual edit path
  exists).
- [Title glued to name without space ("DoñaMaría")] → not handled; OCR text
  virtually always separates. Documented limitation.
- [Non-Latin scripts] → out of scope; certificates processed are Latin
  script. Documented.

## Migration Plan

Code-only change; no data migration. Existing certificates keep their
stored names (no backfill — reviewers can re-extract selectively if wanted).
Rollback = revert deploy.

## Open Questions

- Whether to backfill/re-extract historical certificates with titles —
  defer; likely unnecessary volume.
