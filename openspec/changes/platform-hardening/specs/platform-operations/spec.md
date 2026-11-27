# Spec Delta

## ADDED Requirements

### Requirement: Readiness probe reflects dependency health

The application SHALL expose a readiness endpoint that verifies critical dependencies (at minimum the database) and returns HTTP 503 when any required dependency is unavailable. The container healthcheck SHALL use the readiness endpoint so an unhealthy dependency marks the service unhealthy. The existing liveness endpoint SHALL remain a shallow probe that does not touch dependencies.

#### Scenario: Readiness fails when the database is down

- **WHEN** the database is unavailable and a request hits the readiness endpoint
- **THEN** the endpoint returns HTTP 503
- **AND** the Compose healthcheck reports the app service as unhealthy

#### Scenario: Readiness passes when dependencies are up

- **WHEN** the database is reachable and a request hits the readiness endpoint
- **THEN** the endpoint returns HTTP 200

#### Scenario: Liveness stays shallow

- **WHEN** the database is unavailable and a request hits the liveness endpoint
- **THEN** the endpoint still returns HTTP 200 as long as the process is alive

### Requirement: Backup procedure is automated by a script

The project SHALL provide an executable backup script that creates a timestamped backup set (database dump plus persistent volume data) under a configurable backup directory, prunes backups older than a configurable retention period, and is referenced by the operations documentation together with a scheduling example.

#### Scenario: Operator runs the backup script

- **WHEN** an operator executes the backup script
- **THEN** a timestamped backup directory is created containing the database dump and volume archives
- **AND** backups older than the retention period are removed

#### Scenario: Backup schedule is documented

- **WHEN** an operator reads the operations documentation
- **THEN** a scheduling example (cron or systemd timer) for the backup script is provided
