# Spec Delta

## Purpose

Defines how persistent application data is backed up, retained, and restored so a deployment can recover documents, extracted data, reports, and service state after data loss.

## ADDED Requirements

### Requirement: Automated backup command covers all persistent data

The project SHALL provide a single backup entry point that captures the PostgreSQL database and every Docker volume that holds user or service state (application media, reports, Paperless data and media, n8n data). The backup SHALL be consistent enough to restore into a running stack and SHALL be invocable manually and from a scheduler.

#### Scenario: Manual backup produces a complete set
- **WHEN** an operator runs the backup command
- **THEN** a timestamped backup directory or archive is created containing the database dump and the persistent volumes
- **AND** the command reports what was captured

#### Scenario: Backup is safe to run while the stack is live
- **WHEN** the backup runs while services are up
- **THEN** it does not stop or corrupt running services
- **AND** the resulting backup passes the documented restore procedure

### Requirement: Backup retention is bounded

The backup mechanism SHALL delete backups older than a configurable retention period (default: 14 days) so backup storage does not grow without limit.

#### Scenario: Old backups are pruned
- **WHEN** a backup completes and older backups exceed the retention period
- **THEN** backups older than the retention period are removed
- **AND** backups inside the retention period are kept

#### Scenario: Retention is configurable
- **WHEN** an operator sets a different retention value
- **THEN** pruning uses that value instead of the default

### Requirement: Restore procedure is documented and verified

The project SHALL document the exact steps to restore a backup into the stack, including database restore order and volume restoration, and the procedure SHALL be verified against a real backup.

#### Scenario: Operator follows the restore doc
- **WHEN** an operator restores the most recent backup following the documentation
- **THEN** the application, documents, and reports are available again without manual data fixes
