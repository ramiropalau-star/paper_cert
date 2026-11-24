"""One-shot initialization: migrations, role groups, catalog seed, admin user."""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run migrations, seed roles/catalog, and create the admin user."

    def handle(self, *args, **options):
        call_command("migrate", verbosity=0)
        call_command("seed_roles", verbosity=0)
        call_command("seed_catalog", verbosity=0)

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        if username and password:
            user_model = get_user_model()
            if user_model.objects.filter(username=username).exists():
                self.stdout.write(f"Admin user '{username}' already exists.")
            else:
                user_model.objects.create_superuser(username, email, password)
                self.stdout.write(self.style.SUCCESS(f"Admin user '{username}' created."))
        else:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping admin creation."
            )
        # Best-effort: Paperless may not be running yet during first boot.
        try:
            call_command("provision_paperless_webhook", verbosity=0)
        except Exception as exc:  # noqa: BLE001 - bootstrap must not fail on this
            self.stdout.write(
                self.style.WARNING(
                    f"Paperless webhook provisioning skipped: {exc}. "
                    "The watcher retries it automatically once the stack is up."
                )
            )
        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))
