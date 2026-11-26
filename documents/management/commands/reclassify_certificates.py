"""Re-run catalog classification on pending-review certificates.

Reuses the stored page texts, so no OCR or model calls are needed unless
``--reextract`` is passed (which re-runs the LLM extraction first).
Manual field freezes (``manual_fields``) are respected by the services.
"""

from django.core.management.base import BaseCommand

from documents.models import Document
from documents.services.classification import classify_certificate
from documents.services.extraction import extract_certificate
from documents.services.reclassification import reclassify_document


class Command(BaseCommand):
    help = "Re-run classification (optionally re-extraction) on pending documents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reextract",
            action="store_true",
            help="Re-run LLM extraction from stored pages before classifying.",
        )
        parser.add_argument(
            "--document",
            type=int,
            action="append",
            dest="document_ids",
            help="Limit to specific document ids (repeatable).",
        )

    def handle(self, *args, **options):
        queryset = (
            Document.objects.select_related("certificate")
            .filter(processing_state=Document.ProcessingState.PENDING_REVIEW)
            .exclude(certificate__isnull=True)
            .order_by("pk")
        )
        if options["document_ids"]:
            queryset = queryset.filter(pk__in=options["document_ids"])

        processed = 0
        for document in queryset:
            certificate = document.certificate
            if options["reextract"]:
                document.processing_state = Document.ProcessingState.TEXT_READY
                document.save(update_fields=["processing_state", "updated_at"])
                extracted = extract_certificate(document)
                if extracted.error:
                    self.stderr.write(
                        f"doc {document.pk} {document.original_filename}: "
                        f"extraction failed: {extracted.error}"
                    )
                    continue
                result = classify_certificate(document)
            else:
                result = reclassify_document(document)
            certificate.refresh_from_db()
            processed += 1
            self.stdout.write(
                f"doc {document.pk} {document.original_filename}: "
                f"lang={certificate.language_id} entity={certificate.entity_id} "
                f"exam={certificate.exam_id} cefr={certificate.cefr_level} "
                f"equiv={certificate.equivalence or '-'} "
                f"reasons={','.join(result.review_reasons) or '-'}"
            )

        self.stdout.write(self.style.SUCCESS(f"Reclassified {processed} documents."))
