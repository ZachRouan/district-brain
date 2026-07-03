import pytest


@pytest.fixture(autouse=True)
def _deterministic_embeddings(settings):
    """Tests never download a model: the hash backend is local and deterministic."""
    settings.EMBEDDING_BACKEND = "hash"
