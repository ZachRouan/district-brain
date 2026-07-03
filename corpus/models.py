from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

from accounts.models import Role


class Document(models.Model):
    """One ingested source document and its corpus metadata.

    ENABLED_TIERS is the tier-discipline guardrail: this build refuses to hold
    anything above Tier 1 (no student data), even as test fixtures.
    """

    class Tier(models.IntegerChoices):
        TIER_1 = 1, "Tier 1 — policies, handbooks, schedules (no student data)"
        TIER_2 = 2, "Tier 2 — curriculum & lesson plans (not enabled)"
        TIER_3 = 3, "Tier 3 — student records (not enabled)"

    ENABLED_TIERS = (Tier.TIER_1,)

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        ERROR = "error", "Error"

    title = models.CharField(max_length=255)
    source_file = models.FileField(upload_to="corpus/%Y/", blank=True)
    source_name = models.CharField(
        max_length=500, blank=True, help_text="Original filename or path the document came from."
    )
    tier = models.PositiveSmallIntegerField(choices=Tier.choices, default=Tier.TIER_1)
    last_updated = models.DateField(
        null=True,
        blank=True,
        help_text="When the document's content was last revised — shown with every citation.",
    )
    allowed_roles = models.ManyToManyField(
        Role,
        blank=True,
        related_name="documents",
        help_text="Only these roles can ever retrieve this document. No roles = nobody.",
    )
    content_hash = models.CharField(max_length=64, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ingested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            # The tier discipline made physical: the database itself refuses to
            # store anything above Tier 1 in this build, so no code path — a raw
            # ORM save, a bulk import, a future bug — can slip student-data-tier
            # rows in behind the clean() validation. Keep this in lockstep with
            # ENABLED_TIERS; widening the corpus is a deliberate, migrated change.
            models.CheckConstraint(condition=Q(tier=1), name="document_tier_1_only"),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.tier not in self.ENABLED_TIERS:
            raise ValidationError(
                {
                    "tier": "Only Tier 1 (no student data) is enabled in this build. "
                    "Tier 2/3 require board approval and a proven audit trail first."
                }
            )


class Chunk(models.Model):
    """A retrievable passage of a document, with its embedding.

    Chunks carry no scoping of their own — access is always resolved through
    the parent document's allowed_roles.
    """

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM)

    class Meta:
        ordering = ["document", "index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "index"], name="unique_chunk_index_per_document")
        ]

    def __str__(self):
        return f"{self.document.title} · chunk {self.index}"
