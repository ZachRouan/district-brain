from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    """A district role. Documents are scoped to roles; users hold exactly one.

    Seeded with admin/teacher/staff; extensible to student/family in later tiers
    without schema changes.
    """

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    # Null role = least privilege: the user can sign in but retrieval returns
    # nothing until an admin assigns a role. PROTECT so deleting a role can't
    # silently strip scoping from its users.
    role = models.ForeignKey(
        Role,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="users",
        help_text="Determines which documents this user's questions may search.",
    )

    def __str__(self):
        return self.get_full_name() or self.username
