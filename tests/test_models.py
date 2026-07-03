import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.models import Role
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_user_carries_a_role():
    teacher = Role.objects.create(slug="teacher", name="Teacher")
    user = User.objects.create_user(username="alvarez", password="x", role=teacher)
    assert user.role.slug == "teacher"


def test_user_role_is_optional_for_least_privilege_onboarding():
    user = User.objects.create_user(username="newhire", password="x")
    assert user.role is None


def test_document_scopes_to_roles():
    teacher = Role.objects.create(slug="teacher", name="Teacher")
    staff = Role.objects.create(slug="staff", name="Staff")
    doc = Document.objects.create(title="Staff handbook", tier=1)
    doc.allowed_roles.set([teacher, staff])
    assert set(doc.allowed_roles.values_list("slug", flat=True)) == {"teacher", "staff"}


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


def test_document_defaults_to_tier_one_and_pending_status():
    doc = Document.objects.create(title="Bell schedule")
    assert doc.tier == 1
    assert doc.status == Document.Status.PENDING


def test_chunks_store_embeddings_and_keep_document_order():
    doc = Document.objects.create(title="Policy JICJ", tier=1)
    Chunk.objects.create(document=doc, index=1, text="second", embedding=[0.0] * 384)
    Chunk.objects.create(document=doc, index=0, text="first", embedding=[1.0] * 384)
    texts = list(doc.chunks.values_list("text", flat=True))
    assert texts == ["first", "second"]


def test_chunk_index_is_unique_per_document():
    doc = Document.objects.create(title="Policy JICJ", tier=1)
    Chunk.objects.create(document=doc, index=0, text="a", embedding=[0.0] * 384)
    with pytest.raises(IntegrityError):
        Chunk.objects.create(document=doc, index=0, text="b", embedding=[0.0] * 384)
