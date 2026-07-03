"""LLM backends behind one interface, selected by settings.LLM_BACKEND.

Both backends receive ONLY the chunks that scoped retrieval returned — prompt
assembly happens here, after the security boundary, never before it.

- MockLLMBackend: deterministic, no model. Echoes the retrieved passages, so
  the whole system is testable end-to-end and demos work with zero setup.
- LlamaCppServerBackend: a llama.cpp server's OpenAI-compatible API on the
  local network. Swap to it with LLM_BACKEND=chat.llm.LlamaCppServerBackend.
"""

import requests
from django.conf import settings
from django.utils.module_loading import import_string


class LLMBackendUnavailable(Exception):
    """The answer engine could not be reached or timed out. ask() turns this
    into a friendly notice for the user and an audited failure — never a 500."""

SYSTEM_PROMPT = """\
You are District Brain, the internal assistant for {district}. Answer the \
staff member's question using ONLY the numbered source passages provided. \
Cite the passage number in square brackets, like [1], after each claim. \
If the passages do not contain the answer, say exactly: \
"I don't have that in my sources." Do not use outside knowledge. Keep \
answers short and factual."""


def format_sources(retrieved):
    """Number the retrieved passages for citation, oldest metadata included."""
    lines = []
    for n, r in enumerate(retrieved, 1):
        updated = r.chunk.document.last_updated
        stamp = f", last updated {updated:%Y-%m-%d}" if updated else ""
        lines.append(f"[{n}] From “{r.chunk.document.title}”{stamp}:\n{r.chunk.text}")
    return "\n\n".join(lines)


class MockLLMBackend:
    """Deterministic echo of the retrieved context. What it prints is exactly
    what a real model would have been shown — which is what makes the
    scoping tests end-to-end proofs rather than unit checks."""

    def generate(self, question, retrieved):
        sources = format_sources(retrieved)
        return (
            f"Here is what your district's documents say (mock answer — "
            f"deterministic, no model attached):\n\n{sources}"
        )


class LlamaCppServerBackend:
    """llama.cpp `llama-server` speaking the OpenAI chat-completions API on
    the local network. No cloud service is involved."""

    def __init__(self, base_url=None, timeout=120):
        self.base_url = (base_url or settings.LLAMA_SERVER_URL).rstrip("/")
        self.timeout = timeout

    def build_messages(self, question, retrieved):
        return [
            {"role": "system", "content": SYSTEM_PROMPT.format(district=settings.DISTRICT_NAME)},
            {
                "role": "user",
                "content": f"Source passages:\n\n{format_sources(retrieved)}\n\nQuestion: {question}",
            },
        ]

    def build_payload(self, question, retrieved):
        payload = {
            "messages": self.build_messages(question, retrieved),
            "temperature": 0.2,
            "max_tokens": settings.LLM_MAX_TOKENS,
        }
        if settings.LLM_DISABLE_THINKING:
            # Requires the server's --jinja chat template; drops the reasoning
            # phase so the answer lands in `content` instead of reasoning_content.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return payload

    def generate(self, question, retrieved):
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json=self.build_payload(question, retrieved),
                timeout=self.timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            # A closet box, a crashed llama-server, a wrong URL: don't 500. Signal
            # unavailability so ask() can answer gracefully and audit the failure.
            raise LLMBackendUnavailable(f"{self.base_url}: {exc}") from exc
        response.raise_for_status()

        choice = response.json()["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
        if not content:
            # A reachable server that returns no answer text — most often a
            # reasoning model whose thinking consumed the whole token budget
            # (finish_reason "length") before emitting an answer, or a server not
            # started with --jinja so thinking couldn't be disabled. Treat it as a
            # failure, not a blank answer stored as if it were real.
            raise LLMBackendUnavailable(
                f"{self.base_url}: model returned an empty answer "
                f"(finish_reason={choice.get('finish_reason')!r}). If this is a reasoning model, "
                "run the server with --jinja and keep LLM_DISABLE_THINKING enabled, or raise LLM_MAX_TOKENS."
            )
        return content


def get_llm_backend():
    return import_string(settings.LLM_BACKEND)()
