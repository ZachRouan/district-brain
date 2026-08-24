import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import AuditLog

# A cell starting with one of these is executed as a formula by Excel/Sheets.
# The question column is user-controlled text that lands in front of a board
# member, so every text cell is neutralised with a leading apostrophe.
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(_FORMULA_TRIGGERS) else text


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only console over the audit trail, with CSV export for the board."""

    list_display = (
        "created_at",
        "username",
        "role_slug",
        "short_question",
        "source_count",
        "refused",
        "had_error",
    )
    list_filter = ("role_slug", "refused", "created_at")
    search_fields = ("username", "question", "answer")
    date_hierarchy = "created_at"
    actions = ["export_csv"]

    @admin.display(description="Question")
    def short_question(self, obj):
        return obj.question[:80]

    @admin.display(description="Sources retrieved")
    def source_count(self, obj):
        return len(obj.retrieved)

    @admin.display(description="Engine error", boolean=True)
    def had_error(self, obj):
        return bool(obj.error)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Export selected entries to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="district-brain-audit.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["timestamp", "username", "role", "question", "answer", "sources", "refused", "error"]
        )
        for log in queryset.order_by("created_at"):
            sources = "; ".join(
                f"[{r['rank']}] {r['document_title']} (distance {r['distance']})" for r in log.retrieved
            )
            writer.writerow(
                [
                    log.created_at.isoformat(),
                    csv_safe(log.username),
                    csv_safe(log.role_slug),
                    csv_safe(log.question),
                    csv_safe(log.answer),
                    csv_safe(sources),
                    "yes" if log.refused else "no",
                    csv_safe(log.error),
                ]
            )
        return response
