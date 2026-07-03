from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("chat.urls")),
]

# SECURITY: MEDIA_ROOT is deliberately NEVER served here — not via
# django.views.static.serve, not even under DEBUG. Original source files hold the
# full text of role-scoped documents; a public /media/ URL (the default in most
# nginx/Caddy Django guides) would let anyone fetch any file, bypassing retrieval
# scoping — exactly what the product must never allow. Downloads go through the
# authenticated, per-user-scoped chat:document_download view instead. Serving
# media even in dev would let dev habits leak a public /media/ block into prod,
# so we forbid it everywhere and keep dev identical to production. The runbook's
# reverse-proxy section spells out the matching "do NOT serve /media/" rule, and
# tests/test_media_not_served.py fails if this ever regresses.

if settings.GOOGLE_SSO_ENABLED:
    urlpatterns.insert(1, path("accounts/", include("allauth.urls")))

admin.site.site_header = f"District Brain — {settings.DISTRICT_NAME}"
admin.site.site_title = "District Brain"
admin.site.index_title = "Console"
