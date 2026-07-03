import socket

from django.conf import settings


def district(request):
    """District identity shown in the app shell on every page."""
    return {
        "district_name": settings.DISTRICT_NAME,
        "server_label": socket.gethostname().upper(),
    }
