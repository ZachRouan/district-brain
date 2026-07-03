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

    def generate(self, question, retrieved):
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={"messages": self.build_messages(question, retrieved), "temperature": 0.2},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


def get_llm_backend():
    return import_string(settings.LLM_BACKEND)()
