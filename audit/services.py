from .models import AuditLog


def record_chat(user, conversation, question, answer_text, retrieved, *, refused=None, error=""):
    """Write the audit row for one exchange. Called inside the same database
    transaction that saves the answer: neither exists without the other.

    `refused` defaults to "retrieval was too thin" (no passages); callers pass
    it explicitly when an answer was withheld for another reason — e.g. the
    answer engine was unreachable — alongside an `error` note."""
    if refused is None:
        refused = not retrieved
    return AuditLog.objects.create(
        event=AuditLog.Event.CHAT,
        user=user,
        username=user.get_username(),
        role_slug=user.role.slug if user.role_id else "",
        conversation=conversation,
        question=question,
        answer=answer_text,
        refused=refused,
        error=error,
        retrieved=[
            {
                "rank": n,
                "chunk_id": r.chunk.id,
                "document_id": r.chunk.document_id,
                "document_title": r.chunk.document.title,
                "distance": round(float(r.distance), 4),
                "text": r.chunk.text,
            }
            for n, r in enumerate(retrieved, 1)
        ],
    )
