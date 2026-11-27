# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
