from django.core.management.base import BaseCommand

from documents.services.sync import sync_paperless_documents


class Command(BaseCommand):
    help = "Ingest into Django every Paperless document missing locally."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full",
            action="store_true",
            help="Ignore the sync watermark and reconcile the whole archive.",
        )

    def handle(self, *args, **options):
        full = bool(options.get("full"))
        result = sync_paperless_documents(full=full)
        mode = "completa" if full else "incremental"
        self.stdout.write(
            self.style.SUCCESS(
                f"Sync Paperless ({mode}): {result.scanned} escaneados, "
                f"{result.ingested} ingeridos, {result.duplicates} duplicados, "
                f"{len(result.errors)} errores."
            )
        )
        for error in result.errors:
            self.stdout.write(self.style.WARNING(f"  - {error}"))
