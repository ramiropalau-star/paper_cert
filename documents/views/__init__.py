"""Upload, browse, review, catalog-admin, and internal pipeline views."""

from documents.views.browse import (
    document_gallery,
    document_list,
    document_original,
    document_queue,
    document_status,
    document_thumbnail,
)
from documents.views.catalog_admin import (
    field_alias_list,
    format_profile_list,
    format_profile_preview,
    verifier_config_list,
)
from documents.views.internal import (
    internal_acquire_text,
    internal_classify,
    internal_extract,
    internal_paperless_webhook,
)
from documents.views.review import (
    bulk_review,
    review_approve,
    review_detail,
    review_edit,
    review_history,
    review_reextract,
    review_reject,
    review_release_field,
    review_reprocess,
    review_teach_alias,
    review_validate,
    review_verify_now,
    review_verify_source,
)
from documents.views.uploads import delete, delete_all, upload

__all__ = [
    "bulk_review",
    "delete",
    "delete_all",
    "document_gallery",
    "document_list",
    "document_original",
    "document_queue",
    "document_status",
    "document_thumbnail",
    "field_alias_list",
    "format_profile_list",
    "format_profile_preview",
    "internal_acquire_text",
    "internal_classify",
    "internal_extract",
    "internal_paperless_webhook",
    "review_approve",
    "review_detail",
    "review_edit",
    "review_history",
    "review_reextract",
    "review_reject",
    "review_release_field",
    "review_reprocess",
    "review_teach_alias",
    "review_validate",
    "verifier_config_list",
    "review_verify_now",
    "review_verify_source",
    "upload",
]
