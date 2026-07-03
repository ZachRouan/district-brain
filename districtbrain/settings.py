"""
Django settings for District Brain.

All deployment-specific values come from environment variables (or a .env file
in the project root). See .env.example for the full list and docs/runbook.md
for what to change in production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.environ.get("SECRET_KEY", "insecure-dev-only-key-set-SECRET_KEY-in-env")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

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

# Retrieval tuning. MAX_DISTANCE is cosine distance (0 = identical); anything
# farther than the cutoff is treated as "no relevant sources" and the assistant
# says so instead of guessing.
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "6"))
RETRIEVAL_MAX_DISTANCE = float(os.environ.get("RETRIEVAL_MAX_DISTANCE", "0.60"))

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
