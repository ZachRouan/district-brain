import pytest


@pytest.fixture(autouse=True)
def _deterministic_embeddings(settings):
    """Tests never download a model: the hash backend is local and deterministic.

    RETRIEVAL_MAX_DISTANCE defaults are calibrated for the real sentence-
    transformers model; hash vectors sit systematically farther apart, so tests
    run with a loose cutoff. Tests about the cutoff itself set their own.
    """
    settings.EMBEDDING_BACKEND = "hash"
    settings.RETRIEVAL_MAX_DISTANCE = 0.95


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    """Uploaded files land in a per-test directory, never in the repo."""
    settings.MEDIA_ROOT = tmp_path / "media"
