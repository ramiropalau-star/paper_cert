"""Role helpers and view decorators for the application roles."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

ROLE_VIEWER = "viewer"
ROLE_REVIEWER = "reviewer"
ROLE_ADMIN = "admin"

ALL_ROLES = (ROLE_VIEWER, ROLE_REVIEWER, ROLE_ADMIN)
REVIEW_ROLES = (ROLE_REVIEWER, ROLE_ADMIN)
ADMIN_ROLES = (ROLE_ADMIN,)


def _effective_roles(user) -> set[str]:
    """Expand the role hierarchy: admin implies reviewer, which implies viewer."""
    groups = set(user.groups.values_list("name", flat=True))
    if ROLE_ADMIN in groups:
        groups.update({ROLE_ADMIN, ROLE_REVIEWER, ROLE_VIEWER})
    elif ROLE_REVIEWER in groups:
        groups.update({ROLE_REVIEWER, ROLE_VIEWER})
    return groups


def user_has_any_role(user, roles: tuple[str, ...]) -> bool:
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(_effective_roles(user) & set(roles))


def can_view_documents(user) -> bool:
    return user_has_any_role(user, ALL_ROLES)


def can_review_documents(user) -> bool:
    return user_has_any_role(user, REVIEW_ROLES)


def can_manage_catalog(user) -> bool:
    return user_has_any_role(user, ADMIN_ROLES)


def can_manage_users(user) -> bool:
    return user_has_any_role(user, ADMIN_ROLES)


def can_delete_documents(user) -> bool:
    return user_has_any_role(user, ADMIN_ROLES)


def can_generate_reports(user) -> bool:
    return user_has_any_role(user, ALL_ROLES)


def role_required(*roles: str):
    """Allow superusers or authenticated users in any of the given groups."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not user_has_any_role(request.user, roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
