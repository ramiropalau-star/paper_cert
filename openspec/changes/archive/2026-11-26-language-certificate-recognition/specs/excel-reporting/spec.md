# Spec Delta

## Purpose

Produce downloadable Excel workbooks that summarize approved certificates with the required columns and keep records still pending review clearly separated and identified.

## ADDED Requirements

### Requirement: Generate and download an Excel report
The system SHALL generate a downloadable .xlsx workbook with one row per certificate.

#### Scenario: User downloads the report
- **WHEN** an authenticated user requests the Excel report
- **THEN** the system generates and offers a downloadable .xlsx file
- **AND** the main sheet contains exactly one row per included certificate

#### Scenario: Corrections reflected in the report
- **WHEN** a record has manually corrected data
- **THEN** the generated report contains the current corrected values

### Requirement: Include the required report columns
The main report SHALL include at minimum student, language, level, certifying entity, and issue date, and SHALL also include exam or certificate name and score when available.

#### Scenario: Required columns present
- **WHEN** the report is generated
- **THEN** the main sheet includes columns for Alumno, Idioma, Nivel, Entidad certificadora, Fecha de expedición, Certificado o examen, and Puntuación

#### Scenario: CEFR stored separately
- **WHEN** a certificate has a normalized CEFR level
- **THEN** the report can present it in a separate column from the literal level

#### Scenario: Supplementary columns available
- **WHEN** the report is generated
- **THEN** it may include review status, processing date, and a reference to the original document

### Requirement: Separate records pending review
The system SHALL NOT present unreviewed records as confirmed data in the main sheet, and SHALL place any included pending records on a separate sheet.

#### Scenario: Pending records on their own sheet
- **WHEN** pending records are included in the workbook
- **THEN** they appear on a second sheet named "Pendientes de revisión"

#### Scenario: Main sheet holds approved records
- **WHEN** the main sheet is generated
- **THEN** it contains approved records and does not present pending records as confirmed certificates

### Requirement: Filter the report
The system SHALL allow the report to be filtered by language, entity, issue date, review status, and student.

#### Scenario: Filtered report generation
- **WHEN** a user selects one or more report filters
- **THEN** the generated workbook contains only records matching those filters

#### Scenario: No matches handled
- **WHEN** the selected filters match no records
- **THEN** the system informs the user that no records match
- **AND** does not produce a misleading report of unrelated data

### Requirement: Format the workbook for review
The report SHALL include column headers, usable filters, and appropriate date formatting.

#### Scenario: Headers and filters present
- **WHEN** the workbook is opened
- **THEN** the main sheet has a header row and filter controls enabled

#### Scenario: Dates formatted as dates
- **WHEN** an issue date is present
- **THEN** the cell uses a date format suitable for sorting and filtering

### Requirement: Report reflects approved and rejected states
The system SHALL include only records whose review state permits it and SHALL identify any included unreviewed records clearly.

#### Scenario: Rejected excluded
- **WHEN** a record is rejected
- **THEN** it is excluded from the main report

#### Scenario: Unreviewed identified
- **WHEN** an unreviewed record is included in a secondary sheet
- **THEN** its review status is clearly identified in that sheet
