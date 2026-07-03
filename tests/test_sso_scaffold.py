"""Google Workspace SSO is scaffolded behind GOOGLE_SSO_ENABLED and must not
be required for anything in the Tier 1 slice."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.urls import reverse

BASE_DIR = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.django_db


def test_login_page_has_no_google_button_by_default(client):
    html = client.get(reverse("login")).content.decode()
    assert "Google" not in html


def test_login_page_offers_google_when_enabled(client, settings):
    settings.GOOGLE_SSO_ENABLED = True
    html = client.get(reverse("login")).content.decode()
    assert "Continue with district Google account" in html
    assert "/accounts/google/login/" in html


def test_sso_enabled_settings_are_valid():
    """`manage.py check` in a subprocess with the flag on proves the allauth
    wiring (apps, middleware, urls) actually assembles."""
    env = {
        **os.environ,
        "GOOGLE_SSO_ENABLED": "true",
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-secret",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check"],
        env=env,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
