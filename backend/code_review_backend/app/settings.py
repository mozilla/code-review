# -*- coding: utf-8 -*-
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

import dj_database_url
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

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "t!+s!@x5p!85x19q83jufr#95_z0fv7$!u5z*c&gi!%hr3^w+r"

# Only use DEBUG mode for local development
# When running on Heroku, we disable that mode (see end of file & DYNO mode)
DEBUG = True

ALLOWED_HOSTS = []


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
    "code_review_backend.issues",
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


# Database
# https://docs.djangoproject.com/en/2.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(ROOT_DIR, "db.sqlite3"),
    }
}


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


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.2/howto/static-files/

STATIC_URL = "/static/"

# Static files are set in a dedicated path in Docker image
if "DJANGO_DOCKER" in os.environ:
    STATIC_ROOT = "/static"

    # Enable GZip and cache, and build a manifest during collectstatic
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# Internal logging setup
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO"},
        "code_review_backend": {"handlers": ["console"], "level": "INFO"},
    },
}

# Cors open by default in dev
CORS_ORIGIN_ALLOW_ALL = True

# Heroku settings override to run the web app in production mode
if "DYNO" in os.environ:
    logger.info("Setting up Heroku environment")
    ALLOWED_HOSTS = ["*"]
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # Database setup
    if "DATABASE_URL" in os.environ:
        logger.info("Using remote database from $DATABASE_URL")
        DATABASES["default"] = dj_database_url.parse(
            os.environ["DATABASE_URL"], ssl_require=True
        )
    else:
        logger.info("DATABASE_URL not found, will use sqlite. Data may be lost.")

    # Insert Whitenoise Middleware after the security and cors ones
    MIDDLEWARE.insert(2, "whitenoise.middleware.WhiteNoiseMiddleware")

    # Use Secret key from env
    SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)

    # Cors closed on heroku
    CORS_ORIGIN_ALLOW_ALL = False

    # Load taskcluster secrets on Heroku
    taskcluster_client_id = os.getenv("TASKCLUSTER_CLIENT_ID")
    taskcluster_access_token = os.getenv("TASKCLUSTER_ACCESS_TOKEN")
    taskcluster_secret = os.getenv("TASKCLUSTER_SECRET")
    if taskcluster_client_id and taskcluster_access_token and taskcluster_secret:
        taskcluster.auth(taskcluster_client_id, taskcluster_access_token)
        taskcluster.load_secrets(taskcluster_secret, "backend")

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
        CORS_ORIGIN_WHITELIST = taskcluster.secrets.get("cors-domains", [])

    else:
        logger.info("Skipping taskcluster configuration")
