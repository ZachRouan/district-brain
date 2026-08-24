"""seed_demo: a working, fully synthetic demo before any real document is loaded."""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.models import Role
from chat.retrieval import retrieve, visible_documents
from corpus.management.commands.seed_demo import CORPUS
from corpus.models import Chunk, Document

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def seeded():
    call_command("seed_demo", verbosity=0)


def test_seed_creates_roles_and_demo_users(seeded):
    assert set(Role.objects.values_list("slug", flat=True)) == {"admin", "teacher", "staff"}
    for username, role_slug in (
        ("demo_admin", "admin"),
        ("demo_teacher", "teacher"),
        ("demo_staff", "staff"),
    ):
        user = User.objects.get(username=username)
        assert user.role.slug == role_slug
    assert User.objects.get(username="demo_admin").is_staff


def test_seed_ingests_synthetic_corpus_ready_to_query(seeded):
    docs = Document.objects.all()
    assert docs.count() == len(CORPUS)
    assert all(d.status == Document.Status.READY for d in docs)
    assert all(d.tier == 1 for d in docs)
    assert all(d.last_updated is not None for d in docs)


def test_seeded_scoping_demo_works(seeded):
    """The demo story: teachers get policy answers; the admin-only incident
    procedures stay invisible to them."""
    teacher = User.objects.get(username="demo_teacher")
    admin = User.objects.get(username="demo_admin")

    results = retrieve(teacher, "when can a phone be confiscated from a student")
    assert results, "teacher should find the device policy"

    admin_only = Document.objects.get(title__icontains="incident")
    assert admin_only.id in set(visible_documents(admin).values_list("id", flat=True))
    assert admin_only.id not in set(visible_documents(teacher).values_list("id", flat=True))


def test_seed_is_idempotent(seeded):
    """A second run creates nothing and re-ingests nothing: the same chunk rows
    survive, so it is a true no-op rather than a wipe-and-reload."""
    before_users = User.objects.count()
    before_chunk_ids = set(Chunk.objects.values_list("id", flat=True))
    call_command("seed_demo", verbosity=0)
    assert Document.objects.count() == len(CORPUS)
    assert User.objects.count() == before_users
    assert set(Chunk.objects.values_list("id", flat=True)) == before_chunk_ids
