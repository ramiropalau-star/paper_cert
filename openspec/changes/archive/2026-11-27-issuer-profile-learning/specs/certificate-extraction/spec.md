# Spec Delta

## ADDED Requirements

### Requirement: Issuer and certificate-type pre-detection

The system SHALL run a deterministic pre-detection pass before extraction to identify the likely certifying entity, certificate type or exam, and language from document text, active aliases, format anchors, and verifier domains. It SHALL return a confidence and margin, and SHALL return an ambiguous result without forcing an issuer when either is below threshold. A bounded classifier fallback MAY run only when enabled and the deterministic result is ambiguous.

#### Scenario: Clear issuer is detected

- **WHEN** the document text and profile anchors strongly match one issuer and certificate type
- **THEN** pre-detection returns that issuer, type, confidence, and margin
- **AND** extraction proceeds with that issuer's profile

#### Scenario: Ambiguous detection does not force an issuer

- **WHEN** two issuers or certificate types score within the configured margin
- **THEN** pre-detection returns an ambiguous result
- **AND** extraction uses the global instruction without issuer-specific negative evidence

#### Scenario: Classifier fallback is optional and bounded

- **WHEN** deterministic pre-detection is ambiguous and a classifier fallback is enabled
- **THEN** at most one bounded classifier call may refine the result
- **AND** its output is recorded with the pre-detection result

#### Scenario: Pre-detection does not mutate the document

- **WHEN** pre-detection runs
- **THEN** no certificate fields or processing state change before extraction completes

### Requirement: Profile-guided extraction pass

After pre-detection, the system SHALL build the extraction instruction with the detected issuer's active learned labels, value shapes, and anonymized exemplars, and SHALL run a deterministic candidate pre-pass for labels, scores, and dates. The model SHALL validate candidates with verbatim evidence; values without evidence SHALL NOT be stored as verified. With no detected issuer, the global instruction SHALL be used.

#### Scenario: Issuer labels are used in the prompt

- **WHEN** the detected issuer has active learned labels
- **THEN** the extraction instruction includes those labels and expected value shapes
- **AND** the model validates the label-value candidates with verbatim quotes

#### Scenario: Candidate without evidence is not verified

- **WHEN** a candidate value cannot be supported by verbatim document text
- **THEN** the value is kept only as unverified or left empty
- **AND** it is not treated as a verified extraction

#### Scenario: Global fallback remains available

- **WHEN** no issuer is detected or no active profile exists
- **THEN** extraction uses the global instruction and global aliases

### Requirement: Post-extraction issuer consistency check

After classification, the system SHALL compare the resolved entity and exam with the pre-detection result. When they differ, it SHALL record an `entity_mismatch` reason and MAY re-run extraction at most once with the resolved issuer's profile. The re-run SHALL be bounded and SHALL pass the same evidence validation; it SHALL NOT loop or auto-approve.

#### Scenario: Mismatch is flagged

- **WHEN** the resolved entity differs from the pre-detected entity
- **THEN** the certificate records an `entity_mismatch` review reason
- **AND** the reviewer sees both the pre-detected and resolved values

#### Scenario: One bounded re-run with the resolved profile

- **WHEN** the mismatch is material and the resolved issuer has an active profile
- **THEN** extraction may run once more with that profile
- **AND** no further automatic re-runs occur for the same document

#### Scenario: Ambiguous pre-detection does not trigger a mismatch

- **WHEN** pre-detection returned an ambiguous result
- **THEN** no `entity_mismatch` reason is created solely from that ambiguity

### Requirement: Per-run extraction metadata

The system SHALL record for each extraction run the model name, prompt version, profile version, pre-detection result and confidence, pass count, fallback use, and latency. Review SHALL expose this metadata in a secondary detail so a result can be traced to the configuration that produced it.

#### Scenario: Metadata is stored with the run

- **WHEN** extraction completes
- **THEN** the run records its model, prompt, profile, pre-detection, pass count, fallback use, and latency

#### Scenario: Reviewer inspects run metadata

- **WHEN** a reviewer opens the extraction details
- **THEN** the screen shows the model, prompt, profile, and pre-detection versions used

### Requirement: Bounded fallback-model escalation

When critical fields remain missing after the primary extraction and deterministic fallbacks, the system MAY call a configured fallback model at most once, scoped to the missing fields, and SHALL validate its output with the same schema and evidence rules. The fallback SHALL be recorded in the run metadata.

#### Scenario: Fallback runs only for missing critical fields

- **WHEN** score or dates remain missing after the primary pass and fallbacks
- **THEN** at most one fallback-model request asks only for those fields
- **AND** its values pass the same evidence validation before storage

#### Scenario: Complete extraction skips the fallback

- **WHEN** the primary extraction already produced verified critical fields
- **THEN** no fallback-model request is made

#### Scenario: Fallback failure is recorded

- **WHEN** the fallback model is unavailable or returns invalid output
- **THEN** the document continues with the primary result
- **AND** the failure is recorded in the run metadata
