import os

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from corpus.models import Document

from .models import Conversation
from .retrieval import visible_documents
from .services import ask


def _shell_context(request, conversation=None):
    return {
        "conversations": Conversation.objects.filter(user=request.user),
        "conversation": conversation,
        "visible_docs": visible_documents(request.user).order_by("title"),
    }


@login_required
def home(request):
    """Empty thread with the composer — a conversation starts on first ask."""
    return render(request, "chat/index.html", _shell_context(request))


@login_required
def conversation_detail(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
    context = _shell_context(request, conversation)
    context["messages_with_citations"] = conversation.messages.prefetch_related("citations")
    return render(request, "chat/index.html", context)


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
        filename=os.path.basename(document.source_file.name),
    )
