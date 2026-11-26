"""User management views for the admin role."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from core.permissions import ALL_ROLES, ROLE_ADMIN, role_required

logger = logging.getLogger(__name__)


def _role_groups() -> list[Group]:
    return [Group.objects.get(name=name) for name in ALL_ROLES]


def _active_admin_count() -> int:
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name=ROLE_ADMIN))
        .distinct()
        .count()
    )


def _user_is_last_active_admin(user: User, *, losing_admin: bool, deactivating: bool) -> bool:
    """True when saving would leave zero active admin-capable users."""
    if not (losing_admin or deactivating):
        return False
    remaining = _active_admin_count()
    if user.is_active and (user.is_superuser or user.groups.filter(name=ROLE_ADMIN).exists()):
        remaining -= 1
    return remaining <= 0


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET"])
def user_list(request):
    users = User.objects.prefetch_related("groups").order_by("username")
    return render(request, "accounts/user_list.html", {"users": users})


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def user_create(request):
    roles = _role_groups()
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        role_name = request.POST.get("role", "")
        role_names = {role_name} if role_name in ALL_ROLES else set()

        user = User(username=username) if username else None
        form_errors = []
        if not username:
            form_errors.append("El nombre de usuario es obligatorio.")
        elif User.objects.filter(username=username).exists():
            form_errors.append("Ya existe un usuario con ese nombre.")
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            form_errors.extend(exc.messages)
        if not role_names:
            form_errors.append("Seleccioná al menos un rol.")

        if form_errors:
            for error in form_errors:
                messages.error(request, error)
        else:
            new_user = User.objects.create_user(username=username, email=email, password=password)
            new_user.groups.set(Group.objects.filter(name__in=role_names))
            logger.info(
                "user_created actor=%s target=%s roles=%s",
                request.user.username,
                username,
                ",".join(sorted(role_names)),
            )
            messages.success(request, f"Usuario {username} creado.")
            return redirect("accounts:user_list")

    return render(
        request,
        "accounts/user_form.html",
        {"form_title": "Nuevo usuario", "roles": roles, "editing": None},
    )


@login_required
@role_required(ROLE_ADMIN)
@require_http_methods(["GET", "POST"])
def user_edit(request, pk: int):
    target = get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)
    roles = _role_groups()

    if request.method == "POST":
        role_name = request.POST.get("role", "")
        role_names = {role_name} if role_name in ALL_ROLES else set()
        email = request.POST.get("email", "").strip()
        if target == request.user:
            is_active = target.is_active
        else:
            is_active = request.POST.get("is_active") == "on"
        new_password = request.POST.get("new_password", "")

        errors = []
        losing_admin = ROLE_ADMIN in target.groups.values_list("name", flat=True) and (
            ROLE_ADMIN not in role_names
        )
        deactivating = target.is_active and not is_active
        if _user_is_last_active_admin(target, losing_admin=losing_admin, deactivating=deactivating):
            errors.append("No se puede dejar el sistema sin administradores activos.")
        if not role_names:
            errors.append("Seleccioná al menos un rol.")
        if new_password:
            try:
                validate_password(new_password, user=target)
            except ValidationError as exc:
                errors.extend(exc.messages)

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            target.groups.set(Group.objects.filter(name__in=role_names))
            if target.is_active != is_active:
                target.is_active = is_active
                target.save(update_fields=["is_active"])
                logger.info(
                    "user_%s actor=%s target=%s",
                    "activated" if is_active else "deactivated",
                    request.user.username,
                    target.username,
                )
            if target.email != email:
                target.email = email
                target.save(update_fields=["email"])
            if new_password:
                target.set_password(new_password)
                target.save(update_fields=["password"])
                logger.info(
                    "user_password_reset actor=%s target=%s",
                    request.user.username,
                    target.username,
                )
                messages.success(request, f"Contraseña de {target.username} actualizada.")
            else:
                logger.info(
                    "user_updated actor=%s target=%s roles=%s",
                    request.user.username,
                    target.username,
                    ",".join(sorted(role_names)),
                )
                messages.success(request, f"Usuario {target.username} actualizado.")
            return redirect("accounts:user_list")

    return render(
        request,
        "accounts/user_form.html",
        {
            "form_title": f"Editar {target.username}",
            "roles": roles,
            "editing": target,
            "selected_roles": set(target.groups.values_list("name", flat=True)),
        },
    )
