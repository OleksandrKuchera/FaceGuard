"""
apps/core/models.py — Custom User + TimestampedModel + SystemSettings
"""
from django.contrib.auth.models import AbstractUser
from django.db import models


class TimestampedModel(models.Model):
    """Abstract base class for all models — adds created_at / updated_at."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SystemSettings(models.Model):
    """Key-value store for system-wide configuration persisted to DB."""

    key = models.CharField(max_length=50, primary_key=True)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    # Shipped defaults — used when a key has no DB row yet
    DEFAULTS: dict = {
        "general": {
            "institution_name": "FaceGuard Security",
            "timezone": "Europe/Kyiv",
            "language": "uk",
        },
        "ml": {
            "global_threshold": "0.55",
            "model_version": "hog",
            "liveness_enabled": True,
            "min_face_size": "20",
        },
        "notify": {
            "telegram_enabled": False,
            "telegram_webhook": "",
            "email_enabled": False,
            "email_address": "",
            "alert_on_unknown": True,
            "alert_on_spoofing": True,
        },
        "cooldown": {
            "recognized_cooldown": "30",
            "unknown_cooldown": "15",
            "spoofing_cooldown": "5",
            "multi_face_cooldown": "20",
        },
    }

    class Meta:
        verbose_name = "Системне налаштування"
        verbose_name_plural = "Системні налаштування"

    def __str__(self):
        return self.key


class User(AbstractUser):
    """Custom user model with RBAC role."""

    ROLE_CHOICES = [
        ("superadmin", "Super Admin"),
        ("admin", "Admin"),
        ("guard", "Guard"),
        ("readonly", "Read Only"),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="readonly",
    )

    class Meta:
        verbose_name = "Користувач"
        verbose_name_plural = "Користувачі"

    def __str__(self):
        return f"{self.get_full_name() or self.username} [{self.role}]"
