# Spec Delta

## Purpose

Defines internal code-quality requirements that keep shared pipeline logic in one place, remove dead code, and bound the size of view modules so fixes cannot diverge across copies.

## ADDED Requirements

### Requirement: Shared merge and sniffing helpers have a single implementation

Reason-list merging and file-type sniffing/renaming logic SHALL live in shared service modules used by every pipeline stage, rather than being re-implemented per stage. Each caller SHALL retain control over which reason codes it owns and which MIME types it accepts.

#### Scenario: Reason merge preserves stage ownership
- **WHEN** the text, extraction, and classification stages each merge review reasons
- **THEN** they use the same merge implementation
- **AND** each stage still replaces only its own reason codes

#### Scenario: Sniffing helpers are shared
- **WHEN** text acquisition and Paperless ingestion detect a payload type and derive a filename
- **THEN** they use the same sniffing and naming implementation
- **AND** each caller's MIME allowlist behavior is preserved

### Requirement: No unused service helpers remain

Service modules SHALL NOT contain functions with no callers.

#### Scenario: Dead helper removed
- **WHEN** a service function has no references in the codebase or tests
- **THEN** it is removed or justified before merge

### Requirement: View modules stay focused

View modules SHALL keep HTTP handling concerns together and delegate filtering/query construction to dedicated helpers or modules, keeping individual view files within a maintainable size.

#### Scenario: Document list filtering is extracted
- **WHEN** the document list view applies its filters
- **THEN** the filter logic lives outside the main view module or in a clearly separated helper
- **AND** view behavior is unchanged for valid parameters
