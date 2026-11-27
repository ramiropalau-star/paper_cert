# Spec Delta

## MODIFIED Requirements

### Requirement: Documents table offers quick document preview

The documents list SHALL show a lazy-loaded inline thumbnail for each document
that has an original, without requiring a click to reveal it. Activating the
thumbnail SHALL open the review detail. A separate zoom action SHALL open the
document in a modal overlay for enlargement, using the same rendered source as
the gallery view. The modal SHALL be dismissible via close control, backdrop
click, and keyboard, and SHALL NOT interfere with row navigation or existing
filters.

#### Scenario: Thumbnail is visible without a click

- **WHEN** the documents list renders a document with an original
- **THEN** its thumbnail is visible in the row
- **AND** no preview action is required to reveal it

#### Scenario: Thumbnail opens the review detail

- **WHEN** a reviewer activates a document thumbnail
- **THEN** the review detail for that document opens

#### Scenario: Preview opens from the list

- **WHEN** a reviewer activates the preview action on a document row
- **THEN** a modal shows the document render at a readable size
- **AND** closing it returns to the unchanged list with filters preserved

#### Scenario: Zoom opens the document overlay

- **WHEN** a reviewer activates the separate zoom action
- **THEN** a modal shows the document at a readable size
- **AND** closing it returns to the unchanged list with filters preserved

#### Scenario: Preview is keyboard accessible

- **WHEN** a reviewer opens the zoom overlay and presses Escape
- **THEN** the modal closes and focus returns to the triggering control

#### Scenario: Missing original shows a placeholder

- **WHEN** a document has no original available
- **THEN** the row shows a neutral placeholder instead of a broken thumbnail

## ADDED Requirements

### Requirement: Numeric veracity is visible in list and detail

The document list and review detail SHALL display the certificate's veracity
score as a numeric value with a high, medium, or low quality label. The list
row color SHALL derive from the veracity band, not from format alone, while the
format score remains separately visible. A missing score SHALL be shown as
"not available", not as zero.

#### Scenario: List shows the veracity value

- **WHEN** a certificate has a veracity score
- **THEN** its row shows the numeric value and quality label
- **AND** the row color matches the veracity band

#### Scenario: Detail shows the veracity value

- **WHEN** a reviewer opens a certificate
- **THEN** the detail shows the numeric veracity score and its quality label
- **AND** the format score remains visible as a separate indicator

#### Scenario: Missing score is explicit

- **WHEN** a certificate has no veracity score
- **THEN** the UI shows "not available"
- **AND** it does not show `0` as if it were measured

### Requirement: Veracity breakdown uses human labels

The review detail SHALL show the veracity score's components — source
verification, format/profile match, label-value consistency, and extraction
evidence — with human labels and short explanations. The raw component codes
SHALL NOT be the primary visible text.

#### Scenario: Reviewer inspects the breakdown

- **WHEN** a reviewer opens the veracity breakdown
- **THEN** each component is shown with a readable label and value
- **AND** the weakest component is identifiable

#### Scenario: Unknown component degrades without leaking codes

- **WHEN** a component has no mapping
- **THEN** the screen shows a generic label
- **AND** the raw code is not the primary text

### Requirement: Source document is visible by default in review

The review detail SHALL display the source document alongside the extracted
data on initial load, without requiring an extra click to reveal it. A zoom or
open-original action MAY be offered for enlargement, but it SHALL NOT be the
only way to see the document. When no original is available, the screen SHALL
say so clearly.

#### Scenario: Review opens with the document visible

- **WHEN** a reviewer opens a document that has an original
- **THEN** the source document is rendered with the extracted data
- **AND** no "show image" click is required

#### Scenario: Zoom is optional

- **WHEN** a reviewer wants a larger view
- **THEN** a zoom or open-original action is available
- **AND** the default view already shows the document

#### Scenario: Missing original is explained

- **WHEN** a document has no original available
- **THEN** the review screen shows a clear message instead of an empty frame

### Requirement: Review layout keeps source and data together

On wide screens the review detail SHALL show the source document and the
extracted data side by side. On narrow screens the document MAY stack with the
data, but it SHALL still be rendered on initial load rather than hidden behind
a click.

#### Scenario: Wide screen shows both panels

- **WHEN** the review detail is opened on a wide screen
- **THEN** the source document and extracted data are visible together

#### Scenario: Narrow screen keeps the document rendered

- **WHEN** the review detail is opened on a narrow screen
- **THEN** the source document is rendered in the stacked layout
- **AND** the reviewer does not need a separate click to load it

### Requirement: High veracity never bypasses review

A high veracity score SHALL NOT approve, validate, or deliver a certificate by
itself. Approval SHALL require an explicit reviewer action, and the UI SHALL
keep the normal review reasons visible even when the veracity score is high.

#### Scenario: High score still requires a decision

- **WHEN** a certificate has a high veracity score
- **THEN** it remains in the review flow until a reviewer acts
- **AND** the review reasons are still shown

#### Scenario: High score does not hide warnings

- **WHEN** a certificate has a high veracity score but a missing or unverified
  critical field
- **THEN** the warning remains visible
- **AND** the certificate is not auto-approved
