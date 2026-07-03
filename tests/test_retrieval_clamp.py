"""retrieve() does not trust its callers.

top_k and max_distance are hard-clamped to the caps in settings. A caller —
feature code, a tampered request, a bug — cannot ask for more passages, or a
looser relevance cutoff, than the caps allow. These tests prove the caps win
over the caller, not the other way round.
"""

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Role
from chat.retrieval import retrieve
from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()

QUERY = "when can a phone be confiscated in class"


@pytest.fixture
def teacher():
    role = Role.objects.create(slug="teacher", name="Teacher")
    return User.objects.create_user(username="alvarez", password="x", role=role)


def make_document_with_chunks(role, n):
    doc = Document.objects.create(title="Big policy", tier=1, status=Document.Status.READY)
    doc.allowed_roles.set([role])
    embedder = get_embedder()
    for i in range(n):
        text = f"Rule {i}: a phone confiscated in class goes to the office. Extra detail {i}."
        Chunk.objects.create(document=doc, index=i, text=text, embedding=embedder.embed_query(text))
    return doc


def test_top_k_is_hard_capped_regardless_of_caller(teacher):
    """A caller asking for 10000 passages gets at most the cap, never more."""
    make_document_with_chunks(teacher.role, n=25)
    results = retrieve(teacher, QUERY, top_k=10000)
    assert len(results) == 20  # settings.RETRIEVAL_TOP_K_CAP default


def test_caller_cannot_raise_top_k_above_the_cap(teacher, settings):
    settings.RETRIEVAL_TOP_K_CAP = 3
    make_document_with_chunks(teacher.role, n=25)
    assert len(retrieve(teacher, QUERY, top_k=10000)) == 3


def test_caller_cannot_loosen_max_distance_past_the_cap(teacher, settings):
    """A caller passing max_distance=99 is clamped to the cap, so an on-topic
    query still returns nothing once the cap is set below every real match."""
    settings.RETRIEVAL_MAX_DISTANCE_CAP = 0.001  # tighter than any real match
    make_document_with_chunks(teacher.role, n=3)
    assert retrieve(teacher, QUERY, max_distance=99) == []


def test_returned_distances_never_exceed_the_cap(teacher, settings):
    settings.RETRIEVAL_MAX_DISTANCE_CAP = 0.95
    make_document_with_chunks(teacher.role, n=5)
    results = retrieve(teacher, QUERY, max_distance=99)
    assert all(r.distance <= 0.95 for r in results)


def test_non_positive_top_k_is_rejected_not_silently_corrected(teacher):
    """The upper clamp is silent (a huge request is capped, not an error), but a
    nonsensical top_k <= 0 is a caller bug and should surface as one."""
    make_document_with_chunks(teacher.role, n=3)
    for bad in (0, -5):
        with pytest.raises(ValueError):
            retrieve(teacher, QUERY, top_k=bad)


def test_negative_max_distance_is_rejected(teacher):
    """Cosine distance is never < 0, so a negative cutoff is nonsense input, not
    an over-request: reject loudly rather than clamp. (max_distance=0 is valid —
    exact-match-only — and is left alone.)"""
    make_document_with_chunks(teacher.role, n=3)
    with pytest.raises(ValueError):
        retrieve(teacher, QUERY, max_distance=-0.5)
    assert retrieve(teacher, QUERY, max_distance=0) == []  # valid, just matches nothing
