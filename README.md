# District Brain

**Your district's entire knowledge, on your own hardware, answering only to your people.**

District Brain is a locally hosted, retrieval-augmented AI assistant for K-12 school
districts. Staff ask questions in plain language — *"What's our device-confiscation
policy?"*, *"What time does early release end on Wednesdays?"* — and get answers grounded
in the district's own documents, with a citation to the exact passage on every claim.

This repository is the **Tier 1** build: board policies, handbooks, schedules,
procedures, and board minutes. **No student data is involved at this tier.**

## Why it's different

- **Access control lives in retrieval, not in the prompt.** A user's question only ever
  searches documents their role is allowed to see. Documents outside their scope never
  reach the language model, so they cannot leak — not by jailbreak, not by prompt
  injection hidden inside a document.
- **Local-first.** Documents, embeddings, the vector index, and the audit log live on a
  server the district owns. The default answer engine requires no external service.
- **Every question is logged.** Who asked, what was asked, exactly which passages were
  retrieved, and the answer as delivered — admin-viewable and CSV-exportable for the board.
- **Citations on every answer.** Each claim links to the source passage and shows the
  document's last-updated date. When retrieval finds nothing relevant, the assistant says
  *"I don't have that in my sources"* instead of guessing.
- **Boring, cheap stack.** Django, PostgreSQL + pgvector, a small local embedding model,
  server-rendered pages that are fast on a Chromebook. Runs on one modest box.

## Quick start (development)

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker with Compose.

```bash
git clone <this-repo> && cd district-brain
cp .env.example .env            # then set SECRET_KEY (command in the file's comment)
docker compose up -d            # PostgreSQL + pgvector on localhost:54320
uv sync                         # install Python dependencies
uv run python manage.py migrate
uv run python manage.py seed_demo   # roles, demo users, synthetic sample corpus
uv run python manage.py runserver 8800
```

Open http://localhost:8800 and log in as one of the demo users printed by `seed_demo`.
All sample documents are synthetic — a fictional district — so the demo works before you
load a single real document.

Full setup, operations, and hand-off documentation: **[docs/runbook.md](docs/runbook.md)**.

## Project layout

| Path | What it is |
|---|---|
| `accounts/` | Roles and users; role assignment drives everything retrieval may see |
| `corpus/` | Documents, chunks, embeddings, ingestion pipeline (`manage.py ingest`) |
| `chat/` | Retrieval, LLM backend abstraction, conversations, citations |
| `audit/` | Append-only log of every prompt, retrieval, and response |
| `sample_corpus/` | Synthetic Tier 1 documents for the demo seed |
| `docs/runbook.md` | Setup → operations → hand-off runbook |

## Security model (short version)

1. Role scoping is enforced in the retrieval query itself (`chat/retrieval.py`); there is
   no code path that searches unscoped chunks.
2. Corpus documents are treated as untrusted input. Instructions embedded in a document
   can, at worst, influence the wording of an answer for users already entitled to that
   document — they cannot widen retrieval scope. The test suite proves this.
3. Every exchange is audited atomically with the answer, including refusals.

Tests for these invariants live in `tests/` — run `uv run pytest`.

## License

MIT
