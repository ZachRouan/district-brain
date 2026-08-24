"""The operator console: Django admin, restricted to superusers.

The admin exposes every document's chunks, the full audit log, and user/role
assignment — none of it role-scoped. `is_staff` alone is therefore not enough
to open it; only superusers (the coordinator who loads the corpus) can. The
chat UI applies the same rule to its Console link.
"""

from django.contrib.admin import AdminSite


class ConsoleAdminSite(AdminSite):
    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser
