"""Embedding drift must not silently corrupt retrieval.

Vectors from two different embedding models (or dimensions) are not comparable.
Each document records the embedder that produced its chunks; retrieval searches
only documents matching the *active* embedder, and check_embeddings finds and
re-ingests the mismatches.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command

from accounts.models import Role
from chat.retrieval import retrieve
from corpus.ingest import ingest_document
from corpus.models import Document

pytestmark = pytest.mark.django_db

User = get_user_model()

QUERY = "when can a phone be confiscated in class"
DOC_TEXT = "A phone confiscated in class is logged with the office and returned at the end of the day. " * 3


@pytest.fixture
def teacher():
    role = Role.objects.create(slug="teacher", name="Teacher")
    return User.objects.create_user(username="alvarez", password="x", role=role)


def ingest_scoped_doc(role, name="phone-policy.txt", text=DOC_TEXT):
    doc = Document.objects.create(title="Phone policy", tier=1)
    doc.allowed_roles.set([role])
    doc.source_file.save(name, ContentFile(text.encode()), save=True)
    result = ingest_document(doc)
    assert result.outcome == "ingested"
    doc.refresh_from_db()
    return doc


def retrieved_ids(user):
    return {r.chunk.document_id for r in retrieve(user, QUERY)}


def test_ingest_stamps_the_active_embedder_identity(teacher):
    doc = ingest_scoped_doc(teacher.role)
    # conftest forces the hash backend
    assert doc.embedding_backend == "hash"
    assert doc.embedding_model == ""
    assert doc.embedding_dim == 384
    assert doc.is_embedding_stale() is False


def test_document_embedded_under_a_different_backend_is_excluded_and_flagged(teacher):
    doc = ingest_scoped_doc(teacher.role)
    assert doc.id in retrieved_ids(teacher)  # searchable before drift

    # Simulate a model swap: the chunks were produced by a different embedder.
    Document.objects.filter(pk=doc.pk).update(
        embedding_backend="sentence_transformers",
        embedding_model="all-mpnet-base-v2",
        embedding_dim=768,
    )
    doc.refresh_from_db()

    assert doc.is_embedding_stale() is True
    assert doc.id not in retrieved_ids(teacher)  # excluded from search


def test_legacy_document_without_provenance_stays_searchable(teacher):
    """A document ingested before provenance tracking (blank backend, null dim)
    is treated as compatible, so an upgrade doesn't dark out the existing corpus."""
    doc = ingest_scoped_doc(teacher.role)
    Document.objects.filter(pk=doc.pk).update(embedding_backend="", embedding_model="", embedding_dim=None)
    doc.refresh_from_db()
    assert doc.has_embedding_provenance() is False
    assert doc.is_embedding_stale() is False
    assert doc.id in retrieved_ids(teacher)


def test_check_embeddings_reports_mismatches(teacher, capsys):
    doc = ingest_scoped_doc(teacher.role)
    Document.objects.filter(pk=doc.pk).update(
        embedding_backend="other", embedding_model="x", embedding_dim=99
    )
    call_command("check_embeddings")
    captured = capsys.readouterr()
    assert "STALE" in captured.out
    assert "Phone policy" in captured.out
    assert "need re-ingesting" in captured.err


def test_check_embeddings_fix_reingests_and_restores_searchability(teacher):
    doc = ingest_scoped_doc(teacher.role)
    Document.objects.filter(pk=doc.pk).update(
        embedding_backend="sentence_transformers", embedding_model="all-mpnet-base-v2", embedding_dim=768
    )
    doc.refresh_from_db()
    assert doc.id not in retrieved_ids(teacher)

    call_command("check_embeddings", "--fix")

    doc.refresh_from_db()
    assert doc.embedding_backend == "hash"
    assert doc.embedding_dim == 384
    assert doc.is_embedding_stale() is False
    assert doc.id in retrieved_ids(teacher)  # searchable again
