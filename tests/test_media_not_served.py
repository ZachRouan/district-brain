"""MEDIA_ROOT must never be served directly by the app.

Original source files under MEDIA_ROOT hold the full text of role-scoped
documents. A public /media/ location — the default in most nginx/Caddy Django
guides — would let anyone fetch any file by URL, bypassing retrieval scoping.
Downloads must go only through the authenticated, per-user-scoped
chat:document_download view.

The finding asks specifically that django.views.static.serve is not wired to
MEDIA_ROOT "outside DEBUG". We hold the stronger invariant: it is never wired to
MEDIA_ROOT at all, in any DEBUG state, so dev habits can't leak a public /media/
block into production and dev stays identical to prod. That strictly implies the
outside-DEBUG requirement.
"""

import pytest
from django.urls import Resolver404, resolve
from django.views.static import serve

from districtbrain.urls import urlpatterns


def _all_patterns(patterns):
    for entry in patterns:
        if hasattr(entry, "url_patterns"):  # an include()/resolver
            yield from _all_patterns(entry.url_patterns)
        else:
            yield entry


def _is_static_serve(callback):
    return callback is serve or getattr(callback, "__wrapped__", None) is serve


def test_no_url_pattern_serves_media_root(settings):
    offenders = []
    for pattern in _all_patterns(urlpatterns):
        callback = getattr(pattern, "callback", None)
        if callback is not None and _is_static_serve(callback):
            document_root = (pattern.default_args or {}).get("document_root")
            if document_root is not None and str(document_root) == str(settings.MEDIA_ROOT):
                offenders.append(pattern)
    assert not offenders, (
        "MEDIA_ROOT must never be served via django.views.static.serve — it would "
        "bypass retrieval scoping. Use chat:document_download instead."
    )


def test_a_media_url_does_not_resolve(settings):
    """Concretely: no route claims /media/..., so an original file cannot be
    fetched by guessing its URL."""
    with pytest.raises(Resolver404):
        resolve(f"/{settings.MEDIA_URL.strip('/')}/corpus/2026/policy.pdf")
