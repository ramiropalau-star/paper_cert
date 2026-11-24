from django.contrib import admin

from catalog.models import (
    CefrConversionRule,
    Entity,
    EntityAlias,
    Exam,
    Language,
    LanguageAlias,
)
from core.admin import AdminRoleRequiredMixin


class LanguageAliasInline(admin.TabularInline):
    model = LanguageAlias
    extra = 1


@admin.register(Language)
class LanguageAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = ("code", "name", "name_es", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "name_es")
    inlines = [LanguageAliasInline]


class EntityAliasInline(admin.TabularInline):
    model = EntityAlias
    extra = 1


@admin.register(Entity)
class EntityAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "aliases__alias")
    inlines = [EntityAliasInline]


class CefrConversionRuleInline(admin.TabularInline):
    model = CefrConversionRule
    extra = 0
    fields = (
        "score_min",
        "score_max",
        "cefr_level",
        "reference",
        "approved_by",
        "approved_at",
        "is_active",
    )
    readonly_fields = ("approved_at",)


@admin.register(Exam)
class ExamAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = ("name", "entity", "language", "is_active")
    list_filter = ("is_active", "language", "entity")
    search_fields = ("name", "entity__name")
    inlines = [CefrConversionRuleInline]


@admin.register(CefrConversionRule)
class CefrConversionRuleAdmin(AdminRoleRequiredMixin, admin.ModelAdmin):
    list_display = (
        "exam",
        "score_min",
        "score_max",
        "cefr_level",
        "is_active",
        "approved_by",
        "approved_at",
    )
    list_filter = ("is_active", "cefr_level", "exam")
    search_fields = ("exam__name", "reference", "approved_by")
    readonly_fields = ("approved_at",)
