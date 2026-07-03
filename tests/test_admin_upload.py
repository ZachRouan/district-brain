"""Uploading a document through Django admin must ingest it immediately —
the admin is the corpus console; there is no separate 'now process it' step."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import Role
from corpus.models import Document

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def admin_client_(client):
    User.objects.create_superuser(username="root", password="rootpass")
    client.login(username="root", password="rootpass")
    return client


def test_admin_upload_ingests_and_scopes(admin_client_):
    staff = Role.objects.create(slug="staff", name="Staff")
    upload = SimpleUploadedFile(
        "visitor-policy.txt", b"All visitors must sign in at the main office and wear a badge."
    )
    response = admin_client_.post(
        reverse("admin:corpus_document_add"),
        {
            "title": "Visitor policy",
            "source_file": upload,
            "source_name": "",
            "tier": 1,
            "last_updated": "2026-05-01",
            "allowed_roles": [staff.pk],
        },
    )
    assert response.status_code == 302, response.context["adminform"].errors if response.context else response
    doc = Document.objects.get()
    assert doc.status == Document.Status.READY
    assert doc.chunks.count() == 1
    assert "wear a badge" in doc.chunks.first().text
    assert set(doc.allowed_roles.values_list("slug", flat=True)) == {"staff"}


def test_admin_reingest_action_recovers_errored_document(admin_client_):
    doc = Document.objects.create(title="Empty upload", tier=1)
    doc.source_file.save("empty.txt", SimpleUploadedFile("empty.txt", b"   "), save=True)
    doc.status = Document.Status.ERROR
    doc.save()
    doc.source_file.save("fixed.txt", SimpleUploadedFile("fixed.txt", b"Now with real content."), save=True)

    admin_client_.post(
        reverse("admin:corpus_document_changelist"),
        {"action": "reingest", "_selected_action": [doc.pk]},
    )
    doc.refresh_from_db()
    assert doc.status == Document.Status.READY
    assert doc.chunks.count() == 1
