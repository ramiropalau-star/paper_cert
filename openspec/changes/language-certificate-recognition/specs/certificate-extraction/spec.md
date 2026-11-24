# Spec Delta

## Purpose

Turn extracted document text into structured certificate data using a local language model, capturing only what the document states and routing uncertain or incomplete results to human review.

## ADDED Requirements

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
