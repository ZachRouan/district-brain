"""Downloading an original source file is governed by the SAME retrieval scope
that governs answers. Original files hold the full document text; if this view
leaked, it would bypass the whole access model — so it is tested like the
security boundary it is.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from accounts.models import Role
from corpus.models import Document

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def roles():
    return {
        "admin": Role.objects.create(slug="admin", name="Administrator"),
        "teacher": Role.objects.create(slug="teacher", name="Teacher"),
    }


@pytest.fixture
def users(roles):
    return {
        "teacher": User.objects.create_user(username="teacher_u", password="pw", role=roles["teacher"]),
        "admin_superuser": User.objects.create_superuser(username="root", password="pw"),
    }


def make_downloadable_doc(title, roles, body=b"CONFIDENTIAL ORIGINAL FILE BODY"):
    doc = Document.objects.create(title=title, tier=1, status=Document.Status.READY)
    doc.allowed_roles.set(roles)
    doc.source_file.save("policy.pdf", ContentFile(body), save=True)
    return doc


def download(client, doc):
    return client.get(reverse("chat:document_download", args=[doc.pk]))


def test_in_scope_role_can_download_the_original(client, roles, users):
    doc = make_downloadable_doc("Shared handbook", [roles["teacher"]], body=b"HANDBOOK BYTES")
    client.login(username="teacher_u", password="pw")
    response = download(client, doc)
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    assert b"".join(response.streaming_content) == b"HANDBOOK BYTES"


def test_out_of_scope_role_gets_404_not_403(client, roles, users):
    """404, not 403: a teacher must not even learn an admin-only document exists."""
    doc = make_downloadable_doc("Admin incident procedures", [roles["admin"]])
    client.login(username="teacher_u", password="pw")
    assert download(client, doc).status_code == 404


def test_anonymous_user_is_redirected_to_login(client, roles):
    doc = make_downloadable_doc("Shared handbook", [roles["teacher"]])
    response = download(client, doc)
    assert response.status_code == 302
    assert reverse("login") in response.url


def test_superuser_can_download_any_document(client, roles, users):
    """Console operators manage the corpus, so a superuser may fetch even a
    document outside their own role scope."""
    doc = make_downloadable_doc("Admin incident procedures", [roles["admin"]])
    client.login(username="root", password="pw")
    assert download(client, doc).status_code == 200


def test_missing_source_file_is_404(client, roles, users):
    doc = Document.objects.create(title="No file", tier=1, status=Document.Status.READY)
    doc.allowed_roles.set([roles["teacher"]])
    client.login(username="teacher_u", password="pw")
    assert download(client, doc).status_code == 404


def test_unready_document_is_not_downloadable_by_role(client, roles, users):
    """visible_documents() also gates on READY status; a still-processing upload
    is out of scope for a role user (though a superuser may still fetch it)."""
    doc = make_downloadable_doc("Draft", [roles["teacher"]])
    Document.objects.filter(pk=doc.pk).update(status=Document.Status.PROCESSING)
    client.login(username="teacher_u", password="pw")
    assert download(client, doc).status_code == 404
