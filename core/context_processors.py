"""Template context helpers shared across the app."""

from core.permissions import ROLE_ADMIN, user_has_any_role


def permissions(request):
    return {
        "can_manage_users": user_has_any_role(request.user, (ROLE_ADMIN,)),
    }
