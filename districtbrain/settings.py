"""
Django settings for District Brain.

All deployment-specific values come from environment variables (or a .env file
in the project root). See .env.example for the full list and docs/runbook.md
for what to change in production.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


DEBUG = env_bool("DEBUG", False)

# The fallback key is public (it is in this repository), so it is only ever
# acceptable with DEBUG on. A production boot without a real key is refused
# rather than silently issuing forgeable session cookies.
_DEV_SECRET_KEY = "insecure-dev-only-key-set-SECRET_KEY-in-env"
SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
if not DEBUG and SECRET_KEY == _DEV_SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY is not set. Generate one (see .env.example) and put it in .env, "
        "or set DEBUG=true for development."
    )

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]

# Shown in the UI header and used in synthetic fixtures. Set per district.
DISTRICT_NAME = os.environ.get("DISTRICT_NAME", "Maple Ridge USD")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "corpus",
    "chat",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "districtbrain.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "districtbrain.context_processors.district",
            ],
        },
    },
]

WSGI_APPLICATION = "districtbrain.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "districtbrain"),
        "USER": os.environ.get("POSTGRES_USER", "districtbrain"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "districtbrain"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "54320"),
    }
}

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "chat:home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Operational signals (stale embeddings excluded from search, an unreachable
# answer engine, dropped citation markers) are logged at INFO/WARNING by the
# project loggers. They go to stderr, which systemd/gunicorn capture — see
# docs/runbook.md §9.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {name: {"level": "INFO"} for name in ("accounts", "audit", "chat", "corpus")},
}

# ---------------------------------------------------------------------------
# District Brain configuration
# ---------------------------------------------------------------------------

# Embeddings always run locally. "sentence_transformers" downloads the model
# once from Hugging Face, then works fully offline. "hash" is a deterministic
# no-download backend used by the test suite.
EMBEDDING_BACKEND = os.environ.get("EMBEDDING_BACKEND", "sentence_transformers")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = 384

# Dotted path to the LLM backend class. The mock backend needs no model and
# answers deterministically from retrieved sources; swapping to a real local
# model is this one setting.
LLM_BACKEND = os.environ.get("LLM_BACKEND", "chat.llm.MockLLMBackend")
LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8080")
# Upper bound on generated tokens per answer. Bounds latency and cost on a
# closet-grade box and stops a runaway generation; answers are short by design.
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))

# Reasoning models (e.g. Qwen3) emit chain-of-thought that llama.cpp returns in a
# separate `reasoning_content` field — burning generation budget and latency for
# no benefit on grounded extraction, and (if the budget runs out mid-thought)
# leaving the answer `content` empty. District Brain's task is to quote and cite
# provided passages, so thinking is disabled by default. Requires the llama.cpp
# server to run with --jinja (so the chat template honours the kwarg); harmless
# for models that don't reason. Set false if you deliberately want a reasoning
# model to think.
LLM_DISABLE_THINKING = env_bool("LLM_DISABLE_THINKING", True)

# Retrieval tuning. MAX_DISTANCE is cosine distance (0 = identical); anything
# farther than the cutoff is treated as "no relevant sources" and the assistant
# says so instead of guessing.
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "6"))
RETRIEVAL_MAX_DISTANCE = float(os.environ.get("RETRIEVAL_MAX_DISTANCE", "0.60"))

# Hard caps that retrieve() enforces on its own arguments, so no caller — a
# future feature, a tampered request, a bug — can widen a search beyond what a
# grounded, auditable answer should ever draw on. These bound the *ceiling*;
# the defaults above set normal operating behaviour well under them.
#  - TOP_K_CAP: an answer citing more than this many passages is noise, not grounding.
#  - MAX_DISTANCE_CAP: cosine distance 1.0 == orthogonal (zero similarity); nothing
#    past it is ever "relevant", so it is the strictest defensible upper bound.
RETRIEVAL_TOP_K_CAP = int(os.environ.get("RETRIEVAL_TOP_K_CAP", "20"))
RETRIEVAL_MAX_DISTANCE_CAP = float(os.environ.get("RETRIEVAL_MAX_DISTANCE_CAP", "1.0"))

# ---------------------------------------------------------------------------
# Optional Google Workspace SSO (django-allauth), disabled by default.
# Local accounts always work; see docs/runbook.md to enable SSO.
# ---------------------------------------------------------------------------

GOOGLE_SSO_ENABLED = env_bool("GOOGLE_SSO_ENABLED", False)

if GOOGLE_SSO_ENABLED:
    INSTALLED_APPS += [
        "django.contrib.sites",
        "allauth",
        "allauth.account",
        "allauth.socialaccount",
        "allauth.socialaccount.providers.google",
    ]
    MIDDLEWARE.append("allauth.account.middleware.AccountMiddleware")
    SITE_ID = 1
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",
        "allauth.account.auth_backends.AuthenticationBackend",
    ]
    SOCIALACCOUNT_PROVIDERS = {
        "google": {
            "APP": {
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            },
            "SCOPE": ["profile", "email"],
        }
    }
    # New SSO users get no role until an admin assigns one (least privilege).
    SOCIALACCOUNT_AUTO_SIGNUP = True
    ACCOUNT_EMAIL_VERIFICATION = "none"
