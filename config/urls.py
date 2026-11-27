"""Root URL configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import include, path

from core.internal import internal_health
from core.views import (
    admin_learning,
    admin_panel,
    admin_settings,
    admin_users,
    health,
    home,
    ready,
)
from documents.views import (
    internal_acquire_text,
    internal_classify,
    internal_extract,
    internal_paperless_webhook,
)
from reports.views import internal_run_report

urlpatterns = [
    path("healthz", health, name="health"),
    path("readyz", ready, name="ready"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password_change/",
        login_required(auth_views.PasswordChangeView.as_view()),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        login_required(auth_views.PasswordChangeDoneView.as_view()),
        name="password_change_done",
    ),
    path(
        "accounts/password_reset/",
        auth_views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("internal/healthz", internal_health, name="internal-health"),
    path(
        "internal/documents/<int:pk>/text/",
        internal_acquire_text,
        name="internal-document-text",
    ),
    path(
        "internal/documents/<int:pk>/extract/",
        internal_extract,
        name="internal-document-extract",
    ),
    path(
        "internal/documents/<int:pk>/classify/",
        internal_classify,
        name="internal-document-classify",
    ),
    path(
        "internal/paperless/webhook/",
        internal_paperless_webhook,
        name="internal-paperless-webhook",
    ),
    path(
        "internal/report-jobs/<int:pk>/run/",
        internal_run_report,
        name="internal-report-run",
    ),
    path("documents/", include("documents.urls")),
    path("reports/", include("reports.urls")),
    path("users/", include("accounts.urls")),
    path("catalog/", include("catalog.urls")),
    path("admin/", admin.site.urls),
    path("admin-panel/", admin_panel, name="admin-panel"),
    path("admin-panel/aprendizaje/", admin_learning, name="admin-learning"),
    path("admin-panel/usuarios/", admin_users, name="admin-users"),
    path("admin-panel/configuracion/", admin_settings, name="admin-settings"),
    path("", home, name="home"),
]
