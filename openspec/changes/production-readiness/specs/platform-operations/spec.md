# Spec Delta

## ADDED Requirements

### Requirement: Container logs are bounded

Every Compose service SHALL configure a logging driver with a maximum size and file count so container logs cannot exhaust host disk space.

#### Scenario: Logs rotate at the configured limit
- **WHEN** a service produces more log output than the configured limit
- **THEN** older log files are rotated or discarded per the driver configuration
- **AND** the service keeps running

### Requirement: Service health is visible to operators

The project SHALL provide a way for an operator to see the health status of every service in one place, either via a script that aggregates `docker compose ps` health or documented equivalent commands.

#### Scenario: Operator checks overall health
- **WHEN** an operator runs the health check
- **THEN** they see each service marked healthy, unhealthy, or starting
- **AND** unhealthy services are clearly identified

### Requirement: Production deployment guide covers TLS and exposure

The operational documentation SHALL include a production checklist covering HTTPS termination (reverse proxy example), bind addresses, credential rotation, and the backup schedule.

#### Scenario: Operator prepares a production deploy
- **WHEN** an operator follows the production section of the docs
- **THEN** they can put the app, n8n, and Paperless UI behind HTTPS with correct host and cookie settings
- **AND** the documented settings match what the application actually reads
