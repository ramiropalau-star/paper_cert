# ocr-processing Specification

## Purpose
Defines how the OCR service turns document pages into text and confidence with one recognition pass and bounded time budgets.

## Requirements

### Requirement: Each page is recognized once

The OCR service SHALL perform exactly one text-recognition pass per scanned page. It SHALL NOT run a second OCR engine or a second pass over the same page solely to obtain confidence. The response SHALL use the single pass for page text and confidence.

#### Scenario: Single pass per scanned page
- **WHEN** the service receives a scanned two-page PDF
- **THEN** each page is recognized once
- **AND** the response contains text and confidence for both pages

#### Scenario: No duplicate OCR work
- **WHEN** the service processes a page
- **THEN** it does not invoke a second OCR engine for that page

### Requirement: Per-page and total timeouts are separate

The OCR service SHALL enforce a per-page timeout and a separate total request timeout. A multi-page document SHALL complete when each page finishes within the per-page budget and the whole request finishes within the total budget.

#### Scenario: Multi-page document completes
- **WHEN** a five-page document takes less than the per-page timeout on each page and less than the total timeout overall
- **THEN** the service returns all five pages

#### Scenario: Page timeout is reported
- **WHEN** a page exceeds the per-page timeout
- **THEN** the service returns a structured error identifying the page and marking it retryable
- **AND** it does not silently drop the page

#### Scenario: Total timeout is distinct
- **WHEN** the total request exceeds the total timeout
- **THEN** the service returns a structured total-timeout error
- **AND** the error is distinguishable from a per-page timeout

### Requirement: The OCR response contract is stable

The service SHALL preserve the versioned response fields for page number, text, method, confidence, mean confidence, quality, contract version, and engine metadata. The same input and engine configuration SHALL produce the same field semantics after the single-pass change.

#### Scenario: Existing client contract remains valid
- **WHEN** the Django OCR client parses a response
- **THEN** all existing fields are present with their previous types and meanings

#### Scenario: Engine metadata reflects the single pass
- **WHEN** the service reports engine metadata
- **THEN** it identifies the recognizer actually used for the page text
- **AND** it does not claim a second engine contributed

### Requirement: Temporary rendering artifacts are cleaned up

The OCR service SHALL remove temporary page images and intermediate files after the request completes, including when recognition or timeout handling fails.

#### Scenario: Artifacts are removed on success
- **WHEN** a request completes successfully
- **THEN** its temporary page images are removed

#### Scenario: Artifacts are removed on failure
- **WHEN** a request fails or times out
- **THEN** its temporary page images are removed
