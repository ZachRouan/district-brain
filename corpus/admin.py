from django.contrib import admin

from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
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
