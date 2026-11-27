# Extraction with Ollama

Certificate extraction sends the acquired page text to a local Ollama model
and stores only what the document states. The model never infers missing
data; every field can carry evidence (page + quote) and a confidence value.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `APP_OLLAMA_URL` | `http://ollama:11434` | Ollama base URL |
| `APP_OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Chat model used for extraction |
| `APP_OLLAMA_TIMEOUT_SECONDS` | `180` | Per-request timeout |
| `APP_OLLAMA_RETRIES` | `2` | Transport retries on timeout/5xx |
| `APP_LLM_MAX_INPUT_CHARS` | `40000` | Input cap; larger documents go to review |
| `APP_PRE_DETECTION_ENABLED` | `true` | Run issuer/type pre-detection before extraction |
| `APP_PRE_DETECTION_CONFIDENCE` | `0.6` | Minimum confidence for a pre-detection match |
| `APP_PRE_DETECTION_MARGIN` | `0.15` | Minimum top-two score margin for a match |
| `APP_PRE_DETECTION_CLASSIFIER_ENABLED` | `false` | Allow one bounded classifier call on ambiguous results |

Pull the model once with `ollama pull <model>` (see `docs/operations.md`).

## Issuer and type pre-detection

Before the model call, `documents/services/pre_detection.py` scores every
active catalog `Entity` from deterministic signals in the document text:

- **Name/alias hits** (+4): the entity name or any `EntityAlias` appears in
  the accent-folded text.
- **Exam hits** (+2 each, capped at +4): exams belonging to the entity match
  by name or `ExamAlias`.
- **Profile anchor recall** (+2 × recall): the best fraction of a
  `FormatProfile`'s stored anchors found as normalized document lines.
- **Verifier domains** (+3): an active `VerifierConfig` host for the entity
  appears in the text.

The raw score is normalized to a 0–1 confidence
(`score / 6.0`). The result is `match` only when confidence ≥
`APP_PRE_DETECTION_CONFIDENCE` **and** the margin over the second candidate
≥ `APP_PRE_DETECTION_MARGIN`; otherwise it is `ambiguous` (or `none` when no
signal fired). A match also records the best-scoring `Exam` and the
best-matching `Language`. The full result — candidates, confidence, margin,
and classifier output — is stored on `Certificate.pre_detection` and on the
`ExtractionRun` row created for the pass.

When `APP_PRE_DETECTION_CLASSIFIER_ENABLED` is `true` and the deterministic
result is `ambiguous`, exactly one bounded LLM call may refine the guess;
its output is recorded under `classifier` in the stored result and can
upgrade the outcome to `match` only when it resolves to catalog entries with
confidence ≥ the threshold. The classifier never runs on a deterministic
match, is off by default, and its failure never breaks extraction.

Pre-detection is advisory: a `match` scopes field-label aliases and selects
the issuer's format profile for extraction, but classification still decides
the final entity/exam. Ambiguous or unmatched documents use the global
(alias) profile path.

## Profile-guided extraction pass

When pre-detection returns `match` and `APP_PROFILE_GUIDED_EXTRACTION_ENABLED`
is `true`, extraction runs a second, issuer-aware pass:

1. **Profile selection** — `profile_context.select_profile()` picks the best
   active `FormatProfile` for the detected entity (exam-scoped profile first,
   then the entity-level profile for the latest year).
2. **Prompt context** — `build_profile_context()` renders learned field
   labels, expected value shapes, expected layout anchors, and anonymized
   exemplars (names, codes, and dates are masked) into the prompt, bounded
   by `APP_PROFILE_CONTEXT_MAX_CHARS`.
3. **Candidate pre-pass** — `candidates.extract_candidates()` deterministically
   scans the page texts for label-value pairs, score candidates, and date
   candidates. The candidates are injected into the prompt as hints the model
   must validate with verbatim quotes.
4. **Candidate application** — after the model responds, still-empty fields
   are filled from candidates only when the stored quote verifies verbatim
   against the cited page; applied values carry low confidence and are marked
   unverified. Candidates whose quotes do not verify are dropped.

With an ambiguous or absent pre-detection result — or no active profile —
the existing global instruction and global aliases are used unchanged. Each
`ExtractionRun` records the model, prompt version, profile and profile
version, pre-detection result/confidence, pass count, fallback use, and
latency so every result traces to the configuration that produced it.

## Consistency check and bounded re-extraction

After classification resolves the catalog entity/exam,
`documents/services/consistency.py` compares them with the stored
pre-detection result (`pre_detection.consistency` on the certificate):

- A different resolved entity — or a different resolved exam — records the
  `entity_mismatch` review reason. Ambiguous pre-detection never produces
  this reason.
- When the mismatch is material and the resolved issuer has an active
  profile, extraction may re-run **at most once** with that profile. The
  re-run is marked by `fallback_used="issuer_consistency"` on its
  `ExtractionRun`, passes the same evidence validation, and never loops or
  auto-approves; the reviewer sees both the pre-detected and resolved
  values.

## Score sanitization and deterministic recovery

The model sometimes returns malformed score literals — set/list notation
like `{175, 183}` (per-skill scores) or `[114]`. `_sanitize_score_value`
unwraps a bracketed single scalar and clears anything else, letting the
deterministic fallbacks recover the real overall score.

Score recovery patterns, tried in order before the generic label scan:

1. `score / 100` shape (`_SCORE_OVER_RE`).
2. `Overall/Global Score|Result|Mark|Grade` label followed by the number,
   across a line break (`_SCORE_OVERALL_RE`) — covers layouts like
   Cambridge's `Overall Score\n179`.
3. Number followed by an overall/global label (`_SCORE_TRAIL_RE`) —
   covers layouts where the value precedes the label, e.g. Oxford's
   `B2 114\nOVERALL SCORE`.
4. Generic score-ish labels on the same line (`_SCORE_LABEL_RE`).

Recovered values are marked `score_literal` in `unverified_fields` for
reviewer confirmation. Candidates only fill fields the model left empty,
so a verified model value is never overwritten.

## Bounded fallback-model escalation

When score or an issue date is still missing after the primary pass,
deterministic fallbacks, and the focus pass, a configured fallback model
(`APP_EXTRACTION_FALLBACK_MODEL`, empty by default) may be called **at most
once**, scoped to only the missing fields, with the same schema and
evidence validation. A complete extraction never triggers it. The outcome
is recorded on the run: `fallback_used="fallback_model"`,
`fallback_model=<name>`, and `error` carries the failure detail when the
fallback itself fails — the primary result is always kept.

## Contract

- Endpoint: `POST {APP_OLLAMA_URL}/api/chat` with `stream: false`,
  `temperature: 0`, and `format` set to the extraction JSON schema.
- The schema requires `is_language_certificate`,
  `multiple_certificates_suspected`, one object per field
  (`value`, `evidence{page, quote}`, `confidence`), a `dates` array of
  `{text, role, page, quote}` candidates, and an overall `confidence`.
- The system prompt (`SYSTEM_PROMPT` in
  `documents/services/extraction.py`) forbids inference and treats the
  document text as untrusted content.

## Prompt versioning

`PROMPT_VERSION` (`extraction-v1`) is stored on every certificate row. When
the prompt or schema changes, bump the constant so records remain
traceable to the prompt that produced them.

## Validation and retries

Model output is parsed as JSON and validated with Pydantic against
`ExtractionPayload`. Invalid JSON or schema mismatches are retried up to
`MAX_INVALID_ATTEMPTS` (3) times; exhaustion routes the document to
`pending_review` with the `invalid_extraction` reason and no partial data
is stored.

## Outcomes

| Condition | Document state | Review reasons |
| --- | --- | --- |
| Valid certificate | `extracted` | - |
| Valid non-certificate | `pending_review` | `non_certificate` |
| Multiple certificates suspected | `extracted` (flag stored) | `multiple_certificates` |
| Input over `APP_LLM_MAX_INPUT_CHARS` | `pending_review` | `input_too_large` |
| No acquired text | `pending_review` | `missing_text` |
| Ollama unreachable/error | `error` | `model_unavailable` |
| Invalid output after retries | `pending_review` | `invalid_extraction` |

Review-routed documents get the configured Paperless label (`Otros` by
default). Reprocessing reuses the same document and certificate rows.

## Troubleshooting

- `model_unavailable`: check `APP_OLLAMA_URL`, that the container is
  healthy, and that the model is pulled. The document can be reprocessed
  once Ollama recovers.
- `invalid_extraction`: the model ignored the schema. Try a different
  `APP_OLLAMA_MODEL` or reduce `APP_LLM_MAX_INPUT_CHARS`.
- `input_too_large`: split the PDF or raise the cap if the model context
  allows it.
