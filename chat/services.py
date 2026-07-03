"""The ask() service: one question in, one grounded-and-cited answer out.

Order of operations is load-bearing:
1. retrieve() — role-scoped; the only source of document content
2. generate() — sees only what step 1 returned
3. persist message + citations atomically

Thin retrieval short-circuits to a refusal: no sources, no synthesis.
"""

import logging
import re

from django.db import transaction

from audit.services import record_chat

from .llm import LLMBackendUnavailable, get_llm_backend
from .models import Citation, Message
from .retrieval import retrieve

logger = logging.getLogger(__name__)

NO_SOURCES_ANSWER = (
    "I don't have that in my sources. I only answer from district documents "
    "I can see for your role — try rephrasing, or ask your administrator to "
    "add the relevant document."
)

UNREACHABLE_ANSWER = (
    "The answer engine is unreachable right now, so I can't answer this — "
    "please tell your District Brain administrator. Your question was logged."
)

# Match an optional leading space so a dropped marker doesn't strand a space
# before punctuation ("school [7]." -> "school.").
_CITATION_MARKER = re.compile(r" ?\[(\d+)\]")


def strip_hallucinated_citations(answer, source_count):
    """Remove any ``[n]`` citation marker the model invented — n < 1 or greater
    than the number of passages actually retrieved. Only real sources are
    numbered [1..source_count]; a marker outside that range points at nothing,
    so it is a hallucinated citation and gets dropped. This is a last-line
    hallucination guard: the model can misquote, but it cannot fabricate a
    citation the UI would render as a verifiable source."""

    def replace(match):
        n = int(match.group(1))
        if 1 <= n <= source_count:
            return match.group(0)
        logger.warning("Dropped hallucinated citation marker [%s] (only %s sources)", n, source_count)
        return ""

    return _CITATION_MARKER.sub(replace, answer).strip()


def ask(user, conversation, question):
    """Answer `question` inside `conversation`, returning the assistant Message."""
    retrieved = retrieve(user, question)

    error = ""
    refused = None  # record_chat derives the "thin retrieval" refusal by default
    grounded = bool(retrieved)  # attach citations only when an answer was actually produced
    if not retrieved:
        answer_text = NO_SOURCES_ANSWER
    else:
        try:
            answer_text = get_llm_backend().generate(question, retrieved)
            answer_text = strip_hallucinated_citations(answer_text, len(retrieved))
        except LLMBackendUnavailable as exc:
            # We retrieved sources but couldn't generate an answer: give the user
            # a plain notice, not a 500, and audit it as a refusal with the
            # reason. The retrieved passages stay in the audit for forensics, but
            # no citations are attached to a non-answer.
            logger.warning("LLM backend unavailable: %s", exc)
            answer_text = UNREACHABLE_ANSWER
            error = f"LLM backend unavailable: {exc}"
            refused = True
            grounded = False

    with transaction.atomic():
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
        answer = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, content=answer_text
        )
        if grounded:
            Citation.objects.bulk_create(
                Citation(
                    message=answer,
                    chunk=r.chunk,
                    rank=n,
                    distance=r.distance,
                    document_title=r.chunk.document.title,
                    document_last_updated=r.chunk.document.last_updated,
                    chunk_text=r.chunk.text,
                )
                for n, r in enumerate(retrieved, 1)
            )
        if not conversation.title:
            conversation.title = question[:200]
        conversation.save()  # also bumps updated_at for sidebar ordering
        record_chat(user, conversation, question, answer_text, retrieved, refused=refused, error=error)

    return answer
