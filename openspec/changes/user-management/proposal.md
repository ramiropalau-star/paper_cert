# Proposal

## Why

The application currently has a single superuser (`admin`) created at deploy time. The role model (viewer/reviewer/admin groups) already exists and every view is guarded by it, but there is no way to create or manage additional users from inside the app — the only path is Django admin, which is English-only, requires `is_staff`, and exposes the whole admin surface. As soon as a second reviewer or viewer is needed, user management becomes a blocker.

## What Changes

- **In-app user management**: an admin-only `/users/` section to list users, create users with an initial password and a role, edit roles, reset passwords, and activate/deactivate accounts.
- **Self-service password change**: every authenticated user can change their own password; the login flow gains a "forgot password" entry point using Django's built-in password reset (console email backend in dev, configurable SMTP later).
- **Role assignment stays group-based**: the existing viewer/reviewer/admin groups and the `can_manage_users` permission (already defined, currently unused) gate the new section.
- **Auditability**: user creation, role changes, password resets, and activation toggles are logged.
- **BREAKING**: none. Django admin remains available for superusers; no data model changes.

## Capabilities

### New Capabilities

- `user-management`: durable behavior for listing, creating, editing, disabling, and credential-managing application users, restricted to the admin role, plus self-service password change for every authenticated user.

### Modified Capabilities

None.

## Impact

- **New code**: `accounts` app or `core` views + `users/` templates + URLs; `UserAdmin`-free management views guarded by `can_manage_users`.
- **Auth**: `PasswordChangeView`, `PasswordResetView`/`PasswordResetConfirmView` wired into `config/urls.py`; email backend setting documented (console default).
- **Nav**: "Usuarios" entry in the base template shown only to admins.
- **Tests**: permission matrix (viewer/reviewer denied, admin allowed), create/edit/deactivate flows, self password change, reset flow with locmem email backend.
- **Risk**: low — additive feature; the only sensitive surface is password handling, which uses Django's built-in hashed storage and reset tokens.
