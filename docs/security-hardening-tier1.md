# Tier 1 Security Hardening

Before Tier 1 went into daily use, the codebase went through an adversarial security review
("how does a motivated 14-year-old abuse this?"). This is the record of what it found and how
each finding was closed — one commit per finding, each with a test that fails if the fix
regresses. Nothing in `tests/test_retrieval_scoping.py` was weakened; those tests are
untouched and still pass.

The review shipped three migrations: three embedding-provenance columns on `corpus.Document`,
an `error` column on `audit.AuditLog`, and the tier CheckConstraint (a data migration
backfills provenance for any already-ingested corpus so an upgrade doesn't dark out existing
documents). Two findings have since been revised as the project moved on; each is marked
**Since then** below.

---

## Finding 1 (CRITICAL) — media serving bypassed the access model

**Was:** `Document.source_file` lives under `MEDIA_ROOT`. A public `/media/` block (the
default in most nginx/Caddy Django guides) would make every original file fetchable by URL
with no auth and no role check — bypassing retrieval scoping entirely.

**Now:**
- New `chat:document_download` view at `/documents/<pk>/download/` streams `source_file`
  **only** if the document is in `visible_documents(request.user)`; superusers may fetch
  anything (corpus management). Out-of-scope or nonexistent documents return **404, not 403**,
  so a user can't even learn a document exists. Anonymous requests redirect to login.
- Linked from the chat scope card and every citation panel; the UI never links `/media/`.
- `districtbrain/urls.py` documents that `MEDIA_ROOT` is **never** served directly — not even
  under `DEBUG` (stronger than the requested "outside DEBUG"), so dev habits can't leak a
  public `/media/` block into prod and dev stays identical to prod.
- Runbook: a loud **"NEVER expose /media/"** deployment section with correct nginx and Caddy
  blocks that serve `/static/` only.

**Tests:** `tests/test_document_download.py` (in-scope 200 with byte-exact body; out-of-scope
404; anonymous → login redirect; superuser downloads out-of-scope; missing file 404; unready
doc 404) and `tests/test_media_not_served.py` (no URL pattern wires `django.views.static.serve`
to `MEDIA_ROOT`; a `/media/...` path does not resolve). `tests/test_views.py` gained a case
asserting the scope card renders the download URL and never `/media/`.

**Files:** `chat/views.py`, `chat/urls.py`, `districtbrain/urls.py`, `templates/chat/index.html`,
`static/css/app.css`, `docs/runbook.md`.

## Finding 2 — retrieve() must not trust its callers

**Now:** `retrieve()` hard-clamps its own arguments to caps in settings —
`top_k = min(requested, RETRIEVAL_TOP_K_CAP)` (default cap 20) and
`max_distance = min(requested, RETRIEVAL_MAX_DISTANCE_CAP)` (default cap 1.0, i.e.
cosine-orthogonal — the strictest defensible relevance ceiling). Settings define the
defaults; no caller can exceed the caps.

**Since then:** the clamp was made one-directional on purpose. An *excessive* request is
capped silently (a buggy `top_k=10000` must not crash a user's question), but *nonsensical*
input — `top_k <= 0`, or a negative `max_distance` — is a caller error and raises
`ValueError` instead of being silently corrected to a valid value.

**Tests:** `tests/test_retrieval_clamp.py` — `top_k=10000` returns at most the cap;
lowering the cap overrides the caller; `max_distance=99` is clamped so an on-topic query
returns nothing once the cap is below every match; returned distances never exceed the cap;
`top_k <= 0` and `max_distance < 0` are rejected.

**Files:** `chat/retrieval.py`, `districtbrain/settings.py`.

## Finding 3 — embedding drift corrupted retrieval silently

**Was:** vectors from two embedding models/dimensions aren't comparable; a silent
`EMBEDDING_BACKEND`/`EMBEDDING_MODEL` change would quietly wreck similarity scoring.

**Now:**
- Each `Document` records `embedding_backend`, `embedding_model`, `embedding_dim`, stamped at
  ingest time.
- `retrieve()` searches **only** documents matching the active embedder; mismatched documents
  are excluded and a warning is logged. Documents with no provenance recorded (legacy /
  pre-tracking) are treated as compatible, and a data migration backfills existing corpora so
  an upgrade doesn't dark out already-ingested documents.
- Admin document list shows a loud `⚠ STALE — not searchable` column for mismatches.
- New `manage.py check_embeddings` reports mismatched (and unknown-provenance) documents and
  exits non-zero; `--fix` re-ingests them with the active embedder.

**Tests:** `tests/test_embedding_provenance.py` — ingest stamps the active identity; a
document embedded under a different backend is excluded from retrieval and flagged stale;
legacy no-provenance documents stay searchable; `check_embeddings` reports mismatches;
`check_embeddings --fix` re-ingests and restores searchability. Also verified against a live
database: the migration backfilled every seeded document and `check_embeddings` reported
them all matching.

**Files:** `corpus/models.py`, `corpus/embeddings.py`, `corpus/ingest.py`, `corpus/admin.py`,
`corpus/management/commands/check_embeddings.py`, `chat/retrieval.py`, migration
`corpus/0003_*`.

## Finding 4 — IDOR on POST

**Now:** confirmed the write path already filters
`get_object_or_404(Conversation, pk=..., user=request.user)`, and added the missing proof.

**Test:** `tests/test_views.py::test_posting_to_another_users_conversation_404s_and_writes_nothing`
— POSTing to `chat:ask` with another user's conversation id returns 404 and creates no
message, no audit row, and no new conversation.

## Finding 5 — citation-marker hallucination guard

**Now:** `services.ask()` post-processes every model answer with
`strip_hallucinated_citations(answer, len(retrieved))`, which drops any `[n]` marker where
`n < 1` or `n > retrieved count` (and logs it). Only real sources are numbered `[1..n]`, so a
marker outside that range is a fabricated citation and is removed before the answer is stored
or shown.

**Tests:** `tests/test_chat.py` — the pure function drops out-of-range markers and keeps valid
ones; end-to-end, a fake backend returning `"... [1] ... [7]."` against 2 retrieved chunks has
the `[7]` stripped and `[1]` kept.

**Files:** `chat/services.py`.

## Finding 6 — LlamaCppServerBackend hardening

**Now:**
- Sends `max_tokens` (`settings.LLM_MAX_TOKENS`, default 1024) to bound latency/cost on
  closet-grade hardware and stop runaway generation.
- Catches `requests.ConnectionError`/`Timeout` and raises a typed `LLMBackendUnavailable`
  instead of letting a 500 escape. `ask()` turns it into a friendly *"The answer engine is
  unreachable — tell your administrator"* notice.
- Audits the failure: `refused=True` plus a new `AuditLog.error` note; the retrieved passages
  are kept in the audit for forensics, but no citations are attached to the non-answer. The
  `error` flag also surfaces in the admin list and CSV export.

**Tests:** `tests/test_chat.py` — `max_tokens` is present in the request payload; both
`ConnectionError` and `Timeout` raise `LLMBackendUnavailable`; end-to-end, a down engine
yields the friendly notice, zero citations, and an audited refusal with the error and the
retrieved passage retained.

**Files:** `chat/llm.py`, `chat/services.py`, `audit/services.py`, `audit/models.py`,
`audit/admin.py`, `districtbrain/settings.py`, migration `audit/0002_*`.

## Finding 7 — tier guardrail made physical

**Now:** a database `CheckConstraint(condition=Q(tier=1), name="document_tier_1_only")`
enforces Tier 1 alongside the existing `clean()` validation, so a raw ORM save, bulk import,
or future bug can't slip a Tier 2/3 (student-data-tier) row in behind the form validation.

**Since then:** Tier 2 (curriculum — still no student data) was deliberately enabled. The
constraint was widened by migration `corpus/0004` to `Q(tier__in=[1, 2])` under the name
`document_enabled_tiers_only`; Tier 3 remains physically impossible to store, and the guard
stays in lockstep with `Document.ENABLED_TIERS`.

**Test:** `tests/test_models.py::test_database_refuses_a_direct_tier_three_save` — a direct
`Document.objects.create(tier=3)` raises `IntegrityError` (and Tier 2 saves cleanly).

**Files:** `corpus/models.py`, migration `corpus/0002_*`.

## Finding 8 — documentation debts

- Recorded single-role-per-user (and role-based, not yet relationship-based, scoping) as
  known Tier 1 simplifications and required steps toward relationship-based access in
  Tier 2+ — now carried in the Tier 2 design spec (`docs/design/`, §2.5). Synchronous admin
  ingestion is a known limitation (the management command exists; background jobs only if
  it bites).
- **docs/runbook.md** — large/bulk documents should go through `manage.py ingest` (admin
  upload is synchronous and can time out); retrieval-tuning section now covers the new caps
  and `check_embeddings`.

---

## Design notes

- **`visible_documents()` is unchanged** and remains the single scoping source shared by
  retrieval, the scope card, and the download view. The embedding-provenance filter lives in
  `retrieve()` only: staleness affects *search*, not *permission* — an entitled user can still
  download an original whose embeddings are stale, which is correct.
- **Legacy blank-provenance documents are treated as compatible** by retrieval rather than
  excluded, so an upgrade doesn't dark out an existing corpus. In production every document is
  ingested through `ingest_document`, which stamps provenance, so blank provenance only arises
  for pre-migration rows (backfilled by the data migration) — `check_embeddings` flags any that
  remain unknown.
- **One deliberately loosened field semantic:** `AuditLog.refused` now means "no grounded
  answer was delivered" (thin retrieval **or** engine failure), disambiguated by the new
  `error` column. Help text updated to match.
