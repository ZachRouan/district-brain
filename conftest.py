import pytest

from corpus import embeddings


@pytest.fixture(autouse=True)
def _deterministic_embeddings(settings):
    """Tests never download a model: the hash backend is local and deterministic.

    RETRIEVAL_MAX_DISTANCE defaults are calibrated for the real sentence-
    transformers model; hash vectors sit systematically farther apart, so tests
    run with a loose cutoff. Tests about the cutoff itself set their own.
    """
    settings.EMBEDDING_BACKEND = "hash"
    settings.RETRIEVAL_MAX_DISTANCE = 0.95
    # retrieve() clamps to these caps, so an operator's .env must not be able to
    # undercut the loose test cutoff (or the cap tests' expectations).
    settings.RETRIEVAL_MAX_DISTANCE_CAP = 1.0
    settings.RETRIEVAL_TOP_K_CAP = 20
    embeddings._cache.clear()


@pytest.fixture(autouse=True)
def _mock_llm_backend(settings):
    """Tests never talk to a real answer engine, whatever the developer's .env
    says. The mock backend is deterministic; tests that exercise the llama.cpp
    backend select it explicitly and stub the HTTP call.
    """
    settings.LLM_BACKEND = "chat.llm.MockLLMBackend"
    settings.LLAMA_SERVER_URL = "http://127.0.0.1:9999"
    settings.GOOGLE_SSO_ENABLED = False


@pytest.fixture(autouse=True)
def _isolated_media(settings, tmp_path):
    """Uploaded files land in a per-test directory, never in the repo."""
    settings.MEDIA_ROOT = tmp_path / "media"
