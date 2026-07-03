"""Role-scoped retrieval — the security boundary of the whole product.

Every path from a user's question to document content goes through
``retrieve()``, and ``retrieve()`` only ever searches chunks belonging to
``visible_documents(user)``. Scoping happens in the database query, before
similarity is even computed. There is deliberately no unscoped variant, and
none may ever be added: a document the user isn't entitled to must never
reach the model, no matter what any document's text says.

Covered by tests/test_retrieval_scoping.py — keep those passing.
"""

from dataclasses import dataclass

from django.conf import settings
from pgvector.django import CosineDistance

from corpus.embeddings import get_embedder
from corpus.models import Chunk, Document


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
    which callers must prefer over guessing."""
    top_k = top_k if top_k is not None else settings.RETRIEVAL_TOP_K
    max_distance = max_distance if max_distance is not None else settings.RETRIEVAL_MAX_DISTANCE

    scope = visible_documents(user)
    if not scope.exists():
        return []

    query_vector = get_embedder().embed_query(query)
    chunks = (
        Chunk.objects.filter(document__in=scope.values("id"))
        .annotate(distance=CosineDistance("embedding", query_vector))
        .filter(distance__lte=max_distance)
        .order_by("distance")
        .select_related("document")[:top_k]
    )
    return [RetrievedChunk(chunk=c, distance=c.distance) for c in chunks]
