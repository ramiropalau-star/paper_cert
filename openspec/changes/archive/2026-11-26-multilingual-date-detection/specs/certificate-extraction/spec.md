# Spec Delta

## ADDED Requirements

### Requirement: Dates with month names parse in supported languages

The system SHALL parse dates whose month is written as a name or
abbreviation in Catalan, Spanish, English, French, German, Portuguese, or
Italian (e.g. "18 Setembre 2026", "18 Septiembre 2026", "5 décembre 2020",
"3 März 2021"). Candidates containing such dates SHALL NOT be silently
dropped: when the full value cannot be normalized they SHALL surface as
ambiguous date evidence for review.

#### Scenario: Catalan month name parses

- **WHEN** a candidate text contains "18 Setembre 2026"
- **THEN** the system parses it as 2026-09-18 (or the entity-ordered
  equivalent) instead of discarding it

#### Scenario: Trilingual repeated date collapses to one candidate

- **WHEN** the document prints "18 Setembre 2026 · 18 Septiembre 2026 ·
  18 September 2026" for the same date
- **THEN** harvesting produces a single date candidate, not three

#### Scenario: Unparseable date-like text stays visible

- **WHEN** a candidate mentions a month name but no parseable day/year
  (e.g. "SEPTIEMBRE 2020")
- **THEN** it is retained as ambiguous date evidence and triggers the
  ambiguous-date review reason

### Requirement: Deterministic date harvesting covers label-less dates

When model extraction returns few or no date candidates, the system SHALL
scan the stored page texts for date-like patterns regardless of nearby
labels and add missing candidates with role `unknown`, so dates printed
beside signatures or in unlabeled blocks are not lost. Harvested candidates
SHALL be deduplicated against model-returned candidates by parsed value.

#### Scenario: Label-less issue block is harvested

- **WHEN** the model returns no dates but page text contains "18 Setembre
  2026 · 18 Septiembre 2026 · 18 September 2026" near the signature block
- **THEN** a date candidate is added with role `unknown` and the document
  routes to review with the ambiguous-date reason rather than losing the
  date entirely

#### Scenario: Harvest respects birth-date exclusions

- **WHEN** a date-like pattern appears on a line containing birth/nacimiento/
  naixement/Geburtsdatum markers
- **THEN** the harvester does not add it as a certificate date candidate

#### Scenario: Implausible years are rejected

- **WHEN** a harvested pattern yields a year outside a sane certificate
  range (e.g. "0399")
- **THEN** it is not added as a date candidate
