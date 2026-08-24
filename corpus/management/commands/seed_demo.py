"""Seed a fully synthetic demo: roles, one user per role, and the sample
corpus — so the system is queryable before any real document is loaded.

Idempotent: safe to re-run; existing users and unchanged documents are left
alone. Everything created here is fictional (Maple Ridge USD).
"""

from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Role
from corpus.ingest import ingest_document
from corpus.models import Document

SAMPLE_DIR = Path(settings.BASE_DIR) / "sample_corpus"

DEMO_PASSWORD = "brain-demo-2026"

ROLES = [
    ("admin", "Administrator", "Building and district administration."),
    ("teacher", "Teacher", "Classroom teaching staff."),
    ("staff", "Staff", "Office, facilities, food service, and support staff."),
]

USERS = [
    # username, first, last, role slug, is_staff (Django admin/console access)
    ("demo_admin", "Dana", "Whitfield", "admin", True),
    ("demo_teacher", "Rosa", "Alvarez", "teacher", False),
    ("demo_staff", "Miguel", "Garza", "staff", False),
]

# filename → (title, last_updated, role slugs)
CORPUS = {
    "board-policy-5136-personal-devices.md": (
        "Board Policy 5136 — Personal Electronic Devices",
        date(2026, 3, 10),
        ["admin", "teacher", "staff"],
    ),
    "board-policy-9150-visitors.md": (
        "Board Policy 9150 — Visitors to the Schools",
        date(2024, 11, 11),
        ["admin", "teacher", "staff"],
    ),
    "staff-handbook-2026-27.md": (
        "Staff Handbook 2026-27 (Excerpts)",
        date(2026, 8, 1),
        ["admin", "teacher", "staff"],
    ),
    "bell-schedule-2026-27.md": (
        "Bell Schedules 2026-27",
        date(2026, 8, 19),
        ["admin", "teacher", "staff"],
    ),
    "board-minutes-2026-05-12.md": (
        "Board Minutes — May 12, 2026",
        date(2026, 5, 12),
        ["admin", "teacher", "staff"],
    ),
    "facilities-use-schedule-fall-2026.md": (
        "Facilities Use & Setup Schedule — Fall 2026",
        date(2026, 6, 20),
        ["admin", "staff"],
    ),
    "inclement-weather-procedures.md": (
        "Inclement Weather & Calamity Day Procedures",
        date(2025, 11, 3),
        ["admin", "teacher", "staff"],
    ),
    "admin-incident-response-procedures.md": (
        "Administrative Procedures — Building Incident Response",
        date(2026, 4, 2),
        ["admin"],  # deliberately admin-only: the scoping demo
    ),
}


class Command(BaseCommand):
    help = "Create demo roles, demo users, and ingest the synthetic sample corpus."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even with DEBUG off. The demo password is public; never do this where staff sign in.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "Refusing to seed demo users with DEBUG off: demo_admin is a superuser whose password "
                "is published in the repository. This looks like a production database. Pass --force "
                "only for an evaluation box, and delete the demo users before real staff use it."
            )
        if not SAMPLE_DIR.is_dir():
            raise CommandError(f"sample_corpus/ not found at {SAMPLE_DIR}")

        roles = {}
        for slug, name, description in ROLES:
            roles[slug], _ = Role.objects.get_or_create(
                slug=slug, defaults={"name": name, "description": description}
            )

        User = get_user_model()
        for username, first, last, role_slug, is_staff in USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "role": roles[role_slug],
                    "is_staff": is_staff,
                    "is_superuser": is_staff,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()

        for filename, (title, last_updated, role_slugs) in CORPUS.items():
            path = SAMPLE_DIR / filename
            if not path.is_file():
                raise CommandError(f"Missing sample document: {path}")
            document = Document.objects.filter(source_name=f"sample_corpus/{filename}").first()
            if document is None:
                document = Document(source_name=f"sample_corpus/{filename}")
            document.title = title
            document.last_updated = last_updated
            if document.source_file:
                document.source_file.delete(save=False)
            document.source_file.save(filename, ContentFile(path.read_bytes()), save=True)
            document.allowed_roles.set([roles[slug] for slug in role_slugs])
            result = ingest_document(document)
            if result.outcome == "error":
                raise CommandError(f"{filename}: {result.message}")
            self.stdout.write(f"  {result.outcome:>9}  {title} ({result.chunk_count} chunks)")

        self.stdout.write(self.style.SUCCESS("\nDemo ready. Sign in at / with:"))
        for username, _first, _last, role_slug, is_staff in USERS:
            note = "  (also Django admin console at /admin/)" if is_staff else ""
            self.stdout.write(f"  {username} / {DEMO_PASSWORD} — {role_slug}{note}")
        self.stdout.write("\nAll demo content is synthetic (fictional Maple Ridge USD).")
