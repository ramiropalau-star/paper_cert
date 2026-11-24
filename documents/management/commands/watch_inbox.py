from django.core.management.base import BaseCommand

from documents.services.inbox import watch_inbox


class Command(BaseCommand):
    help = "Watch APP_INBOX_DIR and ingest dropped certificate files."

    def handle(self, *args, **options):
        watch_inbox()
