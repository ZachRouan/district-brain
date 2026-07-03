"""Tabular facts must be retrievable by natural-language questions within the
EXISTING 0.60 cutoff — the fix is chunk enrichment, never a looser threshold.

Uses the hash embedder (conftest default). A raw pipe-delimited schedule row
scores ~0.68+ against a plain question and is refused; the enriched, header-
labeled, heading-prefixed row lands under 0.60 and is retrieved.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from accounts.models import Role
from chat.retrieval import retrieve
from corpus.ingest import ingest_document
from corpus.models import Document

pytestmark = pytest.mark.django_db

User = get_user_model()

BELL_MD = """# Maple Ridge Bell Schedule 2026-27

## Regular Day

| Period | Start | End |
| --- | --- | --- |
| First Period | 7:50 AM | 8:38 AM |
| Second Period | 8:42 AM | 9:30 AM |
| Third Period | 9:34 AM | 10:22 AM |
| Fourth Period | 10:26 AM | 11:14 AM |
"""


@pytest.fixture
def teacher():
    role = Role.objects.create(slug="teacher", name="Teacher")
    return User.objects.create_user(username="alvarez", password="x", role=role)


def ingest_bell_schedule(teacher):
    doc = Document.objects.create(title="Bell Schedule 2026-27", tier=1)
    doc.allowed_roles.set([teacher.role])
    doc.source_file.save("bell.md", ContentFile(BELL_MD.encode()), save=True)
    assert ingest_document(doc).outcome == "ingested"
    return doc


def test_enriched_schedule_row_is_retrieved_within_the_existing_cutoff(teacher, settings):
    # conftest loosens the cutoff for the hash backend; pin the PRODUCTION value.
    settings.RETRIEVAL_MAX_DISTANCE = 0.60
    ingest_bell_schedule(teacher)

    results = retrieve(teacher, "what time does first period start")
    # retrieve() itself drops anything past 0.60, so a returned first-period row
    # proves it scored within the cutoff.
    first_period = [r for r in results if "First Period" in r.chunk.text]
    assert first_period, "the enriched first-period row must be retrieved within the 0.60 cutoff"
    assert first_period[0].distance <= 0.60
    # Each row is its own enriched chunk (context + header labels), not pipe soup.
    assert "Regular Day: Period: First Period, Start: 7:50 AM" in first_period[0].chunk.text


def test_the_row_is_below_cutoff_because_of_enrichment_not_a_looser_threshold(teacher, settings):
    """Guard against a future regression that 'fixes' recall by raising the cutoff:
    the raw pipe row would still be refused at 0.60; only enrichment gets it in."""
    settings.RETRIEVAL_MAX_DISTANCE = 0.60
    ingest_bell_schedule(teacher)
    results = retrieve(teacher, "what time does first period start")
    assert all(r.distance <= 0.60 for r in results)  # cutoff itself is unchanged
    assert results, "enrichment brought the row under the unchanged cutoff"
