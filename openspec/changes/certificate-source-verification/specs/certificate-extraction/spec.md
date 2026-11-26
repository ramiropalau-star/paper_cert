# Spec Delta

## ADDED Requirements

### Requirement: Extraction captures verification artifacts

Extraction SHALL capture the issuer verification code and verification URL
when present on the document, using deterministic label-anchored patterns
("Cod. Verificació", "Verification Number", "CSV", "URL Verif", verifier
links) across the certificate languages in use, and SHALL store them on the
certificate for review display.

#### Scenario: Labeled code captured deterministically

- **WHEN** the document prints "Cod. Verificació: H480BGXM95JWD2R2"
- **THEN** the certificate stores that code without relying on the model

#### Scenario: Model-assisted capture for unlabeled values

- **WHEN** a verification number appears without a clear label but the
  model identifies it with evidence
- **THEN** the value is stored and evidence-validated like other fields
