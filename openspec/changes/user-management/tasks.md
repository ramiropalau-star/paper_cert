# Tasks

## 1. Accounts app skeleton

- [x] 1.1 Create `accounts/` app (`apps.py`, `__init__.py`), register in `INSTALLED_APPS`, add `accounts/` to `pyproject`/pytest discovery if needed; verify `manage.py check` passes.
- [x] 1.2 Add `core/context_processors.py` exposing `can_manage_users` (via `user_has_any_role`) and register it in `TEMPLATES['OPTIONS']['context_processors']`; verify with a template render test.

## 2. Admin user management views

- [x] 2.1 Implement `accounts/views.py`: `user_list`, `user_create`, `user_edit` guarded by `@login_required` + `@role_required(ROLE_ADMIN)`; wire `accounts/urls.py` and include at `users/` in `config/urls.py`.
- [x] 2.2 Build templates `accounts/user_list.html`, `user_form.html` (create + edit share), styled with existing `app.css` classes; show role badges, active state, last login.
- [x] 2.3 Implement create flow: username + password + single role → `create_user` + `groups.set`; duplicate username → form error, no account created.
- [x] 2.4 Implement edit flow: role assignment (any subset of ALL_ROLES stored as groups), `is_active` toggle (disabled for `request.user`), optional password reset field; block changes that would leave zero active admins.
- [x] 2.5 Add `logger.info` audit lines for create/edit/role-change/password-reset/deactivate with actor username.

## 3. Self-service credentials

- [x] 3.1 Wire Django auth views in `config/urls.py`: password change (+done), password reset request (+done), reset confirm (+done), reset complete — with `registration/` templates matching app style.
- [x] 3.2 Add `PASSWORD_RESET_TIMEOUT = 3600` (1h) and `EMAIL_BACKEND` defaulting to console; add `EMAIL_*`/`DEFAULT_FROM_EMAIL` env settings in `config/settings.py` reading from `APP` dict or dedicated env vars.
- [x] 3.3 Update `.env.example` with the new `APP_EMAIL_*` vars (commented/empty defaults) and document SMTP setup in `docs/operations.md`.
- [x] 3.4 Add "Cambiar contraseña" link in `base.html` nav for authenticated users; add "Usuarios" link shown only when `can_manage_users`.
- [x] 3.5 Add "¿Olvidaste tu contraseña?" link on `registration/login.html` pointing to the reset flow.

## 4. Tests

- [x] 4.1 Permission matrix tests: viewer/reviewer GET/POST to `/users/` → 403; anonymous → redirect to login; admin → 200.
- [x] 4.2 Create-user tests: success creates user + group + can log in; duplicate username rejected; missing/weak password rejected by validators.
- [x] 4.3 Edit tests: role change updates groups (hierarchy effective), deactivate blocks login (`client.login` fails / `is_active=False`), self-deactivate checkbox disabled, last-admin guard prevents orphaning.
- [x] 4.4 Password tests: admin reset makes old password fail and new one work; self change requires correct current password; wrong current password rejected.
- [x] 4.5 Reset flow tests with `locmem` email backend: known user gets email with link, unknown user sees same confirmation and no email; expired/invalid token rejected.
- [x] 4.6 Context processor test: `can_manage_users` true for admin/superuser, false for viewer/reviewer/anonymous.

## 5. Integration verification

- [x] 5.1 Run full pytest suite + `ruff check`/`format`; fix any regressions (nav template change touches every page).
- [x] 5.2 Manual smoke in the running stack: create a viewer user via UI, log in as them, verify they see Documentos but not Usuarios; change own password; request reset (console email shows link in app logs).
- [x] 5.3 `openspec validate user-management --strict` and fix artifact issues.
