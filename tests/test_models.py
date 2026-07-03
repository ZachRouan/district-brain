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


def test_document_rejects_tiers_above_one():
    """Tier 2/3 corpora are not enabled in this build; the model must refuse them."""
    for tier in (2, 3):
        doc = Document(title="Out of scope", tier=tier)
        with pytest.raises(ValidationError):
            doc.full_clean()


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
