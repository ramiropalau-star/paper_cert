# platform-operations Specification

## Purpose
Run the whole system as a reproducible, self-hosted Docker environment that protects internal services and secrets, keeps data across restarts, and documents the operational lifecycle.

## Requirements

### Requirement: Reproducible Docker Compose stack
The project SHALL provide a Dockerfile and a Docker Compose file that bring up the web application, n8n, Paperless-ngx, Ollama, PostgreSQL, and the OCR capability, with optional auxiliary services only when required.

#### Scenario: Stack starts from documented instructions
- **WHEN** an operator follows the documented initialization steps on a machine with Docker
- **THEN** the stack starts and the web application is reachable
- **AND** the application can process documents through the configured services

#### Scenario: Services share an internal network
- **WHEN** the stack is running
- **THEN** the application, n8n, Paperless-ngx, Ollama, PostgreSQL, and OCR communicate over a Docker network
- **AND** internal service names resolve within that network

### Requirement: Internal services are not publicly exposed by default
The default Compose configuration SHALL publish only the ports required for users to reach the application.

#### Scenario: Administrative interfaces remain internal
- **WHEN** the stack is started with the default configuration
- **THEN** administrative interfaces, databases, Ollama, and internal services are not reachable from outside the Docker network
- **AND** only the application entry point is published

#### Scenario: Exposure requires explicit configuration
- **WHEN** an operator publishes an additional service port
- **THEN** that change is explicit in configuration and documented as a security-relevant decision

### Requirement: Environment-based configuration and secrets
The project SHALL configure ports, users, passwords, keys, document-store settings, OCR languages, and model selection through environment variables, and SHALL provide a .env.example without real secrets.

#### Scenario: Example environment provided
- **WHEN** an operator inspects the repository
- **THEN** a .env.example lists the required variables with safe placeholder values
- **AND** no real password, key, or secret is committed

#### Scenario: Model selected by configuration
- **WHEN** an operator sets the Ollama model name in the environment
- **THEN** the extraction stage uses that model without code changes

### Requirement: Persistent data volumes
The system SHALL store documents, database data, service configuration, and downloaded Ollama models in Docker volumes so they survive container recreation.

#### Scenario: Data survives container recreation
- **WHEN** the stack is stopped and containers are recreated without deleting volumes
- **THEN** documents, structured data, configuration, and downloaded models remain available

#### Scenario: Volume layout documented
- **WHEN** an operator reads the deployment documentation
- **THEN** the persistent volumes and their contents are identified

### Requirement: Authenticated and authorized access
The system SHALL require authentication to access documents, extracted data, review actions, and reports, and SHALL enforce permissions for administrative and destructive actions.

#### Scenario: Unauthenticated access denied
- **WHEN** an unauthenticated request attempts to view documents or download a report
- **THEN** the system denies access

#### Scenario: Permissions enforced
- **WHEN** a user without the required permission attempts an administrative or destructive action
- **THEN** the system refuses the action
- **AND** the attempt does not modify documents or data

### Requirement: Bounded retries and safe error logging
The system SHALL apply bounded retries to transient failures and SHALL log errors without unnecessarily recording the full certificate content.

#### Scenario: Transient failure retried
- **WHEN** a transient downstream failure occurs during processing
- **THEN** the system retries a configured, bounded number of times

#### Scenario: Failure becomes visible
- **WHEN** retries are exhausted
- **THEN** the document is placed in an error state visible to an operator
- **AND** the failure is recorded without dumping the full certificate text into logs

### Requirement: Idempotent pipeline processing
The system SHALL ensure that retries or reprocessing of the same document do not create duplicate certificates, report rows, or storage entries.

#### Scenario: Pipeline retry does not duplicate
- **WHEN** a processing step is retried for the same document
- **THEN** the system updates the existing record and its associations
- **AND** the report still contains a single row for that certificate

### Requirement: n8n orchestrates the processing workflow
The project SHALL deliver n8n flows or documented creation instructions that coordinate intake, OCR, AI extraction, validation, persistence, and report generation.

#### Scenario: Exported flows or instructions available
- **WHEN** an operator initializes n8n
- **THEN** the repository provides importable flow definitions or step-by-step instructions to create them

#### Scenario: Workflow covers the pipeline stages
- **WHEN** a document is processed through the orchestrated workflow
- **THEN** the workflow covers ingestion, OCR decision, extraction, validation, persistence, and report generation

### Requirement: Operational documentation
The project SHALL document installation, environment configuration, Ollama model setup, backups, updates, report generation, and error review.

#### Scenario: Operator can install and initialize
- **WHEN** an operator follows the installation documentation from a clean environment
- **THEN** the steps initialize the services and prepare the Ollama model

#### Scenario: Backup and update procedures documented
- **WHEN** an operator reads the operations documentation
- **THEN** backup, restore, and update procedures are described, including which volumes to preserve

### Requirement: Deployment script uses the configured application port

The deployment script SHALL derive the application port from the environment file it manages, using the same default as `.env.example` and `compose.yaml`, and SHALL use that port consistently for the generated CSRF trusted origins, the post-deploy health check, and the operator-facing summary.

#### Scenario: Fresh deploy verifies the real port
- **WHEN** `deploy.sh` runs on a fresh checkout where `.env` sets `APP_PORT` to the documented default
- **THEN** the final health check queries that port
- **AND** the script reports success only if the application answers on it

#### Scenario: Trusted origins match the published port
- **WHEN** the script generates `.env` on first deploy
- **THEN** `DJANGO_CSRF_TRUSTED_ORIGINS` contains the configured application port
- **AND** it does not reference a different hardcoded port

#### Scenario: Custom port is respected
- **WHEN** `.env` sets a non-default `APP_PORT`
- **THEN** the health check and displayed URL use that value
