# review-experience Specification

## Purpose
Defines how the document review screen communicates reasons, confidence, warnings, status, and actions so a reviewer can decide without translating internal codes.

## Requirements

### Requirement: Review reasons use human labels and explanations

The review screen SHALL present each known review reason with a human label and a short explanation of what the reviewer should check. The raw reason code SHALL NOT be the primary visible text.

#### Scenario: Known reason is explained
- **WHEN** a certificate has the `low_confidence` reason
- **THEN** the screen shows a readable label and an explanation
- **AND** it does not show the raw code as the main text

#### Scenario: Multiple reasons are readable
- **WHEN** a certificate has several review reasons
- **THEN** each reason is shown once with its label and explanation
- **AND** duplicate codes are not repeated

### Requirement: Unknown reasons degrade without leaking codes

The review screen SHALL show a generic review message for a reason code it does not recognize. It MAY expose the raw code in a secondary detail for diagnostics, but the primary text SHALL remain understandable.

#### Scenario: Unknown reason is generic
- **WHEN** a review reason has no mapping
- **THEN** the screen shows a generic "requires manual review" message
- **AND** the raw code is not the primary text

### Requirement: Confidence is shown as a percentage with a quality label

The review screen SHALL display extraction confidence as a percentage and a high, medium, or low label. The raw decimal MAY remain available in a secondary detail, but it SHALL NOT be the only representation.

#### Scenario: Confidence is readable
- **WHEN** a certificate has confidence `0.87`
- **THEN** the screen shows `87%` and a quality label
- **AND** the raw decimal is not the primary value

#### Scenario: Missing confidence is explicit
- **WHEN** a certificate has no confidence value
- **THEN** the screen shows a clear "not available" state
- **AND** it does not show `0%` as if it were measured

### Requirement: Warnings point to the field they affect

The review screen SHALL associate each mapped warning with the field it concerns and SHALL provide an explicit "no observations" state when there are no review reasons.

#### Scenario: Warning points to its field
- **WHEN** the `unknown_language` reason is present
- **THEN** the warning is shown next to the language field or links to it
- **AND** the reviewer can find the affected field without guessing

#### Scenario: No observations are explicit
- **WHEN** a certificate has no review reasons
- **THEN** the screen shows a clear no-observations message
- **AND** it does not render an empty list

### Requirement: Destructive review actions require explicit confirmation

The review screen SHALL require an explicit confirmation before reprocessing a document. It SHALL keep the rejection reason required. A request without the confirmation SHALL NOT reprocess the document and SHALL show a clear message.

#### Scenario: Reprocess requires confirmation
- **WHEN** a reviewer submits the reprocess action without confirming
- **THEN** the document is not reprocessed
- **AND** the screen explains that confirmation is required

#### Scenario: Confirmed reprocess proceeds
- **WHEN** a reviewer confirms the reprocess action
- **THEN** the document is reprocessed through the existing pipeline

### Requirement: Status and actions are accessible and unambiguous

Every review status badge SHALL include text, not color alone. Every review action SHALL have an accessible name that states its effect, and the review screen SHALL remain operable by keyboard.

#### Scenario: Status is not color-only
- **WHEN** a document is shown as approved, rejected, pending, or in error
- **THEN** the status text is present in the badge
- **AND** the meaning does not depend on color alone

#### Scenario: Actions are keyboard operable
- **WHEN** a reviewer navigates the review actions with the keyboard
- **THEN** each action is reachable and has a visible focus state
- **AND** each action's accessible name states what it does

### Requirement: Catalog-pending badge on unresolved literals

The document list, gallery, and review detail SHALL mark records whose
`entity`, `exam`, or `language` literal failed catalog resolution with a
visible "catálogo pendiente" indicator, distinct from generic review
warnings. Resolved records SHALL NOT show the badge.

#### Scenario: Unresolved entity shows badge
- **WHEN** a certificate has `entity = NULL` and an `entity_literal`
- **THEN** the list row, gallery card, and detail page show the
  catalog-pending indicator

#### Scenario: Resolved entity hides badge
- **WHEN** the certificate's entity literal resolved to a catalog `Entity`
- **THEN** no catalog-pending indicator is shown for that field

### Requirement: Unresolved-catalog filter

The document queue SHALL offer a filter that lists only documents with at
least one unresolved catalog reference (`entity`, `exam`, or `language`
literal without a matching foreign key), combinable with existing filters.

#### Scenario: Filter pending catalog work
- **WHEN** a reviewer applies the unresolved-catalog filter
- **THEN** only documents with at least one unresolved catalog literal are
  listed
- **AND** the filter combines with state/search/other filters using AND
  semantics

### Requirement: Documents table offers quick document preview

The documents list SHALL provide a per-row quick preview action that opens the
certificate document in a modal overlay without navigating away, using the same
rendered document source as the gallery enlarge view. The preview SHALL be
dismissible via close control, backdrop click, and keyboard, and SHALL NOT
interfere with row navigation or existing filters.

#### Scenario: Preview opens from the list

- **WHEN** a reviewer activates the preview action on a document row
- **THEN** a modal shows the document render at a readable size
- **AND** closing it returns to the unchanged list with filters preserved

#### Scenario: Preview is keyboard accessible

- **WHEN** a reviewer opens the preview and presses Escape
- **THEN** the modal closes and focus returns to the triggering control

### Requirement: Documents table columns are filterable and sortable

The documents table SHALL allow reviewers to filter rows by typing into per-column
text filters and to sort rows ascending or descending by activating a column
header. Filtering and sorting SHALL operate client-side over the rendered rows,
compose with each other and with the existing server-side GET filters, and SHALL
preserve the current page state.

#### Scenario: Column filter narrows rows

- **WHEN** a reviewer types text into a column filter
- **THEN** only rows whose cell in that column contains the text remain visible
- **AND** the row count reflects the visible subset

#### Scenario: Header click togggles sort direction

- **WHEN** a reviewer activates a sortable column header
- **THEN** rows reorder ascending by that column's value
- **AND** activating it again reverses to descending, with a visible indicator

#### Scenario: Client filters compose with server filters

- **WHEN** server-side filters are active and a reviewer applies a column filter
- **THEN** the visible rows are the intersection of both filter sets

### Requirement: Documents table paginates client-side

The documents table SHALL paginate the rendered rows client-side, showing 10
rows per page by default. A page-size control SHALL let the reviewer choose a
different number of rows per page or view all rows at once. Pagination SHALL
compose with column filters and sorting — filters and sort apply to the full
result set before paging — and SHALL reset to the first page when the result
set changes.

#### Scenario: Default page size is ten rows

- **WHEN** the documents list renders more than ten rows
- **THEN** only the first ten are visible with pagination controls
- **AND** the controls indicate the current page and total pages

#### Scenario: Reviewer changes page size or views all

- **WHEN** the reviewer selects a different page size or "view all"
- **THEN** the table renders that many rows per page, or every filtered row
- **AND** the choice persists for the session

#### Scenario: Filtering resets pagination

- **WHEN** a column filter or server-side filter changes the result set
- **THEN** the table returns to the first page of the new result set
