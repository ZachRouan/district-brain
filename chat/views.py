from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
