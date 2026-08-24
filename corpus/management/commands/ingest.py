"""Ingest documents from the command line.

    manage.py ingest <file-or-directory>... --roles teacher,staff
        [--title "Board policy JICJ"] [--last-updated 2026-05-01] [--force]

Directories are walked recursively; unsupported file types are skipped with a
note. Re-running on the same path updates the existing document instead of
creating a duplicate.
"""

from datetime import date, datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role
from corpus.extractors import SUPPORTED_EXTENSIONS
from corpus.ingest import ingest_document
from corpus.models import Document


def prettify(stem: str) -> str:
    """ "board-policy-JICJ" -> "Board policy JICJ": capitalise the first word only,
    so acronyms and policy codes in the filename survive."""
    words = stem.replace("-", " ").replace("_", " ").split()
    if not words:
        return stem
    words[0] = words[0][0].upper() + words[0][1:]
    return " ".join(words)


class Command(BaseCommand):
    help = "Ingest documents into the corpus, scoped to the given roles."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Files or directories to ingest.")
        parser.add_argument(
            "--roles",
            required=True,
            help="Comma-separated role slugs allowed to retrieve these documents (explicit on purpose).",
        )
        parser.add_argument("--title", help="Document title (single file only; defaults to the filename).")
        parser.add_argument(
            "--last-updated", help="Content revision date, YYYY-MM-DD (defaults to file mtime)."
        )
        parser.add_argument("--force", action="store_true", help="Re-chunk and re-embed even if unchanged.")

    def handle(self, *args, **options):
        role_slugs = [s.strip() for s in options["roles"].split(",") if s.strip()]
        roles = list(Role.objects.filter(slug__in=role_slugs))
        missing = set(role_slugs) - {r.slug for r in roles}
        if missing:
            available = ", ".join(Role.objects.values_list("slug", flat=True)) or "(none defined yet)"
            raise CommandError(f"Unknown role(s): {', '.join(sorted(missing))}. Available roles: {available}")

        files = self._collect_files(options["paths"])
        if options["title"] and len(files) > 1:
            raise CommandError("--title only makes sense for a single file.")

        last_updated = None
        if options["last_updated"]:
            last_updated = datetime.strptime(options["last_updated"], "%Y-%m-%d").date()

        for path in files:
            result = self._ingest_file(path, roles, options["title"], last_updated, options["force"])
            style = self.style.SUCCESS if result.outcome != "error" else self.style.ERROR
            detail = f"{result.chunk_count} chunks" if result.outcome != "error" else result.message
            self.stdout.write(style(f"{result.outcome:>9}  {path}  ({detail})"))

    def _collect_files(self, paths):
        files = []
        for raw in paths:
            path = Path(raw).resolve()
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files.append(child)
                    elif child.is_file():
                        self.stdout.write(self.style.WARNING(f"  skipped (unsupported type): {child}"))
            elif path.is_file():
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
                    raise CommandError(f"Unsupported file type: {path.suffix}. Supported: {supported}")
                files.append(path)
            else:
                raise CommandError(f"No such file or directory: {raw}")
        if not files:
            raise CommandError("Nothing to ingest.")
        return files

    def _ingest_file(self, path, roles, title, last_updated, force):
        document = Document.objects.filter(source_name=str(path)).first()
        if document is None:
            document = Document(source_name=str(path))
        document.title = title or document.title or prettify(path.stem)
        document.last_updated = last_updated or date.fromtimestamp(path.stat().st_mtime)
        if document.source_file:
            document.source_file.delete(save=False)
        document.source_file.save(path.name, ContentFile(path.read_bytes()), save=True)
        document.allowed_roles.set(roles)
        return ingest_document(document, force=force)
