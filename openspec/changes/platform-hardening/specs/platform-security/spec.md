# Spec Delta

## MODIFIED Requirements

### Requirement: Deployed credentials are strong by default

The deployment script SHALL generate a cryptographically random administrator password when `DEPLOY_ADMIN_PASSWORD` is not provided, and SHALL NOT fall back to a well-known password. The generated value SHALL be written to `.env` and MAY be shown once in the final operator summary so it can be recorded; it SHALL NOT appear in logs during the run. A weak password such as `admin` SHALL only be usable through an explicit, documented test override.

#### Scenario: Fresh deploy generates a strong password

- **WHEN** `deploy.sh` runs without `DEPLOY_ADMIN_PASSWORD`
- **THEN** `.env` receives a randomly generated password of at least 20 characters
- **AND** the password is shown at most once in the final summary, never in logs

#### Scenario: Explicit override is honored

- **WHEN** `DEPLOY_ADMIN_PASSWORD` is set to a strong value
- **THEN** that value is used for the Django and Paperless admin accounts

#### Scenario: Weak password requires explicit test opt-in

- **WHEN** an operator wants a weak password such as `admin` for a test deployment
- **THEN** both the password override and the bootstrap weak-password override are set explicitly
- **AND** the deployment documents that this is for testing only

## ADDED Requirements

### Requirement: Environment file permissions are restrictive

The deployment script SHALL create `.env` with owner-only permissions (mode `600`) because it contains secrets, and SHALL tighten permissions on an existing `.env` that is too permissive.

#### Scenario: Fresh deploy creates a private .env

- **WHEN** `deploy.sh` generates `.env` on a fresh checkout
- **THEN** the file is created with mode `600`

#### Scenario: Existing permissive .env is tightened

- **WHEN** `deploy.sh` runs against an existing `.env` whose permissions are broader than `600`
- **THEN** the script tightens them to `600`

### Requirement: Transport-security settings follow the configured scheme

The application's cookie security, SSL redirect, and HTTP Strict Transport Security settings SHALL be derived from the configured public scheme so that enabling HTTPS does not require manually flipping several independent flags. Explicit environment overrides SHALL still take precedence. The behavior SHALL be documented in the production checklist.

#### Scenario: HTTPS scheme enables transport hardening

- **WHEN** the configured public scheme is `https`
- **THEN** session and CSRF cookies are marked `Secure`, SSL redirect is enabled, and HSTS is emitted
- **AND** the operator does not need to set each flag individually

#### Scenario: HTTP scheme keeps local development working

- **WHEN** the configured public scheme is `http`
- **THEN** secure cookies and SSL redirect remain disabled unless explicitly overridden

#### Scenario: Explicit overrides win

- **WHEN** an operator sets the individual security flags explicitly
- **THEN** the explicit values are honored over the scheme-derived defaults
