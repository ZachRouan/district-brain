"""Report — and optionally repair — documents whose embeddings don't match the
active embedder.

    manage.py check_embeddings          # report mismatches, exit non-zero if any
    manage.py check_embeddings --fix    # re-ingest the mismatches with the active embedder

Vectors produced by two different embedding models (or dimensions) are not
comparable, so a silent EMBEDDING_BACKEND/EMBEDDING_MODEL change would corrupt
retrieval. Those documents are excluded from search until re-ingested; this
command is how an operator finds and fixes them.
"""

from django.core.management.base import BaseCommand

from corpus.embeddings import get_embedder
from corpus.ingest import ingest_document
from corpus.models import Document


class Command(BaseCommand):
    help = "Report documents whose embeddings don't match the active embedder; --fix re-ingests them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Re-ingest each mismatched (and unknown-provenance) document with the active embedder.",
        )

    def handle(self, *args, **options):
        embedder = get_embedder()
        identity = (embedder.backend, embedder.model_name, embedder.dimensions)
        self.stdout.write(f"Active embedder: backend={identity[0]!r} model={identity[1]!r} dim={identity[2]}")

        ingested = [d for d in Document.objects.all() if d.chunks.exists()]
        mismatched = [
            d for d in ingested if d.has_embedding_provenance() and d.embedding_identity() != identity
        ]
        unknown = [d for d in ingested if not d.has_embedding_provenance()]

        if not mismatched and not unknown:
            self.stdout.write(
                self.style.SUCCESS(f"All {len(ingested)} ingested document(s) match the active embedder.")
            )
            return

        for d in mismatched:
            b, m, dim = d.embedding_identity()
            self.stdout.write(
                self.style.WARNING(
                    f"  STALE     {d.title!r} — embedded with {b!r}/{m!r}/{dim} (excluded from search)"
                )
            )
        for d in unknown:
            self.stdout.write(
                self.style.WARNING(
                    f"  UNKNOWN   {d.title!r} — no provenance recorded (legacy; re-ingest to confirm)"
                )
            )

        if not options["fix"]:
            total = len(mismatched) + len(unknown)
            self.stderr.write(
                self.style.ERROR(
                    f"\n{total} document(s) need re-ingesting. Re-run with --fix to repair them."
                )
            )
            return

        self.stdout.write("\nRe-ingesting with the active embedder…")
        for d in mismatched + unknown:
            if not d.source_file:
                self.stdout.write(
                    self.style.ERROR(
                        f"  SKIPPED   {d.title!r} — no source file on record; re-upload it manually."
                    )
                )
                continue
            result = ingest_document(d, force=True)
            style = self.style.SUCCESS if result.outcome != "error" else self.style.ERROR
            detail = f"{result.chunk_count} chunks" if result.outcome != "error" else result.message
            self.stdout.write(style(f"  {result.outcome:>9}  {d.title!r} ({detail})"))
