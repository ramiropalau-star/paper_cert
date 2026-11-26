# Spec Delta

## ADDED Requirements

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
