# Spec Delta

## ADDED Requirements

### Requirement: Low format confidence is visually flagged in the table

The documents table SHALL visually distinguish rows whose certificate
format confidence is low (format score below threshold), using color or
an equivalent non-color cue, so reviewers can prioritize them without
opening each document.

#### Scenario: Warning row stands out

- **WHEN** scanning the document list
- **THEN** rows with low format confidence are immediately distinguishable
  from high-confidence rows

#### Scenario: Meaning is accessible

- **WHEN** a row is flagged for low format confidence
- **THEN** a tooltip, label, or badge explains that the document's layout
  does not match the expected issuer format
