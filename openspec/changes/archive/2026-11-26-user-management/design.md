# Design

## Context

Auth is Django's built-in `User` + `Group` roles (`viewer`/`reviewer`/`admin`) enforced by `core/permissions.py` (`role_required`, `user_has_any_role`, `can_manage_users` — defined but unused until now). `config/urls.py` wires only login/logout; Django admin sits at `/admin/` for superusers. `bootstrap` creates the `admin` superuser and `seed_roles` creates the groups. Templates live under `templates/` (base) and per-app `templates/` dirs; nav is a flat list in `templates/base.html`. Tests use `Client` + `Group` fixtures (`make_user` pattern in `documents/tests/test_review.py`, `tests/test_auth.py` for permission units).

## Goals / Non-Goals

**Goals:**

- Admin-only user management inside the app: list, create, edit roles, reset password, activate/deactivate.
- Self-service password change for every user; password reset flow reachable from login.
- Zero schema changes — `User`, `Group`, and Django's password-reset token machinery cover everything.
- Follow existing conventions: function views + `role_required`, server-rendered templates, `messages` for feedback, pytest + `Client`.

**Non-Goals:**

- Custom user model, profiles, avatars, or per-user permissions beyond the three roles.
- Email-based invites or self-registration.
- Replacing Django admin (it stays for superusers).
- Password policy enforcement beyond Django's validators (document the default).

## Decisions

### 1. New `accounts` app for user management

Create `accounts/` (views, urls, templates, tests) rather than growing `core/`. Views:

- `user_list` (GET): table of users — username, groups (badges), `is_active`, `last_login`, link to edit.
- `user_create` (GET/POST): username, password, role select (viewer/reviewer/admin). Uses `User.objects.create_user` + `user.groups.set([group])`. Duplicate username → form error.
- `user_edit` (GET/POST, `<pk>`): role multi-select restricted to `ALL_ROLES` (hierarchy means admin sees effective perms; store exactly the chosen groups), `is_active` toggle, password reset field (optional new password).
- Deactivation also calls `user.set_unusable_password()`? — **no**: keep the password so reactivation restores access; `is_active=False` already blocks `ModelBackend` auth and `user_has_any_role` checks `is_active`. Sessions: Django does not auto-kill sessions on deactivate; mitigate by checking `is_active` per request — `user_has_any_role` already returns False for inactive users on every decorated view, and `LoginView` rejects inactive users. Acceptable; document it.

All views: `@login_required` + `@role_required(ROLE_ADMIN)` (superusers pass via `user_has_any_role`).

Alternatives: put it in Django admin (rejected — English UI, `is_staff` requirement, exposes everything), management command only (rejected as sole path — no UI for non-technical admins; may add later).

### 2. Self-service password change via Django auth views

Wire in `config/urls.py`:

- `accounts/password_change/` → `PasswordChangeView` (template `registration/password_change_form.html`)
- `accounts/password_change/done/` → `PasswordChangeDoneView`
- `accounts/password_reset/` → `PasswordResetView` (template `registration/password_reset_form.html`)
- `accounts/reset/<uidb64>/<token>/` → `PasswordResetConfirmView`
- `accounts/reset/done/` → `PasswordResetDoneView`
- `accounts/reset/complete/` → `PasswordResetCompleteView`

`PasswordResetView` already implements the silent-unknown-user behavior. Email backend: add `EMAIL_BACKEND` setting defaulting to console (`django.core.mail.backends.console.EmailBackend`) with `EMAIL_HOST`/`EMAIL_PORT`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`DEFAULT_FROM_EMAIL` env-driven for SMTP later — no secrets committed; document in `.env.example` + `operations.md`.

Nav additions in `base.html`: "Usuarios" link shown when `user_has_any_role`-equivalent — templates can't call Python; expose a context processor `core/context_processors.py` adding `can_manage_users` (and reuse for future admin links). Simpler alternative: `{% if user.is_superuser or 'admin' in user.groups.all %}` — but hierarchy makes admin the only role needing it anyway; a tiny context processor is cleaner and testable. Also add "Cambiar contraseña" link next to the username.

### 3. Password reset tokens and throttling

Django's reset tokens expire after `PASSWORD_RESET_TIMEOUT` (default 3 days — set to 1 hour via settings for tighter window). No custom throttling in v1 (internal tool); note as future work if exposed beyond LAN.

### 4. Logging

`logger.info` on create/edit/role-change/reset/deactivate with actor username — matches `documents` logging conventions (`getLogger(__name__)`).

## Risks / Trade-offs

- Admin can lock themselves out by deactivating their own account → prevent self-deactivation (disable the checkbox for `request.user`) and prevent removing own admin role? Self-role-change is allowed but warn: if the last active admin demotes themselves, nobody can manage users. Guard: block edits that would leave zero active admins (count check before save).
- Password reset emails go to console by default → document that real delivery needs SMTP env vars; acceptable for LAN deployment.
- `is_staff` stays False for app users → they cannot reach `/admin/`; intentional.

## Migration Plan

No migrations. Deploy = code only; existing `admin` superuser unaffected. Rollback = revert deploy; no data changes.

## Open Questions

None blocking. (SMTP credentials are deployment config, not a design question.)
