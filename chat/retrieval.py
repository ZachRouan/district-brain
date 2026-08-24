"""Role-scoped retrieval — the security boundary of the whole product.

Every path from a user's question to document content goes through
``retrieve()``, and ``retrieve()`` only ever searches chunks belonging to
``visible_documents(user)``. Scoping happens in the database query, before
similarity is even computed. There is deliberately no unscoped variant, and
none may ever be added: a document the user isn't entitled to must never
reach the model, no matter what any document's text says.

Covered by tests/test_retrieval_scoping.py — keep those passing.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q
from pgvector.django import CosineDistance

from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    chunk: Chunk
    distance: float  # cosine distance: 0 = identical, 2 = opposite


def visible_documents(user):
    """Every document this user's questions may search. The single source of
    truth for scope — the chat UI's "what you can see" card uses it too."""
    if user is None or not user.is_authenticated or user.role_id is None:
        return Document.objects.none()
    return Document.objects.filter(
        status=Document.Status.READY,
        tier__in=Document.ENABLED_TIERS,
        allowed_roles=user.role_id,
    )


def retrieve(user, query, top_k=None, max_distance=None):
    """Return the best-matching chunks for `query`, drawn exclusively from
    documents visible to `user`, nearest first. Chunks farther than
    `max_distance` are dropped — an empty result means "I don't have that",
    which callers must prefer over guessing.

    top_k and max_distance are hard-clamped to the caps in settings: this
    function does not trust its callers. Settings define the defaults; no
    caller — feature code, a tampered request, or a bug — can request more
    passages, or a looser relevance cutoff, than the caps allow. The clamp is
    one-directional on purpose: an excessive request is capped silently (a
    buggy top_k=10000 must not crash a user's question), but nonsensical input
    (top_k <= 0, or a negative max_distance — cosine distance is never < 0) is a
    caller error and is rejected rather than silently corrected."""
    top_k = top_k if top_k is not None else settings.RETRIEVAL_TOP_K
    max_distance = max_distance if max_distance is not None else settings.RETRIEVAL_MAX_DISTANCE
    if top_k <= 0:
        raise ValueError(f"top_k must be a positive integer, got {top_k!r}")
    if max_distance < 0:
        raise ValueError(f"max_distance must be non-negative, got {max_distance!r}")
    top_k = min(top_k, settings.RETRIEVAL_TOP_K_CAP)
    max_distance = min(max_distance, settings.RETRIEVAL_MAX_DISTANCE_CAP)

    scope = visible_documents(user)
    if not scope.exists():
        return []

    embedder = get_embedder()

    # Only search documents embedded with the *active* embedder. Vectors from
    # two different models (or dimensions) are not comparable, so a silent model
    # swap would corrupt similarity scoring. Documents embedded under a different
    # backend/model/dimension are excluded until re-ingested; documents with no
    # provenance recorded (legacy/pre-tracking) are treated as compatible.
    current = Q(
        embedding_backend=embedder.backend,
        embedding_model=embedder.model_name,
        embedding_dim=embedder.dimensions,
    )
    legacy = Q(embedding_backend="", embedding_dim__isnull=True)
    searchable = scope.filter(current | legacy)

    stale_count = scope.exclude(current | legacy).count()
    if stale_count:
        logger.warning(
            "Excluding %d document(s) from retrieval: embedded with a different backend/model than "
            "the active embedder (%s / %s / %s). Run `manage.py check_embeddings --fix`.",
            stale_count,
            embedder.backend,
            embedder.model_name,
            embedder.dimensions,
        )

    query_vector = embedder.embed_query(query)
    chunks = (
        Chunk.objects.filter(document__in=searchable.values("id"))
        .annotate(distance=CosineDistance("embedding", query_vector))
        .filter(distance__lte=max_distance)
        .order_by("distance")
        .select_related("document")[:top_k]
    )
    return [RetrievedChunk(chunk=c, distance=c.distance) for c in chunks]
