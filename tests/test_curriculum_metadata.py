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
