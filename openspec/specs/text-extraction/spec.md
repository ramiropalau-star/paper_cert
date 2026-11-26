# text-extraction Specification

## Purpose
Obtain usable text from every uploaded page by using embedded PDF text when sufficient and OCR otherwise, while recording how the text was produced and flagging unusable input for manual review.

## Requirements

### Requirement: Prefer embedded PDF text
The system SHALL use the text already embedded in a PDF when that text is sufficient, and SHALL record that embedded text was the source.

#### Scenario: Text-based PDF skips OCR
- **WHEN** a PDF contains a sufficient amount of extractable text
- **THEN** the system uses the embedded text for AI extraction
- **AND** the document records the method as embedded PDF text
- **AND** OCR is not executed for that document

#### Scenario: Sufficiency threshold applied
- **WHEN** the embedded text of a PDF falls below the configured minimum amount of usable characters
- **THEN** the system treats the document as lacking usable embedded text and proceeds to OCR

### Requirement: Fall back to OCR when text is insufficient
The system SHALL run OCR on a PDF when it has no usable embedded text, consists of scanned pages, or contains pages without sufficient text.

#### Scenario: Scanned PDF uses OCR
- **WHEN** a PDF is composed of scanned images or otherwise lacks usable embedded text
- **THEN** the system runs OCR over the document before sending text to the AI extraction stage
- **AND** the document records the method as OCR

#### Scenario: Mixed-content PDF processes all pages
- **WHEN** a PDF contains some pages with embedded text and others that require OCR
- **THEN** the system obtains text for every page, running OCR only where needed

### Requirement: OCR supported images and multi-page documents
The system SHALL apply OCR directly to supported images and SHALL process every page of multi-page documents.

#### Scenario: Supported image OCR
- **WHEN** a JPG, JPEG, PNG, or TIFF image is processed
- **THEN** the system runs OCR on it and produces text for AI extraction

#### Scenario: Multi-page document fully processed
- **WHEN** a PDF or multi-page TIFF contains more than one page
- **THEN** the system extracts and combines text from all pages in page order
- **AND** no page is silently skipped

### Requirement: Record text acquisition provenance
The system SHALL record, for each processed document, whether text came from embedded PDF text or from OCR, and SHALL relate any generated OCR copy to its original.

#### Scenario: Provenance exposed to users
- **WHEN** a user views a processed document
- **THEN** the interface clearly indicates whether the text was obtained from the PDF or through OCR

#### Scenario: OCR copy linked to original
- **WHEN** the system generates an OCR-processed copy of a document
- **THEN** that copy is stored in relation to the original file
- **AND** the original remains available and unchanged

### Requirement: Flag unusable input for manual review
The system SHALL mark a document for manual review when its text is blurry, rotated, incomplete, or too scarce for reliable extraction.

#### Scenario: Insufficient OCR result routed to review
- **WHEN** OCR or embedded-text extraction yields text below the configured usefulness threshold
- **THEN** the document is marked for manual review with the reason
- **AND** the document is not presented as successfully extracted

#### Scenario: Review retains the original
- **WHEN** a document is flagged for manual review because its text is unusable
- **THEN** the original file remains accessible to the reviewer

### Requirement: OCR stage is independently configurable
The system SHALL keep OCR configurable and separate from AI extraction, including the OCR languages used, and SHALL allow the OCR engine to be replaced without altering AI extraction, classification, review, or reporting behavior.

#### Scenario: OCR languages configured
- **WHEN** an administrator configures one or more OCR languages in the environment configuration
- **THEN** subsequent OCR runs use those languages without requiring application code changes

#### Scenario: OCR engine substitution
- **WHEN** the configured OCR engine is replaced with another engine that produces text for the supported formats
- **THEN** the downstream extraction, classification, review, and reporting behavior remains unchanged
