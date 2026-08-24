import logging
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from corpus.models import Document

from .models import Conversation
from .retrieval import visible_documents
from .services import ask

logger = logging.getLogger(__name__)

TOO_LONG = "That question is too long — please ask it in a sentence or two."
TOO_FAST = "You're asking faster than the answer engine can keep up. Wait a minute and try again."


def _shell_context(request, conversation=None):
    context = {
        "conversations": Conversation.objects.filter(user=request.user),
        "conversation": conversation,
        "visible_docs": visible_documents(request.user).order_by("title"),
    }
    if conversation is not None:
        context["thread"] = conversation.messages.prefetch_related("citations")
    return context


def _render_chat(request, conversation=None, status=200, **extra):
    return render(
        request, "chat/index.html", {**_shell_context(request, conversation), **extra}, status=status
    )


def _over_rate_limit(user):
    """True once `user` has asked more than ASK_RATE_LIMIT_PER_MINUTE questions
    in the current minute. Counted in the cache, keyed per user and minute."""
    limit = settings.ASK_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return False
    key = f"ask-rate:{user.pk}:{int(time.time() // 60)}"
    cache.add(key, 0, timeout=120)
    return cache.incr(key) > limit


@login_required
def home(request):
    """Empty thread with the composer — a conversation starts on first ask."""
    return _render_chat(request)


@login_required
def conversation_detail(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    return _render_chat(request, conversation)


@login_required
@require_POST
def ask_view(request):
    question = request.POST.get("question", "").strip()
    conversation_id = request.POST.get("conversation")

    conversation = None
    if conversation_id:
        conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)

    if not question:
        return redirect(conversation or "chat:home")

    # Abuse limits are checked before anything is stored or retrieved, so a
    # rejected request costs one cache hit and leaves no rows behind.
    if len(question) > settings.ASK_MAX_QUESTION_CHARS:
        logger.warning(
            "Rejected %d-char question from user %s (limit %d)",
            len(question),
            request.user.pk,
            settings.ASK_MAX_QUESTION_CHARS,
        )
        return _render_chat(request, conversation, status=400, error=TOO_LONG, question=question)
    if _over_rate_limit(request.user):
        logger.warning(
            "Rate-limited user %s (limit %d/min)", request.user.pk, settings.ASK_RATE_LIMIT_PER_MINUTE
        )
        return _render_chat(request, conversation, status=429, error=TOO_FAST, question=question)

    if conversation is None:
        conversation = Conversation.objects.create(user=request.user)

    ask(request.user, conversation, question)
    return redirect("chat:conversation", pk=conversation.pk)


@login_required
def document_download(request, pk):
    """Stream a document's original source file — but ONLY if the requesting user
    is entitled to it under the same retrieval scope that governs answers.

    This is the ONLY sanctioned way to fetch an original file. MEDIA_ROOT is
    never served directly (see districtbrain/urls.py), because a public /media/
    location would let anyone fetch any PDF by URL, bypassing role scoping — the
    one thing the product must never allow.

    Out-of-scope (or nonexistent) documents 404, not 403, so a user cannot even
    learn that a document they can't see exists. Superusers (console operators)
    may download anything for corpus management.
    """
    if request.user.is_superuser:
        document = get_object_or_404(Document, pk=pk)
    else:
        document = get_object_or_404(visible_documents(request.user), pk=pk)

    if not document.source_file:
        raise Http404("This document has no stored source file.")

    return FileResponse(
        document.source_file.open("rb"),
        as_attachment=True,
        filename=document.source_file.name.rsplit("/", 1)[-1],
    )
