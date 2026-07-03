"""The embedding abstraction: local backends only, deterministic option for tests."""

import math

from corpus.embeddings import HashEmbedder, get_embedder


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
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
