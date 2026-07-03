"""Ingestion: file → clean text → chunks → embeddings, idempotently."""

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command

from accounts.models import Role
from corpus.ingest import ingest_document
from corpus.models import Document

pytestmark = pytest.mark.django_db

LONG_TEXT = "\n\n".join(
    f"Policy section {i}. Students shall be counted tardy if not seated when the bell rings. "
    "Three tardies convert to one absence for attendance accounting." for i in range(12)
)


def make_uploaded_document(text=LONG_TEXT, name="attendance-policy.txt", title="Attendance policy"):
    doc = Document.objects.create(title=title, tier=1)
    doc.source_file.save(name, ContentFile(text.encode()), save=True)
    return doc


def test_ingest_produces_ready_document_with_embedded_chunks():
    doc = make_uploaded_document()
    result = ingest_document(doc)
    doc.refresh_from_db()
    assert result.outcome == "ingested"
    assert doc.status == Document.Status.READY
    assert doc.content_hash
    assert doc.ingested_at is not None
    chunks = list(doc.chunks.all())
    assert len(chunks) > 1
    assert all(len(c.embedding) == 384 for c in chunks)
    assert "counted tardy" in chunks[0].text


def test_reingesting_unchanged_content_is_a_noop():
    doc = make_uploaded_document()
    ingest_document(doc)
    doc.refresh_from_db()
    before_ids = set(doc.chunks.values_list("id", flat=True))
    result = ingest_document(doc)
    doc.refresh_from_db()
    assert result.outcome == "unchanged"
    assert set(doc.chunks.values_list("id", flat=True)) == before_ids


def test_changed_content_replaces_chunks():
    doc = make_uploaded_document()
    ingest_document(doc)
    doc.refresh_from_db()
    before_ids = set(doc.chunks.values_list("id", flat=True))
    doc.source_file.save("attendance-policy.txt", ContentFile(b"A completely revised policy text."), save=True)
    result = ingest_document(doc)
    doc.refresh_from_db()
    assert result.outcome == "ingested"
    after_ids = set(doc.chunks.values_list("id", flat=True))
    assert after_ids.isdisjoint(before_ids)
    assert doc.chunks.count() == 1
    assert "revised policy" in doc.chunks.first().text


def test_empty_document_errors_instead_of_pretending():
    doc = make_uploaded_document(text="   \n\n  ")
    ingest_document(doc)
    doc.refresh_from_db()
    assert doc.status == Document.Status.ERROR
    assert doc.error_message
    assert doc.chunks.count() == 0


def test_ingest_command_creates_scoped_ready_documents(tmp_path):
    Role.objects.create(slug="teacher", name="Teacher")
    Role.objects.create(slug="staff", name="Staff")
    f = tmp_path / "bell-schedule.md"
    f.write_text("# Bell schedule\n\nFirst period begins at 7:50 AM. " * 3)
    call_command("ingest", str(f), "--roles", "teacher,staff")
    doc = Document.objects.get()
    assert doc.status == Document.Status.READY
    assert set(doc.allowed_roles.values_list("slug", flat=True)) == {"teacher", "staff"}
    assert doc.title == "Bell schedule"
    assert doc.source_name == str(f)
    assert doc.chunks.count() >= 1


def test_ingest_command_is_idempotent_per_source_path(tmp_path):
    Role.objects.create(slug="staff", name="Staff")
    f = tmp_path / "handbook.txt"
    f.write_text("Staff sign in at the front office each morning.")
    call_command("ingest", str(f), "--roles", "staff")
    call_command("ingest", str(f), "--roles", "staff")
    assert Document.objects.count() == 1


def test_ingest_command_rejects_unknown_role(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("Anything at all.")
    with pytest.raises(Exception, match="[Uu]nknown role"):
        call_command("ingest", str(f), "--roles", "wizard")
    assert Document.objects.count() == 0


def test_ingest_command_walks_directories(tmp_path):
    Role.objects.create(slug="staff", name="Staff")
    (tmp_path / "a.txt").write_text("Gym setup for assemblies takes one hour.")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.md").write_text("The cafeteria seats two hundred students.")
    (sub / "ignored.xlsx").write_bytes(b"binary")
    call_command("ingest", str(tmp_path), "--roles", "staff")
    assert Document.objects.count() == 2
