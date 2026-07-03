# District Brain — Runbook

Operations manual for standing up, running, and handing off a Tier 1 District Brain
deployment. Written so a tech coordinator in another district can follow it start to
finish without the original author in the room.

> **Status: living document.** Sections are filled in as the corresponding feature lands.

## 1. What you're deploying

One box (on-prem server or district-owned VPS) running:

- **PostgreSQL 17 + pgvector** — documents, chunks, embeddings, audit log
- **Django app** — web UI, admin console, ingestion, retrieval
- **Embedding model** — small sentence-transformers model, runs locally on CPU
- **LLM backend** — starts as a deterministic mock (no model needed); swaps to a local
  llama.cpp server with one settings change

Nothing in the data path leaves the box. The only outbound network use is one-time:
installing packages and downloading the embedding model.

## 2. Requirements

- Linux server, 8+ GB RAM (16 GB recommended once a real LLM is enabled), ~20 GB disk
- Python 3.12 or 3.13, [uv](https://docs.astral.sh/uv/), Docker + Compose plugin
- A GPU is **not** required for Tier 1 with the mock backend; embeddings run on CPU.

## 3. Install

```bash
git clone <repo> district-brain && cd district-brain
cp .env.example .env
# Edit .env:
#   SECRET_KEY  — generate: python -c "import secrets; print(secrets.token_urlsafe(50))"
#   DEBUG=false
#   ALLOWED_HOSTS=localhost,127.0.0.1,<server LAN hostname or IP>
#   DISTRICT_NAME="Your District Name"
#   POSTGRES_PASSWORD — set a real one (and mirror it in docker-compose.yml or your DB)
docker compose up -d
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 0.0.0.0:8800   # dev; see §9 for production serving
```

First ingestion will download the embedding model (~90 MB) from Hugging Face once;
after that the box can run fully offline.

## 4. Roles and users

_TODO: filled in with the accounts feature — creating roles, assigning users, what each
role can see, demo seed users._

## 5. Loading documents

_TODO: filled in with the ingestion feature — `manage.py ingest`, admin upload, supported
formats, tier tags, last-updated dates, role scoping per document, re-ingesting updates._

## 6. The audit log

_TODO: filled in with the audit feature — where it lives, how to filter, CSV export for
board review, retention guidance._

## 7. Google Workspace SSO (optional)

_TODO: filled in with the SSO scaffold — creating the OAuth client in the Google admin
console, setting GOOGLE_SSO_ENABLED, role assignment for SSO users._

## 8. Swapping the answer engine (mock → local LLM)

_TODO: filled in at the LLM integration step — running llama.cpp server, choosing a
model, changing `LLM_BACKEND`, verifying citations still ground every answer._

## 9. Production serving

_TODO: gunicorn + reverse proxy + static files; systemd units; where the media
(uploaded documents) directory lives; backup of Postgres volume and media._

## 10. Verifying the security invariants

```bash
uv run pytest
```

The suite includes tests that fail if any code path lets a role retrieve a chunk outside
its permissions — including a document that contains adversarial "reveal everything"
instructions. Run it after every upgrade and before every corpus expansion.

## 11. Troubleshooting

| Symptom | Check |
|---|---|
| `connection refused` on startup | `docker compose ps` — is the `db` container healthy? Port 54320 free? |
| Ingestion slow | Embeddings are CPU-bound; expect ~1–2 s per page-sized chunk batch on a modest CPU. |
| Answers always "I don't have that" | Is the corpus ingested (`Documents` in admin show status Ready)? Is `RETRIEVAL_MAX_DISTANCE` too strict? |
