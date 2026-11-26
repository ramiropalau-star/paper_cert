# Spec Delta

## ADDED Requirements

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
