# Design

## Context

See proposal.md — Why. Real documents show heterogeneous verification:
CSV+URL GET-verifiable (GVA/tramita), web-form portals (Cambridge
verifiers, Oxford go.oup.com, UV seu.uv.es), pre-verified marks ("VERIFICADO
Y CONFORME"), and none. The pipeline already stores page text, so
deterministic harvest is feasible for labeled codes/URLs.

## Goals / Non-Goals

Goals:

- Always capture code + URL when printed (deterministic first).
- Honest status model distinguishing self-reported vs actually verified.
- Automated check ONLY where a known programmatic pattern exists.
- Manual confirm path with audit for everything else.

Non-goals:

- Scraping JS portals (Cambridge/Oxford/UV verifiers) — fragile, out of
  scope; manual confirm covers them.
- Verifying signature cryptographic validity (UV's `Cod. Verificació` may
  be signed — deeper integration is a future change).
- Blocking approval on verification status (informational, not a gate).

## Decisions

### D1: Fields on Certificate

`verification_code` (str), `verification_url` (str),
`verification_status` (choices: none/self_reported/verified_at_source/
manually_confirmed), `verified_by` (FK User null), `verified_at` (datetime
null), `verification_evidence` (JSON: matched line, method, http status,
timestamp). Migration only.

### D2: Deterministic harvest in extraction

`documents/services/verification.py`: label-anchored regexes over page
texts — patterns for `CSV <code>`, `Cod. Verificació|Código de
verificaci|Verification (Number|Code)|código` + URL regexes
(`https?://` near "verif"/"csv"/issuer domains). Runs inside
`extract_certificate` after date harvest; results merged into payload
persistence. Also feeds the `self_reported` status whenever code or URL
found.

Model-assisted path: optional `verification_code`/`verification_url`
FieldValue entries in the extraction schema — deferred unless deterministic
coverage proves insufficient (keeps schema stable).

### D3: Verifier registry, CSV-family first

`verifiers.py`: `Verifier` protocol `verify(code, url) ->
VerificationOutcome(ok, detail, evidence)`. v1 implements the CSV pattern:
code shape `XXXX-XXXX-XXXX-XXXX` (or issuer-specific) + URL on a known
verifier domain → GET the URL (bounded timeout, no JS) and check response
for success markers. Registry keyed by URL domain; unknown domains → no
auto attempt. Async/sync: run inline with tight timeout (5s) post-extract,
failure never blocks the pipeline.

Alternative considered: headless browser per portal — rejected (heavy,
fragile, maintenance per issuer redesign).

### D4: Manual confirm in review

POST endpoint on document detail (reviewer+): sets
`manually_confirmed`, `verified_by`, `verified_at`; unconfirm reverses
status keeping `verified_by/at` history in `verification_evidence` or
ReviewEvent. Badge component in detail.html + optional column/filter in
documents table.

### D5: QR — phase 2, optional

PDFs may embed QR images. Detection via `pypdfium2` render + `pyzbar`
(optional dep, already-rendered pages exist). If the dep is undesirable,
ship without QR in v1 (spec marks it MAY). Decision left to tasks: try
pyzbar; if install is clean, include; else defer.

## Risks / Trade-offs

- [GET verifier returns JS app shell, not result] → treat non-2xx or
  missing success marker as `unreachable`/`self_reported`, never verified.
- [Codes printed but URL missing] → store code, status self_reported,
  reviewer uses portal manually.
- [Harvest false positives on "code"] → require label anchor AND plausible
  code charset/length; evidence line stored for audit.
- [SSRF-ish: verification_url fetched server-side] → only fetch URLs on an
  allowlist of known verifier domains; never arbitrary document URLs.

## Migration Plan

Migration adds fields (all nullable/defaults). Deploy; existing certs get
`none` until re-extracted or manually confirmed. Rollback = revert.

## Open Questions

- Exact CSV endpoint contract for tramita.gva.es (needs a live probe during
  implementation — task includes it).
- Whether UV's verification code is cryptographically verifiable offline —
  investigate during implementation; likely future change.
