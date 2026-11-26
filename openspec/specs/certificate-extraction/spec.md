# certificate-extraction Specification

## Purpose
Turn extracted document text into structured certificate data using a local language model, capturing only what the document states and routing uncertain or incomplete results to human review.

## Requirements

### Requirement: Structured extraction through a local model
The system SHALL send the acquired document text to the locally hosted Ollama model with a structured extraction instruction and SHALL require the response to conform to a defined JSON schema.

#### Scenario: Valid structured response stored
- **WHEN** the model returns a response that conforms to the extraction schema
- **THEN** the system stores the extracted fields with the document record
- **AND** the record becomes available for classification

#### Scenario: Model unavailable
- **WHEN** Ollama is unreachable during extraction
- **THEN** the document is marked with a processing error that is visible to the user
- **AND** the document can be reprocessed later without creating a duplicate record

### Requirement: Extract only information present in the document
The system SHALL extract values that appear in the certificate and SHALL NOT infer, complete, or fabricate missing data.

#### Scenario: Missing field stays absent
- **WHEN** a requested field does not appear in the document text
- **THEN** the field is stored as absent
- **AND** the system does not fill it with a plausible guess

#### Scenario: No cross-exam inference
- **WHEN** the document contains a score but no stated equivalent level
- **THEN** the system does not derive or assign a level from that score

### Requirement: Capture source evidence and confidence
The system SHALL retain, for each extracted field where possible, the document text that supports it, and SHALL record an extraction confidence value.

#### Scenario: Evidence stored per field
- **WHEN** a field value is extracted from the document
- **THEN** the supporting document text is stored alongside the extracted value when it can be identified

#### Scenario: Low confidence recorded
- **WHEN** the model reports low confidence for the extraction or for an individual field
- **THEN** that confidence is stored with the record
- **AND** the record is routed to review according to the review rules

### Requirement: Validate model output and retry within bounds
The system SHALL validate every model response against the extraction schema and SHALL retry invalid responses only a bounded number of times.

#### Scenario: Invalid response retried
- **WHEN** the model response is not valid JSON or does not match the schema
- **THEN** the system retries the extraction a limited configured number of times

#### Scenario: Retries exhausted
- **WHEN** every allowed attempt returns an invalid response
- **THEN** the document is marked for review with the validation failure recorded
- **AND** the system does not store partially valid schema data as a successful extraction

### Requirement: Extract the required certificate field set
The system SHALL extract, when present, student name, language, certifying entity as printed, exam or certificate name, literal level, literal score or result, issue date, certificate number, exam or result date when distinct, and relevant OCR text supporting the data.

#### Scenario: Complete certificate extracted
- **WHEN** a certificate contains all required fields
- **THEN** each field is stored with its extracted value
- **AND** literal level and literal score are stored as separate fields

#### Scenario: Optional identifier captured
- **WHEN** a certificate displays a certificate number or code
- **THEN** the system stores it as a value without asserting that it was externally verified

### Requirement: Recognize non-certificate documents
The system SHALL determine whether a document appears to be a language certificate and SHALL route documents that do not appear to be certificates away from normal report inclusion.

#### Scenario: Non-certificate document flagged
- **WHEN** the extracted content does not appear to be a language certificate
- **THEN** the document is marked accordingly and sent to review
- **AND** it is excluded from the main Excel report

### Requirement: Route uncertain extractions to review
The system SHALL send a record to manual review when an essential field is missing, a date cannot be assigned to a category, confidence is low, or the document appears to contain more than one certificate.

#### Scenario: Missing essential field
- **WHEN** an essential field such as student, language, entity, level or score, or issue date is absent
- **THEN** the record is marked pending review

#### Scenario: Ambiguous date
- **WHEN** the document shows a single date whose category as issue, exam, or result date cannot be determined
- **THEN** the date is stored as a detected date without a definitive category
- **AND** the record is marked pending review

#### Scenario: Multiple certificates suspected
- **WHEN** the text suggests the file contains more than one certificate
- **THEN** the system does not silently merge or discard data
- **AND** the record is marked pending review for manual splitting or correction

### Requirement: Preserve literal values from the document
The system SHALL keep literal values for level, score, entity, and dates as printed, instead of replacing them with normalized values.

#### Scenario: Literal level retained
- **WHEN** a certificate prints a level in a national or exam-specific scale
- **THEN** the literal level text is stored unchanged
- **AND** any normalized CEFR value is stored in a separate field

### Requirement: Unverifiable evidence retains the value flagged as unverified

When a literal field's evidence quote cannot be verified verbatim on the cited
page, the system SHALL keep the extracted value, mark that field as unverified,
and continue the extraction instead of rejecting the whole result. Fields whose
evidence verifies normally SHALL remain verified. The unverified mark SHALL be
persisted per field and cleared when a reviewer edits or explicitly confirms
the field.

#### Scenario: Single bad quote no longer fails extraction

- **WHEN** the model returns a complete extraction where one literal field's
  evidence quote does not appear on its cited page
- **THEN** the extraction completes and stores all returned values
- **AND** only the offending field is marked unverified
- **AND** the document proceeds to classification and review

#### Scenario: Unverified mark survives to review

- **WHEN** a certificate has fields marked unverified
- **THEN** the review UI shows which fields are unverified
- **AND** editing or confirming a field clears its unverified mark

#### Scenario: Verified fields are unaffected

- **WHEN** every literal field's evidence quote verifies on its cited page
- **THEN** no field is marked unverified

### Requirement: Deterministic fallback fills empty score and dates

When the model returns an empty score or no date candidates, the system SHALL
attempt a deterministic label/regex pass over the stored page text to fill them,
using the same fallback pattern as the student-name recovery. Fallback-derived
values SHALL be marked unverified.

#### Scenario: Score recovered from page text

- **WHEN** the model omits the score but the page text contains a recognizable
  score pattern (e.g. `80 /100`, `Score: 89`)
- **THEN** the score field is populated from the matched text and marked
  unverified

#### Scenario: Issue date recovered from page text

- **WHEN** the model returns no usable date candidates but the page text contains
  a recognizable date near a date label
- **THEN** the issue date is populated from the matched text and marked
  unverified

#### Scenario: Nothing found stays empty

- **WHEN** neither the model nor the deterministic pass finds a score or date
- **THEN** the field remains empty and no unverified mark is added

### Requirement: Focused second pass recovers missing critical fields

When the primary extraction leaves critical fields (score or dates) empty after
fallbacks, the system SHALL issue at most one bounded follow-up extraction
request scoped to the missing fields, requiring verbatim quotes. The second pass
SHALL NOT run when the primary extraction already produced verified values for
those fields, and its results SHALL pass the same evidence validation.

#### Scenario: Second pass runs only on gaps

- **WHEN** the primary extraction plus fallbacks still lacks a score or issue
  date
- **THEN** exactly one follow-up request asks only for the missing fields
- **AND** returned values are validated against page evidence before storing

#### Scenario: Happy path skips the second pass

- **WHEN** the primary extraction already yields verified score and dates
- **THEN** no follow-up request is made

### Requirement: Reviewers can re-extract a document directly

The system SHALL provide a reviewer-facing action that re-runs extraction for a
single document without depending on the external ingestion webhook. The action
SHALL be idempotent, SHALL preserve manually entered fields, and SHALL record a
review event describing the re-extraction.

#### Scenario: Manual re-extract bypasses the webhook

- **WHEN** a reviewer triggers re-extraction on a document whose pipeline is
  stuck or whose extraction missed fields
- **THEN** extraction runs against the stored page texts directly
- **AND** the document returns to the appropriate processing state on success

#### Scenario: Manual fields are preserved

- **WHEN** re-extraction runs on a certificate with fields in `manual_fields`
- **THEN** those fields are not overwritten by the new extraction

### Requirement: Dates with month names parse in supported languages

The system SHALL parse dates whose month is written as a name or
abbreviation in Catalan, Spanish, English, French, German, Portuguese, or
Italian (e.g. "18 Setembre 2026", "18 Septiembre 2026", "5 décembre 2020",
"3 März 2021"). Candidates containing such dates SHALL NOT be silently
dropped: when the full value cannot be normalized they SHALL surface as
ambiguous date evidence for review.

#### Scenario: Catalan month name parses

- **WHEN** a candidate text contains "18 Setembre 2026"
- **THEN** the system parses it as 2026-09-18 (or the entity-ordered
  equivalent) instead of discarding it

#### Scenario: Trilingual repeated date collapses to one candidate

- **WHEN** the document prints "18 Setembre 2026 · 18 Septiembre 2026 ·
  18 September 2026" for the same date
- **THEN** harvesting produces a single date candidate, not three

#### Scenario: Unparseable date-like text stays visible

- **WHEN** a candidate mentions a month name but no parseable day/year
  (e.g. "SEPTIEMBRE 2020")
- **THEN** it is retained as ambiguous date evidence and triggers the
  ambiguous-date review reason

### Requirement: Deterministic date harvesting covers label-less dates

When model extraction returns few or no date candidates, the system SHALL
scan the stored page texts for date-like patterns regardless of nearby
labels and add missing candidates with role `unknown`, so dates printed
beside signatures or in unlabeled blocks are not lost. Harvested candidates
SHALL be deduplicated against model-returned candidates by parsed value.

#### Scenario: Label-less issue block is harvested

- **WHEN** the model returns no dates but page text contains "18 Setembre
  2026 · 18 Septiembre 2026 · 18 September 2026" near the signature block
- **THEN** a date candidate is added with role `unknown` and the document
  routes to review with the ambiguous-date reason rather than losing the
  date entirely

#### Scenario: Harvest respects birth-date exclusions

- **WHEN** a date-like pattern appears on a line containing birth/nacimiento/
  naixement/Geburtsdatum markers
- **THEN** the harvester does not add it as a certificate date candidate

#### Scenario: Implausible years are rejected

- **WHEN** a harvested pattern yields a year outside a sane certificate
  range (e.g. "0399")
- **THEN** it is not added as a date candidate

### Requirement: Student names exclude honorifics and titles

Extracted `student_name` values SHALL NOT include leading honorifics or
titles. The system SHALL strip leading title tokens from a curated
multilingual list covering the certificate languages in use, preserve
titles inside the name, and SHALL NOT strip tokens that can be legitimate
given names or initials.

#### Scenario: Spanish honorific stripped

- **WHEN** the document prints "Doña María González Pérez" as the student
  name
- **THEN** `student_name` stores "María González Pérez"

#### Scenario: French treatment stripped

- **WHEN** the document prints "Mme Claire Martin" as the student name
- **THEN** `student_name` stores "Claire Martin"

#### Scenario: German title stripped

- **WHEN** the document prints "Frau Anna Schmidt" as the student name
- **THEN** `student_name` stores "Anna Schmidt"

#### Scenario: Ambiguous token preserved

- **WHEN** the extracted name begins with a token that can be a real given
  name or initial (e.g. "Don Pablo Rivera" where "Don" is part of the
  registered name)
- **THEN** the system does not strip the token and stores the name as
  printed

#### Scenario: Title inside the name preserved

- **WHEN** the name is "María de los Ángeles Pérez"
- **THEN** no token is removed because none is a leading honorific

#### Scenario: Stripping is auditable

- **WHEN** stripping changes the extracted value
- **THEN** the original value remains recoverable from stored evidence or
  extraction metadata for audit

### Requirement: Extraction incorporates configured field label aliases

When building the extraction instruction and running deterministic field
fallbacks, the system SHALL include the active field label aliases that
apply to the document: all global aliases for the field, plus aliases
scoped to the document's resolved entity when the document has already been
classified. Aliases SHALL be presented to the model as additional label
examples for their field and SHALL extend fallback label matching without
weakening verbatim-evidence validation.

#### Scenario: Global alias appears in the extraction instruction

- **WHEN** an active global alias exists for the student name field
- **THEN** the extraction instruction lists it as an additional label
  example for that field

#### Scenario: Entity-scoped alias applies after classification

- **WHEN** a document is reprocessed after classification and an active
  alias is scoped to its resolved entity
- **THEN** the extraction for that document includes the scoped alias

#### Scenario: Unclassified document uses global aliases only

- **WHEN** a document has no resolved entity yet (first extraction pass)
- **THEN** only global aliases are applied; entity-scoped aliases are not
  used

#### Scenario: Alias-derived values still require evidence

- **WHEN** a value is recovered through an alias
- **THEN** it carries evidence from the document text like any other
  extracted value, and unverifiable evidence still marks the field
  unverified rather than discarding the value

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
