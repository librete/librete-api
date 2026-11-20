"""Settings used by the test suite (see `pyproject.toml`)."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ACCOUNT_EMAIL_VERIFICATION", "mandatory")

from .settings import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
LOGGING = {"version": 1, "disable_existing_loggers": False}
