# Tier 2 Plan 1 — Data Model & Tier Guard Implementation Plan

> **Execution:** Implement this plan one task at a time; each task ends in a green test run and a commit. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Tier 2 in the model layer and add the `CurriculumMetadata` companion model, so curriculum documents can be stored with the metadata later phases key off — with no extraction, resolution, or access logic yet.

**Architecture:** Widen the existing tier guard (`Document.ENABLED_TIERS` + the DB `CheckConstraint`) from Tier-1-only to Tier-1-and-2, keeping the constraint as a physical guard that still refuses Tier 3. Add `CurriculumMetadata` as a one-to-one companion to `Document`, so `Document` stays tier-agnostic. All changes are additive and migration-backed.

**Tech Stack:** Django 5.2, PostgreSQL + `pgvector`, `django.contrib.postgres.fields.ArrayField`, `psycopg` 3, pytest + pytest-django (`uv run pytest`).

**Spec:** `docs/design/2026-07-03-tier2-lesson-plan-schema.md` (§2.1, §2.4). This plan is Plan 1 of a 5-plan sequence (see that spec's §8 scope boundary).

## Global Constraints

- **Access scoping lives in retrieval, never in the prompt.** This plan adds no retrieval logic; it must not weaken `visible_documents()`.
- **Tier discipline is physical.** The DB `CheckConstraint` must continue to reject Tier 3 rows by any code path (raw ORM save, bulk import, future bug). Widening is deliberate and migrated.
- **Synthetic data only.** No real student data anywhere, ever — not even as a test fixture.
- **Boring stack, cheap hardware.** Django + Postgres only; no new runtime dependencies in this plan.
- **Tests run with `uv run pytest`.** Postgres must be up (`docker compose up -d`).

---

### Task 1: Widen the tier guard to Tier 2 (still block Tier 3)

**Files:**
- Modify: `corpus/models.py` (`Document.ENABLED_TIERS` at line 22; the `CheckConstraint` in `Meta.constraints` at lines 63-70)
- Test: `tests/test_models.py` (rewrite `test_document_rejects_tiers_above_one` at lines 33-38 and `test_database_refuses_a_direct_tier_two_save` at lines 41-47)
- Create: `corpus/migrations/0004_widen_tier_guard_to_tier_2.py` (generated)

**Interfaces:**
- Consumes: existing `Document.Tier` IntegerChoices (`TIER_1=1, TIER_2=2, TIER_3=3`), existing `Document.clean()` (guards on `ENABLED_TIERS`).
- Produces: `Document.ENABLED_TIERS == (Tier.TIER_1, Tier.TIER_2)`; a DB constraint named `document_enabled_tiers_only` with condition `Q(tier__in=[1, 2])`. Later plans rely on being able to save Tier 2 `Document` rows.

- [ ] **Step 1: Rewrite the tier-guard tests to the new expectation (Tier 2 allowed, only Tier 3 rejected)**

In `tests/test_models.py`, replace the two existing tier-guard tests with:

```python
def test_document_rejects_only_tier_three():
    """Tier 1 and Tier 2 are enabled; only Tier 3 (student records) is refused by clean()."""
    ok = Document(title="Curriculum map", tier=2)
    ok.full_clean()  # must not raise

    bad = Document(title="Out of scope", tier=3)
    with pytest.raises(ValidationError):
        bad.full_clean()


def test_database_refuses_a_direct_tier_three_save():
    """clean() guards the admin path, but a raw ORM save bypasses validation.
    The CheckConstraint keeps the tier discipline physical: the database itself
    still rejects a Tier 3 row, so no code path can slip student-data-tier
    documents in. Tier 2 now saves cleanly."""
    Document.objects.create(title="Legit Tier 2 map", tier=2)  # must not raise
    with pytest.raises(IntegrityError):
        Document.objects.create(title="Sneaky Tier 3", tier=3)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_models.py::test_document_rejects_only_tier_three tests/test_models.py::test_database_refuses_a_direct_tier_three_save -v`
Expected: FAIL — `full_clean()` raises `ValidationError` for tier=2 (still rejected by the old `ENABLED_TIERS`), and/or `create(tier=2)` raises `IntegrityError` (old `Q(tier=1)` constraint).

- [ ] **Step 3: Widen `ENABLED_TIERS` and the constraint in `corpus/models.py`**

Change the enabled tiers (line 22):

```python
    ENABLED_TIERS = (Tier.TIER_1, Tier.TIER_2)
```

Replace the `CheckConstraint` in `Meta.constraints` (keep the surrounding comment, updated):

```python
        constraints = [
            # The tier discipline made physical: the database itself refuses to
            # store anything above the enabled tiers, so no code path — a raw ORM
            # save, a bulk import, a future bug — can slip student-data-tier
            # (Tier 3) rows in behind the clean() validation. Keep this in
            # lockstep with ENABLED_TIERS; widening the corpus is a deliberate,
            # migrated change.
            models.CheckConstraint(
                condition=Q(tier__in=[1, 2]), name="document_enabled_tiers_only"
            ),
        ]
```

- [ ] **Step 4: Generate the migration**

Run: `uv run python manage.py makemigrations corpus --name widen_tier_guard_to_tier_2`
Expected: creates `corpus/migrations/0004_widen_tier_guard_to_tier_2.py` with `RemoveConstraint(model_name="document", name="document_tier_1_only")` and `AddConstraint(... name="document_enabled_tiers_only" ...)`. Open the file and confirm those two operations are present and nothing else.

- [ ] **Step 5: Apply the migration**

Run: `uv run python manage.py migrate corpus`
Expected: `Applying corpus.0004_widen_tier_guard_to_tier_2... OK`.

- [ ] **Step 6: Run the full model test file to verify pass + no regressions**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS — the two rewritten tests pass, and the existing `test_document_scopes_to_roles`, `test_document_defaults_to_tier_one_and_pending_status`, chunk tests, etc. still pass.

- [ ] **Step 7: Commit**

```bash
git add corpus/models.py corpus/migrations/0004_widen_tier_guard_to_tier_2.py tests/test_models.py
git commit -m "Enable Tier 2 in the corpus tier guard, still blocking Tier 3"
```

---

### Task 2: Add the `CurriculumMetadata` model

**Files:**
- Modify: `corpus/models.py` (add `from django.contrib.postgres.fields import ArrayField` import near the top; add the `CurriculumMetadata` class after `Chunk`)
- Test: `tests/test_curriculum_metadata.py` (create)
- Create: `corpus/migrations/0005_curriculummetadata.py` (generated)

**Interfaces:**
- Consumes: `Document` (Tier 2 rows now saveable, from Task 1).
- Produces: `CurriculumMetadata` one-to-one with `Document` via `related_name="curriculum"`. Field names and choice enums (`ArtifactType`, `AuthorshipLevel`, `Subject`, `DocumentMode`, `LifecycleStatus`) that Plans 2, 3, and 5 read from and write to. Access-scoping fields: `authorship_level`, `school_year`, `sis_teacher_id`, `sis_section_id`. Retrieval/relevance fields: `artifact_types`, `merged_artifact`, `grades`, `subject`, `document_mode`, `lifecycle_status`, `revision_date`, `parent_document`, `field_provenance`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_curriculum_metadata.py`:

```python
import pytest

from corpus.models import CurriculumMetadata, Document

pytestmark = pytest.mark.django_db


def test_curriculum_metadata_attaches_to_a_tier_2_document():
    doc = Document.objects.create(title="Grade 3 Math Pacing Guide", tier=2)
    meta = CurriculumMetadata.objects.create(
        document=doc,
        artifact_types=[CurriculumMetadata.ArtifactType.PACING_GUIDE],
        authorship_level=CurriculumMetadata.AuthorshipLevel.DISTRICT_CONSENSUS,
        grades=["3"],
        subject=CurriculumMetadata.Subject.MATH,
        school_year="2025-26",
        lifecycle_status=CurriculumMetadata.LifecycleStatus.LIVING,
        field_provenance={"subject": {"source": "folder_path", "confidence": 0.9}},
    )
    assert doc.curriculum == meta
    assert meta.artifact_types == ["pacing_guide"]
    assert meta.subject == "math"
    assert meta.field_provenance["subject"]["source"] == "folder_path"


def test_curriculum_metadata_defaults_are_empty_not_null():
    doc = Document.objects.create(title="Bare metadata", tier=2)
    meta = CurriculumMetadata.objects.create(document=doc)
    assert meta.artifact_types == []
    assert meta.grades == []
    assert meta.merged_artifact is False
    assert meta.field_provenance == {}


def test_one_curriculum_metadata_per_document():
    doc = Document.objects.create(title="Only one", tier=2)
    CurriculumMetadata.objects.create(document=doc)
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        CurriculumMetadata.objects.create(document=doc)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_curriculum_metadata.py -v`
Expected: FAIL — `ImportError: cannot import name 'CurriculumMetadata'`.

- [ ] **Step 3: Add the import and the model to `corpus/models.py`**

Add near the existing imports at the top:

```python
from django.contrib.postgres.fields import ArrayField
```

Add after the `Chunk` class:

```python
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

    document = models.OneToOneField(
        Document, on_delete=models.CASCADE, related_name="curriculum"
    )
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
        models.CharField(max_length=8), default=list, blank=True,
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
```

- [ ] **Step 4: Generate the migration**

Run: `uv run python manage.py makemigrations corpus --name curriculummetadata`
Expected: creates `corpus/migrations/0005_curriculummetadata.py` with a single `CreateModel` for `CurriculumMetadata`. Open it and confirm the `OneToOneField` to `Document` and the `ArrayField`/`JSONField` columns are present.

- [ ] **Step 5: Apply the migration**

Run: `uv run python manage.py migrate corpus`
Expected: `Applying corpus.0005_curriculummetadata... OK`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_curriculum_metadata.py -v`
Expected: PASS (all three tests).

- [ ] **Step 7: Run the whole suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS — existing model, retrieval-scoping, ingestion, chunking, and tabular tests are unaffected.

- [ ] **Step 8: Commit**

```bash
git add corpus/models.py corpus/migrations/0005_curriculummetadata.py tests/test_curriculum_metadata.py
git commit -m "Add CurriculumMetadata companion model for Tier 2 documents"
```

---

## Self-Review

**Spec coverage (§2.1, §2.4):**
- §2.4 tier-guard widening + physical Tier-3 block → Task 1. ✓
- §2.4 "existing tier-guard tests updated in lockstep" → Task 1 Step 1. ✓
- §2.1 every field (artifact_types, merged_artifact, authorship_level, grades, subject, school_year, sis_teacher_id, sis_section_id, document_mode, lifecycle_status, revision_date, parent_document, field_provenance) → Task 2 model. ✓
- §2.1 access-scoping vs retrieval-filter distinction → encoded in the docstring + field grouping (not enforced code here; enforcement is Plan 5's retrieval branch). ✓
- Out of scope for Plan 1 (correctly deferred): `AcademicStandard`/`StandardReference` (Plan 2), extraction/resolution (Plan 2), ingestion wiring (Plan 3), multi-role + relationship retrieval (Plans 4–5). No task should implement these.

**Placeholder scan:** none — every step has concrete code or an exact command.

**Type consistency:** `related_name="curriculum"` (used in Task 2 test as `doc.curriculum`) matches the model. Choice enums referenced in tests (`ArtifactType.PACING_GUIDE`, `AuthorshipLevel.DISTRICT_CONSENSUS`, `Subject.MATH`, `LifecycleStatus.LIVING`) all exist on the model. Constraint name `document_enabled_tiers_only` is used consistently in Task 1 Step 3 and its Interfaces block.

**Note for the implementer:** `makemigrations` autogenerates migration bodies, so exact migration file contents are not transcribed here — the steps tell you the command, the resulting filename, and exactly which operations to verify are present.
