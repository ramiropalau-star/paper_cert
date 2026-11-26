# Design

## Context

See proposal.md — Why. Date flow today: model returns `dates` candidates
(text/role/page/quote) → `_validate_evidence` drops candidates whose quote
isn't verbatim → fallbacks (`_fallback_issue_date`) run only when no issue
date exists → `classification.apply_dates` parses each candidate via
`parse_date_text` (strptime EN formats + `dateutil`, both English-centric)
into `issue_date`/`exam_date`/`result_date`/`detected_date`.

Observed failures: "18 Setembre 2026" unparsed (Catalan), trilingual block
near signature never harvested, OCR-garbled labels invisible to fallback,
model over-assigns role `exam`.

## Goals / Non-Goals

Goals:

- Parse named-month dates in CA/ES/EN/FR/DE/PT/IT.
- Never silently drop a date-like candidate: unparseable → `detected_date`
  + `ambiguous_date` reason.
- Harvest label-less dates deterministically as `unknown` role.
- Keep noise out: birth dates, implausible years, duplicates.

Non-goals:

- Perfect role assignment (issue vs exam vs result) — `unknown` → review
  is the honest fallback; better role heuristics only via nearby labels.
- OCR repair of garbled labels (out of scope; harvest still catches the
  date pattern itself even if the label is corrupt).
- Backfilling historical certificates (re-extract is available per doc).

## Decisions

### D1: Month-name map, not locale hacking

A module-level `MONTH_NAMES` dict mapping folded month names + common
abbreviations (gener, febr, mär, märz, avr, mai, jui, juil, août, sep,
set, oct, nov, des, dic, dez, enero..diciembre, etc.) to month numbers,
keyed through `_norm_text` folding. `parse_date_text` gains a branch: if
the text matches `day + monthname + year` (any order variant seen in the
wild: "18 Setembre 2026", "Setembre 18, 2026"), construct the date directly
instead of relying on `dateutil`. `MONTH_NAME` in classification becomes
generated from the same map so `_looks_like_date` covers all languages.

Alternative considered: `locale.setlocale` per document — rejected,
process-global state, fragile in containers, doesn't cover mixed-language
documents anyway.

### D2: Harvest as a separate pass after model + existing fallbacks

`_harvest_dates(page_texts) -> list[DateCandidate]`: regex-scan each page
for (a) numeric dates `d/m/y`, `d-m-y`, ISO, (b) `day monthname year` and
`monthname year` patterns. Each match becomes a candidate only if its
parsed date isn't already represented in `payload.dates` (dedupe by parsed
value AND by normalized text). Role assignment: `unknown` by default;
upgrade to `issue`/`exam`/`result` only when a multilingual label appears
within ~80 chars before the match (reusing an extended label regex).

Exclusions: line contains birth markers (`birth`, `nacimiento`,
`naixement`, `geburtsdatum`, `data de naixement`, `date of birth`,
`né le`, `nascita`); parsed year <1900 or >2100; day/month implausible.

Merged into `payload.dates` after `_merge_focus`, before `_persist_certificate`,
marked via the existing unverified/ambiguous machinery (role unknown →
`detected_date` + `ambiguous_date` reason downstream — no new plumbing).

### D3: Extend `_ISSUE_DATE_LABEL_RE` multilingual

Add CA/FR/DE/PT/IT issue-label stems: `expedici`, `emissi`, `data d'emissió`,
`fecha de expedici`, `relevé`, `ausgestellt`, `rilascio`, `data di
rilascio`, `issue`, `exped`, `awarded`, `darrera`. Same 120-char window
logic.

### D4: Prompt tweak, minimal

One added bullet in the dates guidance: month names may appear in any
language present in the document; dates adjacent to signature/issuer blocks
are usually issue dates. `PROMPT_VERSION` bumps (coordinate with the
field-label-aliases change — whichever lands second takes the next version).

## Risks / Trade-offs

- [Harvest adds noise → more ambiguous_date reviews] → dedupe + birth/year
  guardrails + role only via labels; ambiguous dates already route to human
  review which is the designed path.
- [Month-name false positives in prose] → require day+month+year or
  month+year shape, not bare month names.
- [dateutil still used for EN formats] → multilingual branch runs first;
  EN behavior unchanged.
- [Harvested candidate quote fails evidence validation] → harvested
  candidates carry the matched line as quote; `_validate_evidence` for dates
  drops unverifiable quotes — harvest inserts AFTER validation, using the
  raw page text as quote, so it always verifies by construction.

## Migration Plan

Code-only; no schema changes. Deploy restarts workers; in-flight docs
re-extract on demand. Rollback = revert.

## Open Questions

- Whether harvested `unknown` dates should also feed `detected_date`
  directly at extraction time vs waiting for classification — design
  assumes classification's `apply_dates` handles it (it does).
