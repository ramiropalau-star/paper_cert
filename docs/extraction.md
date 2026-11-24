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

Pull the model once with `ollama pull <model>` (see `docs/operations.md`).

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
