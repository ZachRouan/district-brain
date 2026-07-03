from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """One row per exchange: who asked, what was asked, exactly which passages
    were retrieved, and the answer as delivered.

    Append-only. User and conversation links are snapshotted (username,
    role_slug) and passages are denormalized into `retrieved`, so a row stays
    complete even if the user, conversation, or corpus is later deleted.
    """

    class Event(models.TextChoices):
        CHAT = "chat", "Chat exchange"

    event = models.CharField(max_length=20, choices=Event.choices, default=Event.CHAT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    username = models.CharField(max_length=150)
    role_slug = models.CharField(max_length=50, blank=True)
    conversation = models.ForeignKey("chat.Conversation", null=True, on_delete=models.SET_NULL)
    question = models.TextField()
    answer = models.TextField()
    retrieved = models.JSONField(
        default=list,
        help_text="Every chunk shown to the model: document, rank, distance, and the exact passage text.",
    )
    refused = models.BooleanField(
        default=False,
        help_text="True when no grounded answer was delivered — retrieval was too thin, "
        "or the answer engine failed (see error).",
    )
    error = models.TextField(
        blank=True,
        help_text="Set when the answer engine could not be reached or failed; the user got a "
        "friendly notice instead of an answer. Blank on normal exchanges.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.username} · {self.question[:60]}"
