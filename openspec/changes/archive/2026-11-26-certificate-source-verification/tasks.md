# Tasks

## 1. Data model

- [x] 1.1 Add `verification_code`, `verification_url`,
  `verification_status`, `verified_by`, `verified_at`,
  `verification_evidence` to `Certificate` + migration. Verify migrate
  clean and defaults (`none`) on existing rows.

## 2. Deterministic capture

- [x] 2.1 Create `documents/services/verification.py` with label-anchored
  harvesters: CSV-style code+URL, "Cod. Verificació"/"Verification
  Number"/"código" codes, verifier-domain URLs; multilingual labels. Verify
  with fixture texts from real docs (51, 43, 44, 40).
- [x] 2.2 Wire harvest into `extract_certificate` persist path; set
  `self_reported` when artifacts found. Verify re-extract of doc 51 stores
  code+URL.

## 3. Automated verification (CSV pattern)

- [x] 3.1 Probe tramita.gva.es CSV verification endpoint live; document
  request/response contract in design or code comment. Verify with a real
  code from doc 51.
- [x] 3.2 Implement verifier registry + CSV-family GET verifier with
  domain allowlist, 5s timeout, success-marker check; wire post-extract.
  Verify: matching code → `verified_at_source`; bad/unreachable →
  `self_reported` + recorded failure.

## 4. Review UI

- [x] 4.1 Verification panel on `detail.html`: status badge, code, clickable
  URL, verified_by/at for manual. Verify renders for all statuses.
- [x] 4.2 Confirm/unconfirm POST endpoint (reviewer+, audit via
  ReviewEvent). Verify role enforcement and history.
- [x] 4.3 Optional: status filter/column in documents table. Verify filter
  works.

## 5. QR (optional)

- [x] 5.1 ~~Evaluate pyzbar~~ SKIPPED: pyzbar requires the native `libzbar`
  system package which is not in the image, and the issuers in scope
  (UV, Cambridge, Oxford, GVA, Trinity, KMK) publish code+URL
  verification rather than QR payloads. Revisit if a QR-bearing issuer
  appears.

## 6. Verification

- [x] 6.1 Run test suite; `openspec validate certificate-source-verification
  --strict`.
