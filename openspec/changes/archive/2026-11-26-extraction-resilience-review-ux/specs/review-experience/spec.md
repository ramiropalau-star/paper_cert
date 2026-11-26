# Spec Delta

## ADDED Requirements

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
