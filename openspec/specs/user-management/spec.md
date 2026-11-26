# user-management Specification

## Purpose
Defines how administrators manage application users and how every user manages their own credentials, so the team can onboard reviewers and viewers without exposing Django admin or writing management commands.

## Requirements

### Requirement: Admins can list application users

The system SHALL provide an admin-only user list showing each user's username, roles, active state, and last login. Users without the admin role SHALL NOT see the section or its data.

#### Scenario: Admin sees the user list
- **WHEN** an admin opens the user management section
- **THEN** every user account is listed with username, roles, active state, and last login

#### Scenario: Non-admin is denied
- **WHEN** a viewer or reviewer opens the user management URL directly
- **THEN** access is denied and no user data is shown

### Requirement: Admins can create users with a role

The system SHALL let an admin create a user account with a username, an initial password, and exactly one role (viewer, reviewer, or admin). The created user SHALL be able to log in immediately.

#### Scenario: Create a reviewer
- **WHEN** an admin submits a valid username, password, and the reviewer role
- **THEN** the account is created, assigned the reviewer group, and can log in

#### Scenario: Duplicate username is rejected
- **WHEN** an admin submits a username that already exists
- **THEN** the form shows a clear error and no account is created

### Requirement: Admins can edit roles and account state

The system SHALL let an admin change a user's role assignment and activate or deactivate the account. Deactivating SHALL prevent login without deleting data.

#### Scenario: Change a user's role
- **WHEN** an admin assigns the reviewer role to a viewer
- **THEN** the user keeps viewer access through the role hierarchy and gains reviewer permissions

#### Scenario: Deactivate blocks login
- **WHEN** an admin deactivates a user
- **THEN** that user can no longer log in and their session is invalidated

### Requirement: Admins can reset a user's password

The system SHALL let an admin set a new password for any user. The new password SHALL be stored hashed and SHALL take effect immediately.

#### Scenario: Admin resets password
- **WHEN** an admin submits a new password for a user
- **THEN** the user can log in with the new password and the old one stops working

### Requirement: Users can change their own password

Every authenticated user SHALL be able to change their own password by confirming the current password. An incorrect current password SHALL be rejected with a clear error.

#### Scenario: Successful self-service change
- **WHEN** a user submits the correct current password and a valid new password
- **THEN** the password is updated and the user stays logged in

#### Scenario: Wrong current password
- **WHEN** a user submits an incorrect current password
- **THEN** the change is rejected and the password is unchanged

### Requirement: Users can request a password reset

The system SHALL offer a password reset flow reachable from the login page. The reset request SHALL NOT reveal whether the account exists, and the reset link SHALL expire.

#### Scenario: Reset email is sent for a known user
- **WHEN** a user requests a reset for an existing account
- **THEN** a reset email with a time-limited link is sent

#### Scenario: Unknown account is silent
- **WHEN** a reset is requested for a username that does not exist
- **THEN** the same confirmation page is shown and no email is sent
