# Spec Delta

## ADDED Requirements

### Requirement: Pages retain layout data for format learning

For PDF documents, the system SHALL store per-page layout data alongside the
extracted text — including text line positions and image regions — so that
downstream format learning can use positional and structural signals. Layout
capture SHALL be best-effort: documents without a usable layout (scans,
unsupported PDFs) SHALL still be ingested with text only, and layout SHALL
NOT block ingestion.

#### Scenario: PDF page layout is stored

- **WHEN** a PDF page is ingested
- **THEN** its text lines are stored with positional information and its
  image regions are recorded

#### Scenario: Scan without text layer still ingests

- **WHEN** a scanned page has no extractable text or layout
- **THEN** the document is ingested normally with OCR text and no layout
  data

### Requirement: Embedded text is cleaned before downstream use

Text extracted from the embedded PDF text layer SHALL be normalized before it
is stored or used for extraction and format learning: ligatures and common
encoding artifacts SHALL be repaired where reliably detectable, and obvious
pipeline metadata SHALL be excluded from the text used for anchor
candidacy. Cleaning SHALL be conservative — it SHALL NOT alter text that is
already well-formed.

#### Scenario: Corrupted embedded text is repaired

- **WHEN** the embedded text layer contains known corruption patterns
  (ligatures, concatenated words, encoding artifacts)
- **THEN** the stored text uses the repaired form when the repair is
  unambiguous

#### Scenario: Clean text is left untouched

- **WHEN** the embedded text is already well-formed
- **THEN** stored text is unchanged apart from standard normalization
