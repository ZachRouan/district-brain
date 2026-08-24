import socket

from django.conf import settings


def district(request):
    """District identity shown in the app shell on every page."""
    return {
        "district_name": settings.DISTRICT_NAME,
        "server_label": socket.gethostname().upper(),
        "google_sso_enabled": settings.GOOGLE_SSO_ENABLED,
        "ask_max_chars": settings.ASK_MAX_QUESTION_CHARS,
    }
