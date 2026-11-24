from django.contrib import admin

from core.admin import AdminRoleRequiredMixin
from documents.models import Certificate, Document, DocumentPage, ReviewEvent


class DocumentPageInline(admin.TabularInline):
    model = DocumentPage
    extra = 0
    fields = ("page_number", "method", "ocr_confidence", "text")
    readonly_fields = ("page_number", "method", "ocr_confidence", "text")
    can_delete = False


class CertificateInline(admin.StackedInline):
    model = Certificate
    extra = 0
    fields = (
        "student_name",
        "language",
        "language_literal",
        "entity",
        "entity_literal",
        "exam",
        "exam_literal",
        "cefr_level",
        "cefr_source",
        "issue_date",
        "exam_date",
        "result_date",
        "review_status",
        "review_reasons",
    )
    readonly_fields = ("review_reasons",)


@admin.register(Document)
class DocumentAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = (
        "original_filename",
        "processing_state",
        "text_method",
        "page_count",
        "created_at",
    )
    list_filter = ("processing_state", "text_method", "created_at")
    search_fields = ("original_filename", "fingerprint", "paperless_document_id")
    readonly_fields = (
        "fingerprint",
        "size_bytes",
        "review_reasons",
        "created_at",
        "updated_at",
    )
    inlines = [DocumentPageInline, CertificateInline]


@admin.register(Certificate)
class CertificateAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = (
        "student_name",
        "language",
        "entity",
        "cefr_level",
        "review_status",
        "created_at",
    )
    list_filter = ("review_status", "cefr_level", "language", "entity")
    search_fields = (
        "student_name",
        "entity_literal",
        "language_literal",
        "document__original_filename",
    )
    readonly_fields = ("evidence", "field_confidence", "created_at", "updated_at")


@admin.register(ReviewEvent)
class ReviewEventAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = ("certificate", "event_type", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("certificate__student_name", "reason")
    readonly_fields = (
        "certificate",
        "event_type",
        "actor",
        "reason",
        "before",
        "after",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
