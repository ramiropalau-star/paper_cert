"""Re-run catalog classification without re-extracting or calling the LLM."""

from documents.models import Document
from documents.services.classification import classify_certificate


def reclassify_document(document: Document):
    """Reset ``document`` to ``extracted`` and re-run classification.

    Manual field freezes (``manual_fields``) are respected inside
    ``classify_certificate``. Returns the ``ClassificationResult``.
    """
    document.processing_state = Document.ProcessingState.EXTRACTED
    document.save(update_fields=["processing_state", "updated_at"])
    return classify_certificate(document)
