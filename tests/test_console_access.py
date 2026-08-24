"""The operator console (Django admin) is superuser-only.

It is not role-scoped — it shows every chunk and every audit row — so a mere
`is_staff` flag, even with model permissions attached, must not open it.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from accounts.models import Role
from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()

SECRET = "Only administrators may read the incident response procedure."


@pytest.fixture
def admin_only_chunk():
    role = Role.objects.create(slug="admin", name="Administrator")
    doc = Document.objects.create(title="Incident response", tier=1, status=Document.Status.READY)
    doc.allowed_roles.set([role])
    Chunk.objects.create(document=doc, index=0, text=SECRET, embedding=get_embedder().embed_query(SECRET))
    return doc


@pytest.fixture
def staff_with_every_permission():
    teacher = Role.objects.create(slug="teacher", name="Teacher")
    user = User.objects.create_user(username="clerk", password="pw", role=teacher, is_staff=True)
    user.user_permissions.set(Permission.objects.all())
    return user


CONSOLE_PAGES = [
    "admin:index",
    "admin:corpus_chunk_changelist",
    "admin:corpus_document_changelist",
    "admin:audit_auditlog_changelist",
    "admin:accounts_user_changelist",
]


@pytest.mark.parametrize("page", CONSOLE_PAGES)
def test_staff_without_superuser_cannot_open_the_console(
    client, staff_with_every_permission, admin_only_chunk, page
):
    client.login(username="clerk", password="pw")
    response = client.get(reverse(page))
    assert response.status_code == 302  # bounced to the console login
    assert SECRET not in response.content.decode(errors="ignore")


def test_superuser_opens_the_console(client, admin_only_chunk):
    User.objects.create_superuser(username="root", password="pw")
    client.login(username="root", password="pw")
    assert client.get(reverse("admin:corpus_chunk_changelist")).status_code == 200


def test_console_tab_is_offered_only_to_superusers(client, staff_with_every_permission):
    client.login(username="clerk", password="pw")
    assert "Console" not in client.get(reverse("chat:home")).content.decode()
    User.objects.create_superuser(username="root", password="pw")
    client.login(username="root", password="pw")
    assert "Console" in client.get(reverse("chat:home")).content.decode()
