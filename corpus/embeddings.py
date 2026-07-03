"""Embedding backends. All of them run locally — that is a product requirement.

- SentenceTransformerEmbedder: the real one. Downloads its model once from
  Hugging Face, then works fully offline.
- HashEmbedder: deterministic bag-of-ngrams vectors with no model at all.
  Used by the test suite and available for model-free dev (EMBEDDING_BACKEND=hash).
"""

import hashlib
import math
import re

from django.conf import settings


class HashEmbedder:
    """Maps word and character-trigram features into a fixed number of hash
    buckets, L2-normalized. Texts sharing vocabulary get nearby vectors, which
    is all retrieval tests need — and it is a pure function of the text."""

    def __init__(self, dimensions=None):
        self.dimensions = dimensions or settings.EMBEDDING_DIM

    def _features(self, text):
        words = re.findall(r"[a-z0-9]+", text.lower())
        for word in words:
            yield word
            padded = f" {word} "
            for i in range(len(padded) - 2):
                yield padded[i : i + 3]

    def embed_query(self, text):
        vector = [0.0] * self.dimensions
        for feature in self._features(text):
            digest = hashlib.md5(feature.encode()).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed(self, texts):
        return [self.embed_query(t) for t in texts]


class SentenceTransformerEmbedder:
    """Local sentence-transformers model. Loaded lazily so importing this
    module (e.g. in tests or management commands) never touches the model."""

    def __init__(self, model_name=None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_query(self, text):
        return self.model.encode(text, normalize_embeddings=True).tolist()

    def embed(self, texts):
        return [v.tolist() for v in self.model.encode(list(texts), normalize_embeddings=True)]


_cache = {}


def get_embedder():
    """The embedder selected by settings, cached per backend so the model
    loads at most once per process."""
    backend = settings.EMBEDDING_BACKEND
    if backend not in _cache:
        if backend == "hash":
            _cache[backend] = HashEmbedder()
        elif backend == "sentence_transformers":
            _cache[backend] = SentenceTransformerEmbedder()
        else:
            raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend!r} (expected 'sentence_transformers' or 'hash')")
    return _cache[backend]
