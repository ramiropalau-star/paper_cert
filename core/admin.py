from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User


class AdminRoleRequiredMixin:
    """Restrict a model admin to superusers or members of the ``admin`` group."""

    def _is_admin_user(self, request) -> bool:
        user = request.user
        if not user.is_active:
            return False
        return user.is_superuser or user.groups.filter(name="admin").exists()

    def has_module_permission(self, request) -> bool:
        return self._is_admin_user(request)

    def has_view_permission(self, request, obj=None) -> bool:
        return self._is_admin_user(request)

    def has_add_permission(self, request) -> bool:
        return self._is_admin_user(request)

    def has_change_permission(self, request, obj=None) -> bool:
        return self._is_admin_user(request)

    def has_delete_permission(self, request, obj=None) -> bool:
        return self._is_admin_user(request)


admin.site.unregister(User)


@admin.register(User)
class RoleRestrictedUserAdmin(AdminRoleRequiredMixin, BaseUserAdmin):
    """User management restricted to the application admin role."""
