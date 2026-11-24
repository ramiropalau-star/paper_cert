from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from core.permissions import ROLE_ADMIN, ROLE_REVIEWER, ROLE_VIEWER


class Command(BaseCommand):
    help = "Create the viewer, reviewer, and admin role groups."

    def handle(self, *args, **options):
        for name in (ROLE_VIEWER, ROLE_REVIEWER, ROLE_ADMIN):
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS("Role groups ready: viewer, reviewer, admin."))
