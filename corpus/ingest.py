"""Document ingestion: stored file → clean text → chunks → embeddings.

Idempotent by content hash: re-ingesting an unchanged document is a no-op;
changed content atomically replaces the old chunks so retrieval never sees a
half-ingested document.
"""

import hashlib
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .chunking import chunk_text
from .embeddings import get_embedder
from .extractors import extract_text
from .models import Chunk, Document


@dataclass
class IngestResult:
    document: Document
    outcome: str  # "ingested" | "unchanged" | "error"
    chunk_count: int = 0
    message: str = ""


def _fail(document, message):
    document.status = Document.Status.ERROR
    document.error_message = message
    document.save(update_fields=["status", "error_message"])
    return IngestResult(document=document, outcome="error", message=message)


def ingest_document(document, force=False):
    """Extract, chunk, and embed `document.source_file`. Safe to call again
    any time; unchanged content is skipped unless `force`."""
    if not document.source_file:
        return _fail(document, "No file attached to this document.")

    document.status = Document.Status.PROCESSING
    document.save(update_fields=["status"])

    try:
        with document.source_file.open("rb") as f:
            text = extract_text(f, filename=document.source_file.name)
    except Exception as exc:  # extraction failures must surface in admin, not crash
        return _fail(document, f"Could not extract text: {exc}")

    content_hash = hashlib.sha256(text.encode()).hexdigest()
    if not force and content_hash == document.content_hash and document.chunks.exists():
        document.status = Document.Status.READY
        document.error_message = ""
        document.save(update_fields=["status", "error_message"])
        return IngestResult(document=document, outcome="unchanged", chunk_count=document.chunks.count())

    texts = chunk_text(text)
    if not texts:
        return _fail(document, "No extractable text found in the file.")

    embeddings = get_embedder().embed(texts)

    with transaction.atomic():
        document.chunks.all().delete()
        Chunk.objects.bulk_create(
            Chunk(document=document, index=i, text=t, embedding=e)
            for i, (t, e) in enumerate(zip(texts, embeddings))
        )
        document.content_hash = content_hash
        document.status = Document.Status.READY
        document.error_message = ""
        document.ingested_at = timezone.now()
        document.save(update_fields=["content_hash", "status", "error_message", "ingested_at"])

    return IngestResult(document=document, outcome="ingested", chunk_count=len(texts))
