# extraction-evaluation Specification

## Purpose

Provide a repeatable, offline way to measure extraction quality before changing models, prompts, or issuer profiles, so improvements are evidence-based and regressions are caught.

## Requirements

### Requirement: Versioned golden set from human-confirmed certificates

The system SHALL maintain a versioned golden set of extraction cases built from approved or validated certificates whose fields a human confirmed. Each case SHALL record the source text, expected fields and evidence, issuer/profile, and the prompt/model context used, and rejected or unapproved documents SHALL NOT be included.

#### Scenario: Approved certificate becomes an evaluation case

- **WHEN** a certificate is approved and its fields are human-confirmed
- **THEN** it is eligible for the golden set with its expected fields and evidence
- **AND** later edits create a new golden-set version instead of mutating history

#### Scenario: Rejected document is excluded

- **WHEN** a document is rejected or never approved
- **THEN** it is not added to any golden set

### Requirement: Offline dry-run evaluation

The system SHALL run extraction against a golden-set version without persisting extracted fields to live certificates, creating review reasons, or changing document state. A run SHALL record the model, prompt version, profile version, pre-detection version, code revision, and start/end time.

#### Scenario: Dry run leaves live data unchanged

- **WHEN** an evaluation run executes
- **THEN** no certificate fields, review reasons, or processing states change
- **AND** the run record stores its model, prompt, profile, and code versions

#### Scenario: Run can target one issuer

- **WHEN** an operator evaluates only certificates from one issuer
- **THEN** the run uses only that issuer's cases and reports its metrics separately

### Requirement: Per-field, evidence, and latency metrics

An evaluation run SHALL report schema validity, exact and normalized accuracy per field, missing-field rate, fabricated-value rate, evidence-quote validity, and latency, both overall and grouped by issuer and certificate type.

#### Scenario: Field accuracy is reported

- **WHEN** a run completes
- **THEN** each extracted field has exact and normalized accuracy against the golden set
- **AND** missing and fabricated values are counted separately

#### Scenario: Evidence validity is reported

- **WHEN** a run completes
- **THEN** the report shows how many evidence quotes matched the source text and how many did not

#### Scenario: Latency is reported

- **WHEN** a run completes
- **THEN** the report shows total and per-document latency for the evaluated configuration

### Requirement: Baseline comparison and regression reporting

The system SHALL compare a run with a selected baseline and report per-field regressions and improvements. A regression report SHALL NOT deploy, approve, or activate any model, prompt, or profile by itself.

#### Scenario: Regression is visible

- **WHEN** a run's field accuracy is lower than the baseline beyond the configured tolerance
- **THEN** the report marks that field as a regression with both values
- **AND** no live configuration changes automatically

#### Scenario: Improvement is visible

- **WHEN** a run improves a field's accuracy over the baseline
- **THEN** the report marks the improvement with both values

### Requirement: Evaluation history is auditable

The system SHALL retain evaluation runs and their results with actor, timestamp, configuration versions, and golden-set version, and SHALL let authorized reviewers list and compare runs. Viewers SHALL NOT create or delete runs.

#### Scenario: Reviewer compares two runs

- **WHEN** an authorized reviewer selects two runs
- **THEN** the system shows their metrics side by side and the configuration differences

#### Scenario: Viewer cannot start a run

- **WHEN** a viewer attempts to start an evaluation run
- **THEN** the request is rejected and no run is created
