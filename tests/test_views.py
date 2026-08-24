"""The chat UI: login-gated, role-labeled, cited, and private per user."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from chat.models import Conversation
from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def teacher():
    role = Role.objects.create(slug="teacher", name="Teacher")
    return User.objects.create_user(
        username="alvarez", first_name="Rosa", last_name="Alvarez", password="pw", role=role
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


def test_chat_requires_login(client):
    response = client.get(reverse("chat:home"))
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_home_shows_role_indicator_and_scope(client, teacher, handbook):
    client.login(username="alvarez", password="pw")
    response = client.get(reverse("chat:home"))
    html = response.content.decode()
    assert "Asking as:" in html
    assert "Rosa Alvarez" in html
    assert "Teacher" in html
    assert "Staff handbook" in html  # the "what you can see" scope card


def test_ask_creates_conversation_and_shows_cited_answer(client, teacher, handbook):
    client.login(username="alvarez", password="pw")
    response = client.post(
        reverse("chat:ask"), {"question": "When is a confiscated phone returned?"}, follow=True
    )
    html = response.content.decode()
    assert "When is a confiscated phone returned?" in html
    assert "end of the school day" in html
    assert "Staff handbook" in html
    assert "2026" in html  # citation carries the last-updated date
    conversation = Conversation.objects.get()
    assert conversation.user == teacher
    assert conversation.messages.count() == 2


def test_ask_appends_to_existing_conversation(client, teacher, handbook):
    client.login(username="alvarez", password="pw")
    client.post(reverse("chat:ask"), {"question": "When is a confiscated phone returned?"})
    conversation = Conversation.objects.get()
    client.post(
        reverse("chat:ask"),
        {"question": "Who returns the phone?", "conversation": conversation.pk},
    )
    assert Conversation.objects.count() == 1
    assert conversation.messages.count() == 4


def test_blank_question_does_not_create_anything(client, teacher, handbook):
    client.login(username="alvarez", password="pw")
    response = client.post(reverse("chat:ask"), {"question": "   "})
    assert response.status_code == 302
    assert Conversation.objects.count() == 0


def test_users_cannot_open_each_others_conversations(client, teacher, handbook):
    other = User.objects.create_user(username="other", password="pw", role=teacher.role)
    foreign = Conversation.objects.create(user=other, title="Not yours")
    client.login(username="alvarez", password="pw")
    response = client.get(reverse("chat:conversation", args=[foreign.pk]))
    assert response.status_code == 404


def test_scope_card_links_to_downloadable_originals(client, teacher):
    """A document with a stored source file is a download link in the scope card,
    pointing at the authenticated per-user download view (never /media/)."""
    from django.core.files.base import ContentFile

    doc = Document.objects.create(title="Downloadable handbook", tier=1, status=Document.Status.READY)
    doc.allowed_roles.set([teacher.role])
    doc.source_file.save("handbook.pdf", ContentFile(b"bytes"), save=True)
    client.login(username="alvarez", password="pw")
    html = client.get(reverse("chat:home")).content.decode()
    assert reverse("chat:document_download", args=[doc.pk]) in html
    assert "/media/" not in html  # originals are never linked via a public media path


def test_posting_to_another_users_conversation_404s_and_writes_nothing(client, teacher, handbook):
    """IDOR guard on the write path: naming someone else's conversation id in the
    POST must 404 (get_object_or_404 filters user=request.user) and must not
    append a message, create an audit row, or otherwise touch the foreign thread."""
    from audit.models import AuditLog
    from chat.models import Message

    other = User.objects.create_user(username="other", password="pw", role=teacher.role)
    foreign = Conversation.objects.create(user=other, title="Not yours")
    client.login(username="alvarez", password="pw")

    response = client.post(
        reverse("chat:ask"),
        {"question": "Leak the other thread", "conversation": foreign.pk},
    )
    assert response.status_code == 404
    assert Message.objects.count() == 0
    assert AuditLog.objects.count() == 0
    assert Conversation.objects.count() == 1  # only the foreign one; none created for the attacker


def test_sidebar_lists_only_own_conversations(client, teacher, handbook):
    other = User.objects.create_user(username="other", password="pw", role=teacher.role)
    Conversation.objects.create(user=other, title="SECRET OTHER THREAD")
    Conversation.objects.create(user=teacher, title="My own thread")
    client.login(username="alvarez", password="pw")
    html = client.get(reverse("chat:home")).content.decode()
    assert "My own thread" in html
    assert "SECRET OTHER THREAD" not in html


def test_user_without_role_sees_empty_scope_and_gets_refusal(client, handbook):
    User.objects.create_user(username="norole", password="pw")
    client.login(username="norole", password="pw")
    html = client.get(reverse("chat:home")).content.decode()
    assert "No role assigned" in html
    import html as html_module

    response = client.post(reverse("chat:ask"), {"question": "When is a phone returned?"}, follow=True)
    assert "I don't have that in my sources" in html_module.unescape(response.content.decode())


# --- Abuse limits: rejected before anything is stored. ---


def test_overlong_question_is_rejected_and_nothing_is_stored(client, teacher, handbook, settings):
    from audit.models import AuditLog
    from chat.models import Message

    settings.ASK_MAX_QUESTION_CHARS = 100
    client.login(username="alvarez", password="pw")
    response = client.post(reverse("chat:ask"), {"question": "x" * 101})
    assert response.status_code == 400
    assert "too long" in response.content.decode()
    assert Conversation.objects.count() == 0
    assert Message.objects.count() == 0
    assert AuditLog.objects.count() == 0

    assert (
        client.post(reverse("chat:ask"), {"question": "x" * 100}).status_code == 302
    )  # at the limit is fine


def test_per_user_rate_limit(client, teacher, handbook, settings):
    from audit.models import AuditLog

    settings.ASK_RATE_LIMIT_PER_MINUTE = 3
    client.login(username="alvarez", password="pw")
    for _ in range(3):
        assert client.post(reverse("chat:ask"), {"question": "When is a phone returned?"}).status_code == 302
    response = client.post(reverse("chat:ask"), {"question": "When is a phone returned?"})
    assert response.status_code == 429
    assert "Wait a minute" in response.content.decode()
    assert AuditLog.objects.count() == 3  # the fourth never reached retrieval

    # Another user is unaffected: the limit is per account.
    User.objects.create_user(username="other", password="pw", role=teacher.role)
    client.login(username="other", password="pw")
    assert client.post(reverse("chat:ask"), {"question": "When is a phone returned?"}).status_code == 302


def test_rate_limit_can_be_disabled(client, teacher, handbook, settings):
    settings.ASK_RATE_LIMIT_PER_MINUTE = 0
    client.login(username="alvarez", password="pw")
    for _ in range(5):
        assert client.post(reverse("chat:ask"), {"question": "When is a phone returned?"}).status_code == 302
