# code-health Specification

## Purpose
Defines internal code-quality requirements that keep shared pipeline logic in one place, remove dead code, and bound the size of view modules so fixes cannot diverge across copies.

## Requirements

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

View modules SHALL keep HTTP handling concerns together and delegate filtering/query construction to dedicated helpers or modules, keeping individual view files within a maintainable size. Large view modules SHALL be split into focused packages or modules by concern.

#### Scenario: Document list filtering is extracted
- **WHEN** the document list view applies its filters
- **THEN** the filter logic lives outside the main view module or in a clearly separated helper
- **AND** view behavior is unchanged for valid parameters

#### Scenario: Oversized view module is split
- **WHEN** a view module grows beyond a maintainable size
- **THEN** it is split into a package or focused modules by concern
- **AND** URL routes and view behavior are unchanged

### Requirement: Continuous integration enforces quality gates

The repository SHALL define a CI workflow that runs the linter, the formatter check, and the test suite on every push and pull request, and SHALL fail when any of them fails.

#### Scenario: CI runs on push and pull request
- **WHEN** a commit is pushed or a pull request is opened
- **THEN** the CI workflow runs `ruff check`, `ruff format --check`, and `pytest`
- **AND** the check fails if any step fails

### Requirement: Lint and format debt is zero

The codebase SHALL pass `ruff check` and `ruff format --check` with no violations, excluding generated or vendored paths such as `openspec/`.

#### Scenario: Clean lint and format state
- **WHEN** a developer runs `ruff check` and `ruff format --check` on a clean checkout
- **THEN** both commands exit successfully

### Requirement: Test tooling supports coverage and parallel execution

The development dependencies SHALL include coverage and parallel test execution plugins so the suite can report coverage and run faster on multi-core machines.

#### Scenario: Coverage report is available
- **WHEN** a developer runs the test suite with the coverage plugin enabled
- **THEN** a coverage report is produced

#### Scenario: Tests can run in parallel
- **WHEN** a developer runs the test suite with the parallel plugin enabled
- **THEN** tests are distributed across available workers and pass
