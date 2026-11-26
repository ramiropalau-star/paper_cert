# reporting-integrity Specification

## Purpose
Defines how certificate reports represent processing dates, counts, filters, timezones, and generated artifacts so a report can be trusted as a record of the selected data.

## Requirements

### Requirement: The processing date is stable across later edits

The system SHALL record a processing timestamp when a document reaches a terminal processing outcome and SHALL use that timestamp for the report's processing-date column. Later edits to the certificate or document metadata SHALL NOT change the reported processing date.

#### Scenario: Editing a certificate does not change its processing date
- **WHEN** a certificate is processed on one date and edited later
- **THEN** the report still shows the original processing date

#### Scenario: Reprocessing updates the processing date
- **WHEN** a document is reprocessed successfully
- **THEN** the processing date reflects the successful reprocessing
- **AND** the previous value is replaced, not shown twice

#### Scenario: Existing documents are backfilled
- **WHEN** the migration runs for documents without a processing timestamp
- **THEN** each receives the best available historical timestamp
- **AND** the report does not show an empty processing date for them

### Requirement: Report counts match the generated rows

The system SHALL persist the approved, pending, rejected, and total row counts on the report job and SHALL display them with the report. The stored counts SHALL equal the number of data rows in the corresponding sheets of the generated workbook.

#### Scenario: Counts match the workbook
- **WHEN** a report contains three approved, two pending, and one rejected certificate
- **THEN** the job stores those counts and the total
- **AND** the workbook sheets contain exactly those numbers of data rows
- **AND** the report detail shows the same counts

#### Scenario: Pending includes validated certificates
- **WHEN** a certificate is in the validated state and pending rows are requested
- **THEN** it is counted in the pending count and appears on the pending sheet
- **AND** it is not counted twice

### Requirement: Invalid filters are rejected

The system SHALL validate report filters before generating a report. An invalid or ambiguous date SHALL produce a clear error and SHALL NOT be silently ignored or converted into an unfiltered report.

#### Scenario: Invalid date is rejected
- **WHEN** a report is requested with an unparseable issue date
- **THEN** no report is generated
- **AND** the user receives an error identifying the invalid filter

#### Scenario: Valid range remains inclusive
- **WHEN** a report is requested with a from-date and a to-date
- **THEN** certificates on both boundary dates are included
- **AND** certificates outside the range are excluded

### Requirement: Report dates use the configured local timezone

The system SHALL convert report timestamps to the application's configured timezone before extracting a calendar date. Date filters SHALL use the same timezone convention.

#### Scenario: Timestamp near midnight uses local date
- **WHEN** a processing timestamp falls near midnight UTC but on the previous or next local date
- **THEN** the report uses the local calendar date
- **AND** it does not use the UTC date by accident

### Requirement: A ready report is an immutable snapshot

The system SHALL compute rows and counts from the same per-status query results and SHALL NOT rewrite an existing ready artifact. Regenerating a ready job SHALL return the existing artifact; a new report SHALL create a new job and artifact.

#### Scenario: Ready artifact is not rewritten
- **WHEN** a ready report job is run again after source data changes
- **THEN** the existing artifact is returned unchanged

#### Scenario: New report reflects new data
- **WHEN** a new report job is created after source data changes
- **THEN** its rows and counts reflect the new data
- **AND** the previous artifact remains unchanged
