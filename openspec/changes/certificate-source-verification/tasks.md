# Tasks

## 1. Data model

- [ ] 1.1 Add `verification_code`, `verification_url`,
  `verification_status`, `verified_by`, `verified_at`,
  `verification_evidence` to `Certificate` + migration. Verify migrate
  clean and defaults (`none`) on existing rows.

## 2. Deterministic capture

- [ ] 2.1 Create `documents/services/verification.py` with label-anchored
  harvesters: CSV-style code+URL, "Cod. Verificació"/"Verification
  Number"/"código" codes, verifier-domain URLs; multilingual labels. Verify
  with fixture texts from real docs (51, 43, 44, 40).
- [ ] 2.2 Wire harvest into `extract_certificate` persist path; set
  `self_reported` when artifacts found. Verify re-extract of doc 51 stores
  code+URL.

## 3. Automated verification (CSV pattern)

- [ ] 3.1 Probe tramita.gva.es CSV verification endpoint live; document
  request/response contract in design or code comment. Verify with a real
  code from doc 51.
- [ ] 3.2 Implement verifier registry + CSV-family GET verifier with
  domain allowlist, 5s timeout, success-marker check; wire post-extract.
  Verify: matching code → `verified_at_source`; bad/unreachable →
  `self_reported` + recorded failure.

## 4. Review UI

- [ ] 4.1 Verification panel on `detail.html`: status badge, code, clickable
  URL, verified_by/at for manual. Verify renders for all statuses.
- [ ] 4.2 Confirm/unconfirm POST endpoint (reviewer+, audit via
  ReviewEvent). Verify role enforcement and history.
- [ ] 4.3 Optional: status filter/column in documents table. Verify filter
  works.

## 5. QR (optional)

- [ ] 5.1 Evaluate pyzbar on rendered pages; if clean, decode QR payloads
  into `verification_evidence`. Verify with a QR-bearing fixture; else mark
  task skipped with reason.

## 6. Verification

- [ ] 6.1 Run test suite; `openspec validate certificate-source-verification
  --strict`.
