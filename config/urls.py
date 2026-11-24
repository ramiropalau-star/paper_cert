"""Root URL configuration."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core.internal import internal_health
from core.views import health, home
from documents.views import (
    internal_acquire_text,
    internal_classify,
    internal_extract,
    internal_paperless_webhook,
)
from reports.views import internal_run_report

urlpatterns = [
    path("healthz", health, name="health"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
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
    path("catalog/", include("catalog.urls")),
    path("admin/", admin.site.urls),
    path("", home, name="home"),
]
