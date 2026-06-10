"""
FaceGuard — Development Settings
"""
from .base import *  # noqa

DEBUG = True

# SQLite fallback for dev (comment out for PostgreSQL)
# DATABASES["default"]["ENGINE"] = "django.db.backends.sqlite3"
# DATABASES["default"]["NAME"] = BASE_DIR / "db.sqlite3"

# Allow all origins in dev
CORS_ALLOW_ALL_ORIGINS = True

# Show emails in console
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable throttling in dev
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
