"""The embedding abstraction: local backends only, deterministic option for tests."""

import math

import pytest
from django.core.exceptions import ImproperlyConfigured

from corpus.embeddings import HashEmbedder, SentenceTransformerEmbedder, get_embedder


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def test_get_embedder_honors_settings(settings):
    settings.EMBEDDING_BACKEND = "hash"
    assert isinstance(get_embedder(), HashEmbedder)


def test_hash_embedder_is_deterministic():
    e = HashEmbedder(dimensions=384)
    assert e.embed_query("device confiscation policy") == e.embed_query("device confiscation policy")


def test_hash_embedder_dimension_matches_request():
    e = HashEmbedder(dimensions=384)
    assert len(e.embed_query("bell schedule")) == 384


def test_hash_embedder_ranks_similar_text_closer():
    e = HashEmbedder(dimensions=384)
    query = e.embed_query("when may a phone be confiscated from a student")
    same_topic = e.embed_query("a phone may be confiscated from a student when it disrupts class")
    other_topic = e.embed_query("the gym floor is resurfaced every August by the facilities crew")
    assert cosine(query, same_topic) > cosine(query, other_topic)


def test_hash_embedder_batches():
    e = HashEmbedder(dimensions=384)
    vectors = e.embed(["first text", "second text"])
    assert len(vectors) == 2
    assert vectors[0] == e.embed_query("first text")


def test_unknown_backend_is_rejected(settings):
    settings.EMBEDDING_BACKEND = "cloud-api"
    with pytest.raises(ValueError, match="Unknown EMBEDDING_BACKEND"):
        get_embedder()


def test_sentence_transformer_refuses_a_model_whose_width_does_not_match(monkeypatch, settings):
    """EMBEDDING_MODEL is operator-settable but the vector column is fixed at
    EMBEDDING_DIM; a mismatch must fail loudly on first use, not as a raw
    database error mid-ingest. Uses a stub sentence_transformers module so the
    test never loads a real model."""
    import sys
    import types

    class FakeModel:
        def __init__(self, name, **kwargs):
            self.name = name

        def get_sentence_embedding_dimension(self):
            return 768

    stub = types.ModuleType("sentence_transformers")
    stub.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", stub)
    settings.EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"

    with pytest.raises(ImproperlyConfigured, match="768-wide"):
        _ = SentenceTransformerEmbedder().model
