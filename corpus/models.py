from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from pgvector.django import VectorField

from accounts.models import Role

# The tiers this build may store. Widening this is a deliberate, migrated change
# (the CheckConstraint below is derived from it, so `makemigrations --check`
# fails if the two ever drift).
ENABLED_TIER_VALUES = (1, 2)


class Document(models.Model):
    """One ingested source document and its corpus metadata.

    ENABLED_TIERS is the tier-discipline guardrail: this build refuses to hold
    anything above Tier 2 (never Tier 3 student records), even as test fixtures.
    """

    class Tier(models.IntegerChoices):
        TIER_1 = 1, "Tier 1 — policies, handbooks, schedules (no student data)"
        TIER_2 = 2, "Tier 2 — curriculum & lesson plans"
        TIER_3 = 3, "Tier 3 — student records (not enabled)"

    ENABLED_TIERS = tuple(map(Tier, ENABLED_TIER_VALUES))

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
    # Embedding provenance, stamped at ingest. Retrieval excludes any document
    # whose chunks were embedded with a backend/model/dimension different from
    # the active embedder — otherwise a model swap silently corrupts similarity
    # (vectors from two models are not comparable). check_embeddings surfaces and
    # re-ingests the mismatches.
    embedding_backend = models.CharField(max_length=50, blank=True, editable=False)
    embedding_model = models.CharField(max_length=255, blank=True, editable=False)
    embedding_dim = models.PositiveIntegerField(null=True, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ingested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title"]
        constraints = [
            # The tier discipline made physical: the database itself refuses to
            # store anything above the enabled tiers, so no code path — a raw ORM
            # save, a bulk import, a future bug — can slip student-data-tier
            # (Tier 3) rows in behind the clean() validation. Derived from
            # ENABLED_TIER_VALUES so the two cannot drift.
            models.CheckConstraint(
                condition=Q(tier__in=list(ENABLED_TIER_VALUES)), name="document_enabled_tiers_only"
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.tier not in self.ENABLED_TIERS:
            raise ValidationError(
                {
                    "tier": "Only Tier 1 and Tier 2 are enabled in this build. "
                    "Tier 3 (student records) requires board approval and a proven audit trail first."
                }
            )

    def embedding_identity(self):
        return (self.embedding_backend, self.embedding_model, self.embedding_dim)

    def has_embedding_provenance(self):
        """False for a document ingested before provenance was tracked (or via a
        raw ORM path in tests). Such documents are treated as legacy-compatible
        by retrieval, but check_embeddings flags them for a confirming re-ingest."""
        return bool(self.embedding_backend) or self.embedding_dim is not None

    def is_embedding_stale(self):
        """True when this document's chunks were embedded with a different
        backend/model/dimension than the active embedder — so retrieval excludes
        it until it is re-ingested. Legacy documents with no provenance recorded
        return False (assumed compatible)."""
        from corpus.embeddings import get_embedder

        if not self.has_embedding_provenance():
            return False
        embedder = get_embedder()
        return self.embedding_identity() != (embedder.backend, embedder.model_name, embedder.dimensions)


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


class CurriculumMetadata(models.Model):
    """Tier 2 curriculum metadata for a Document (curriculum maps, pacing
    guides, scope & sequence, unit/lesson plans). One-to-one so Document
    stays tier-agnostic.

    Access-scoping fields (authorship_level, school_year, sis_teacher_id,
    sis_section_id) parameterize the Phase 2 retrieval filter; every other
    field only narrows relevance. Metadata and standard codes are retrieval
    keys, never access grants — scoping stays in visible_documents().
    """

    class ArtifactType(models.TextChoices):
        CURRICULUM_MAP = "curriculum_map", "Curriculum map"
        SCOPE_AND_SEQUENCE = "scope_and_sequence", "Scope & sequence"
        PACING_GUIDE = "pacing_guide", "Pacing guide"
        UNIT_PLAN = "unit_plan", "Unit plan"
        LESSON_PLAN = "lesson_plan", "Lesson plan"

    class AuthorshipLevel(models.TextChoices):
        DISTRICT_CONSENSUS = "district_consensus", "District consensus"
        SCHOOL = "school", "School"
        INDIVIDUAL_TEACHER = "individual_teacher", "Individual teacher"

    class Subject(models.TextChoices):
        ELA = "ela", "English Language Arts"
        MATH = "math", "Mathematics"
        SCIENCE = "science", "Science"
        SOCIAL_STUDIES = "social_studies", "Social Studies"

    class DocumentMode(models.TextChoices):
        PRESCRIBED_PLANNED = "prescribed_planned", "Prescribed / planned"
        ENACTED_ACTUAL = "enacted_actual", "Enacted / actual"

    class LifecycleStatus(models.TextChoices):
        LIVING = "living", "Living (continuously revised)"
        POINT_IN_TIME = "point_in_time", "Point-in-time"

    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="curriculum")
    # Retrieval / relevance fields ------------------------------------------
    artifact_types = ArrayField(
        models.CharField(max_length=32, choices=ArtifactType.choices),
        default=list,
        blank=True,
        help_text="Multi-valued: districts collapse map+pacing+S&S into one file.",
    )
    merged_artifact = models.BooleanField(
        default=False, help_text="True when one file genuinely IS several artifact types."
    )
    grades = ArrayField(
        models.CharField(max_length=8),
        default=list,
        blank=True,
        help_text='Instructional grade(s), e.g. ["K", "1", "2"].',
    )
    subject = models.CharField(max_length=32, choices=Subject.choices, blank=True)
    document_mode = models.CharField(max_length=32, choices=DocumentMode.choices, blank=True)
    lifecycle_status = models.CharField(max_length=32, choices=LifecycleStatus.choices, blank=True)
    revision_date = models.DateField(null=True, blank=True)
    parent_document = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_curriculum_docs",
        help_text="Hierarchy: a lesson's unit, a unit's map.",
    )
    field_provenance = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-field {source, confidence}; supports coordinator override.",
    )
    # Access-scoping fields (consumed by the Phase 2 retrieval filter) -------
    authorship_level = models.CharField(
        max_length=32,
        choices=AuthorshipLevel.choices,
        blank=True,
        help_text="The access-decision key: consensus docs are staff-visible; "
        "teacher-authored plans are section-scoped.",
    )
    school_year = models.CharField(
        max_length=9,
        blank=True,
        help_text='e.g. "2025-26". MUST be sourced from the SIS/coordinator, '
        "never from file timestamps (plans are copied year to year).",
    )
    sis_teacher_id = models.CharField(max_length=128, blank=True)
    sis_section_id = models.CharField(max_length=128, blank=True)

    def __str__(self):
        return f"Curriculum metadata for {self.document.title}"
