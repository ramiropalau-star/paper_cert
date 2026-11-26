# platform-security Specification

## Purpose
Defines the deployment and request boundaries that keep orchestration services private, authenticated, and safe to operate outside a developer laptop.

## Requirements

### Requirement: Orchestration webhooks require authentication

The system SHALL require a shared secret header on every n8n processing and report webhook. Requests with a missing or invalid secret SHALL be rejected with HTTP 401 before any workflow stage runs. The secret SHALL come from environment configuration and SHALL NOT be written to logs.

#### Scenario: Missing token is rejected
- **WHEN** a request reaches the processing webhook without `X-Webhook-Token`
- **THEN** n8n returns HTTP 401
- **AND** no pipeline stage runs

#### Scenario: Invalid token is rejected
- **WHEN** a request reaches the report webhook with a token that does not match `APP_N8N_WEBHOOK_TOKEN`
- **THEN** n8n returns HTTP 401
- **AND** no report stage runs

#### Scenario: Valid token is accepted
- **WHEN** a request reaches either webhook with the configured token
- **THEN** the workflow runs normally

#### Scenario: Token is not logged
- **WHEN** a webhook request is accepted or rejected
- **THEN** the token value does not appear in the workflow output or application logs

### Requirement: Administrative services are not published by default

The default Compose configuration SHALL publish only the application entry point and the n8n UI. Paperless-ngx, Ollama, PostgreSQL, and the OCR service SHALL remain reachable only inside the Docker network unless an operator explicitly opts into a documented exposure.

#### Scenario: Default stack keeps Paperless internal
- **WHEN** the stack starts with the default Compose file
- **THEN** Paperless port 9090 is not reachable from the host
- **AND** the application can still reach Paperless over the Docker network

#### Scenario: Extra exposure is explicit and documented
- **WHEN** an operator publishes an additional service port
- **THEN** the change is explicit in configuration
- **AND** the operations documentation records it as a security-relevant decision

### Requirement: Insecure startup secrets fail fast

When `DEBUG` is false, the application SHALL refuse to start if `DJANGO_SECRET_KEY` is missing, empty, the development default, or shorter than 32 characters. The error SHALL name the variable without printing its value. Development mode MAY use the default.

#### Scenario: Default secret blocks startup
- **WHEN** the application starts with `DEBUG=false` and the development default key
- **THEN** startup fails with an error that names `DJANGO_SECRET_KEY`
- **AND** the error does not include the key value

#### Scenario: Strong secret starts normally
- **WHEN** the application starts with a non-default key of at least 32 characters
- **THEN** startup proceeds

#### Scenario: Development default is allowed in debug mode
- **WHEN** the application starts with `DEBUG=true` and the development default key
- **THEN** startup proceeds

### Requirement: n8n cookie security matches the access scheme

The n8n configuration SHALL set `N8N_SECURE_COOKIE` according to the public scheme. An HTTPS deployment SHALL use secure cookies. An HTTP LAN deployment SHALL either use HTTPS or explicitly disable secure cookies and document the risk.

#### Scenario: HTTPS deployment uses secure cookies
- **WHEN** n8n is published over HTTPS
- **THEN** `N8N_SECURE_COOKIE` is `true`

#### Scenario: HTTP LAN deployment is explicit
- **WHEN** n8n is published over plain HTTP on the LAN
- **THEN** the deployment explicitly sets `N8N_SECURE_COOKIE=false`
- **AND** the documentation states the risk and the HTTPS migration path

#### Scenario: Login is not silently broken
- **WHEN** an operator follows the documented setup for the chosen scheme
- **THEN** the n8n login cookie is accepted by the browser

### Requirement: Bulk document deletion is scoped

The system SHALL restrict bulk deletion to documents tracked by the application by default. Deleting untracked Paperless documents SHALL require an explicit, separately confirmed scope and SHALL be recorded in the audit log.

#### Scenario: Default deletion removes tracked documents only
- **WHEN** an operator confirms bulk deletion without selecting the untracked scope
- **THEN** only documents tracked by the application are deleted
- **AND** unrelated Paperless documents remain

#### Scenario: Untracked deletion requires explicit confirmation
- **WHEN** an operator selects the untracked scope
- **THEN** a second, explicit confirmation is required
- **AND** the deletion is recorded in the audit log

### Requirement: Total request size and per-file size are enforced separately

The system SHALL enforce a per-file upload limit and a separate total request limit. A multi-file upload whose individual files and total size are within their respective limits SHALL be accepted.

#### Scenario: Valid multi-file upload is accepted
- **WHEN** two files of 20 MB each are uploaded with a 25 MB per-file limit and a 100 MB total limit
- **THEN** the request is accepted

#### Scenario: Oversized single file is rejected
- **WHEN** one file exceeds the per-file limit
- **THEN** the request is rejected with a per-file error

#### Scenario: Oversized total request is rejected
- **WHEN** the combined upload exceeds the total request limit
- **THEN** the request is rejected with a total-size error

### Requirement: Deployed credentials are strong by default

The deployment script SHALL generate a cryptographically random administrator password when `DEPLOY_ADMIN_PASSWORD` is not provided, and SHALL NOT fall back to a well-known password. The generated value SHALL be written only to `.env`, never printed to logs or the console banner.

#### Scenario: Fresh deploy generates a strong password
- **WHEN** `deploy.sh` runs without `DEPLOY_ADMIN_PASSWORD`
- **THEN** `.env` receives a randomly generated password of at least 20 characters
- **AND** the console output does not reveal the password

#### Scenario: Explicit override is honored
- **WHEN** `DEPLOY_ADMIN_PASSWORD` is set
- **THEN** that value is used for the Django and Paperless admin accounts

### Requirement: Bootstrap rejects weak admin passwords

The bootstrap command SHALL validate the configured superuser password with the project's password validators and SHALL refuse to create the account when the password is invalid, unless an explicit development override is set.

#### Scenario: Weak password is rejected
- **WHEN** bootstrap runs with a superuser password that fails validation (e.g. `admin`)
- **THEN** the command fails with a clear error naming the problem
- **AND** no superuser is created

#### Scenario: Valid password creates the superuser
- **WHEN** bootstrap runs with a password that passes validation
- **THEN** the superuser is created normally

#### Scenario: Development override bypasses validation
- **WHEN** the explicit development override is set
- **THEN** bootstrap creates the superuser without validation, for local testing only

### Requirement: Administrative UIs default to loopback binding

Published ports that expose administrative interfaces (n8n UI) SHALL bind to loopback by default. Operators MAY override the bind address explicitly for LAN or reverse-proxy deployments.

#### Scenario: Default n8n binding is loopback
- **WHEN** the stack starts with the default Compose configuration
- **THEN** the n8n UI is reachable on `127.0.0.1:5678` on the host
- **AND** it is not reachable from other machines on the network

#### Scenario: Explicit bind address is honored
- **WHEN** an operator configures a different bind address for the n8n UI
- **THEN** the port is published on that address
