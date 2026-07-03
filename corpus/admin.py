from django.contrib import admin, messages

from .ingest import ingest_document
from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    actions = ["reingest"]
    list_display = ("title", "tier", "status", "last_updated", "role_list", "chunk_count", "ingested_at")
    list_filter = ("status", "tier", "allowed_roles")
    search_fields = ("title", "source_name")
    filter_horizontal = ("allowed_roles",)
    readonly_fields = ("status", "error_message", "content_hash", "created_at", "ingested_at")
    fields = (
        "title",
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

    @admin.display(description="Visible to")
    def role_list(self, obj):
        return ", ".join(obj.allowed_roles.values_list("name", flat=True)) or "— nobody —"

    @admin.display(description="Chunks")
    def chunk_count(self, obj):
        return obj.chunks.count()

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
