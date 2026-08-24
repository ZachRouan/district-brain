from django import forms
from django.contrib import admin, messages
from django.db import models
from django.db.models import Count
from django.urls import reverse
from django.utils.html import format_html

from .ingest import ingest_document
from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    actions = ["reingest"]
    # The default file widget links the current file at its /media/ URL, which
    # this app never serves (see districtbrain/urls.py). Use a plain upload
    # widget and show the file through the scoped download view instead.
    formfield_overrides = {models.FileField: {"widget": forms.FileInput}}
    list_display = (
        "title",
        "tier",
        "status",
        "last_updated",
        "role_list",
        "chunk_count",
        "embedding_stale",
        "ingested_at",
    )
    list_filter = ("status", "tier", "allowed_roles")
    search_fields = ("title", "source_name")
    filter_horizontal = ("allowed_roles",)
    readonly_fields = ("current_file", "status", "error_message", "content_hash", "created_at", "ingested_at")
    fields = (
        "title",
        "current_file",
        "source_file",
        "source_name",
        "tier",
        "last_updated",
        "allowed_roles",
        "status",
        "error_message",
        "created_at",
        "ingested_at",
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request).prefetch_related("allowed_roles").annotate(n_chunks=Count("chunks"))
        )

    @admin.display(description="Current file")
    def current_file(self, obj):
        if not obj.pk or not obj.source_file:
            return "—"
        url = reverse("chat:document_download", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.source_file.name.rsplit("/", 1)[-1])

    @admin.display(description="Visible to")
    def role_list(self, obj):
        return ", ".join(r.name for r in obj.allowed_roles.all()) or "— nobody —"

    @admin.display(description="Chunks", ordering="n_chunks")
    def chunk_count(self, obj):
        return obj.n_chunks

    @admin.display(description="Embedding stale")
    def embedding_stale(self, obj):
        """Empty when this document's embeddings match the active embedder;
        a loud warning when a model/backend mismatch has excluded it from
        retrieval — re-ingest it (`manage.py check_embeddings --fix`)."""
        return "⚠ STALE — not searchable" if obj.is_embedding_stale() else ""

    def save_related(self, request, form, formsets, change):
        """Ingest right after save (and after roles are attached), so an
        uploaded document is searchable the moment the admin page confirms."""
        super().save_related(request, form, formsets, change)
        document = form.instance
        if not document.source_file:
            return
        result = ingest_document(document)
        if result.outcome == "error":
            messages.error(request, f"Ingestion failed: {result.message}")
        elif result.outcome == "ingested":
            messages.success(request, f"Ingested {result.chunk_count} chunks from “{document.title}”.")

    @admin.action(description="Re-ingest selected documents")
    def reingest(self, request, queryset):
        for document in queryset:
            result = ingest_document(document, force=True)
            level = messages.SUCCESS if result.outcome != "error" else messages.ERROR
            detail = f"{result.chunk_count} chunks" if result.outcome != "error" else result.message
            messages.add_message(request, level, f"{document.title}: {result.outcome} ({detail})")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    """Read-only view for verifying what a document was split into."""

    list_display = ("document", "index", "preview")
    list_filter = ("document",)
    search_fields = ("text",)

    @admin.display(description="Text")
    def preview(self, obj):
        return obj.text[:120]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
