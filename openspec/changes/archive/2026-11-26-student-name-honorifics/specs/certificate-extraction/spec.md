# Spec Delta

## ADDED Requirements

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
