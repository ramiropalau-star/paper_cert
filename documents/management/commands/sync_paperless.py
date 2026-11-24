from django.core.management.base import BaseCommand

from documents.services.sync import sync_paperless_documents


class Command(BaseCommand):
    help = "Ingest into Django every Paperless document missing locally."

    def handle(self, *args, **options):
        result = sync_paperless_documents()
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync Paperless: {result.scanned} escaneados, "
                f"{result.ingested} ingeridos, {result.duplicates} duplicados, "
                f"{len(result.errors)} errores."
            )
        )
        for error in result.errors:
            self.stdout.write(self.style.WARNING(f"  - {error}"))
