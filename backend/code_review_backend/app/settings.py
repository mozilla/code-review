# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Django settings for backend project.

Generated by 'django-admin startproject' using Django 2.2.6.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.2/ref/settings/
"""

import logging
import os

import environ
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from code_review_backend.app import taskcluster

logger = logging.getLogger(__name__)

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BASE_DIR)

# Load current Version
with open(os.path.join(ROOT_DIR, "VERSION")) as f:
    VERSION = f.read().strip()


# Initialize django-environ variables
env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "t!+s!@x5p!85x19q83jufr#95_z0fv7$!u5z*c&gi!%hr3^w+s"),
    # https://django-environ.readthedocs.io/en/latest/types.html#environ-env-db-url
    DATABASE_URL=(str, f"sqlite:////{ROOT_DIR}/db.sqlite3"),
    ALLOWED_HOSTS=(list[str], ["*"]),
    CSRF_TRUSTED_ORIGINS=(
        list[str],
        ["http://localhost:8000", "http://localhost:8010"],
    ),
    CORS_ALLOWED_ORIGINS=(
        list[str],
        ["http://localhost:8000", "http://localhost:8010"],
    ),
    DYNO=(str, ""),
)

# Set backend user agent
BACKEND_USER_AGENT = f"code-review-backend/{VERSION}"

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# Only use DEBUG mode for local development
# When running on Heroku, we disable that mode (see end of file & DYNO mode)
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "dockerflow.django",
    "code_review_backend.issues",
    "drf_yasg",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dockerflow.django.middleware.DockerflowMiddleware",
]

ROOT_URLCONF = "code_review_backend.app.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "code_review_backend.app.wsgi.application"


DATABASES = {"default": env.db()}

if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    logger.warning("Running application with SQLite backend. Data may be lost.")

# Password validation
# https://docs.djangoproject.com/en/2.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# API configuration
REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly"
    ],
    # Setup pagination
    "PAGE_SIZE": 50,
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
}

# Internal Ips where django debug toolbar is enabled
INTERNAL_IPS = ["127.0.0.1"]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = "/static/"

# Static files are set in a dedicated path in Docker image
if DEBUG is False:
    STATIC_ROOT = "/static"

    # Enable GZip and cache, and build a manifest during collectstatic
    STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# Setup CSRF trusted origins explicitly as it's needed from Django 4
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# Configure CORS origins from env variable
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

# Internal logging setup
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "dockerflow.logging.JsonLogFormatter",
            "logger_name": "code_review_backend",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "json": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "DEBUG",
        },
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "code_review_backend": {"handlers": ["console"], "level": "INFO"},
        "request.summary": {
            "handlers": ["json"],
            "level": "DEBUG",
        },
    },
}

# Use production Phabricator instance by default
PHABRICATOR_HOST = "https://phabricator.services.mozilla.com"

# Limit the automatic creation of reositories to allowed hosts
ALLOWED_REPOSITORY_HOSTS = ["hg.mozilla.org"]

DYNO = env("DYNO")
# Heroku settings override to run the web app through dyno
if DYNO:
    logger.info("Setting up Heroku environment")

    # Insert Whitenoise Middleware after the security and cors ones
    MIDDLEWARE.insert(2, "whitenoise.middleware.WhiteNoiseMiddleware")

    # Cors closed on heroku
    CORS_ORIGIN_ALLOW_ALL = False

    # Use SSL on Heroku
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Load taskcluster secrets on Heroku
    taskcluster_secret = os.getenv("TASKCLUSTER_SECRET")
    if taskcluster_secret:
        taskcluster.auth()
        taskcluster.load_secrets(taskcluster_secret, prefixes=["common", "backend"])

        # Setup Sentry
        if "SENTRY_DSN" in taskcluster.secrets:
            sentry_sdk.init(
                taskcluster.secrets["SENTRY_DSN"],
                integrations=[DjangoIntegration()],
                environment=taskcluster.secrets.get("APP_CHANNEL"),
                release=VERSION,
            )
            logger.info("Enabled Sentry error reporting")

        # Setup Cors allowed domains
        CORS_ALLOWED_ORIGINS = taskcluster.secrets.get("cors-domains", [])

        # Setup CSRF trusted origins
        CSRF_TRUSTED_ORIGINS = taskcluster.secrets.get("csrf-trusted-origins", [])

        # Override Phabricator instance
        if "PHABRICATOR" in taskcluster.secrets:
            PHABRICATOR_HOST = taskcluster.secrets["PHABRICATOR"]["url"]

    else:
        logger.info("Skipping taskcluster configuration")

# Activate django debug toolbar on debug only
if DEBUG:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
    try:
        import django_extensions  # noqa

        INSTALLED_APPS.append("django_extensions")
    except ImportError:
        pass
