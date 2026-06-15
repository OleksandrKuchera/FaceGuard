"""
apps/security/models.py — SpoofingAttempt, AuditLog
"""
from django.conf import settings
from django.db import models

from apps.cameras.models import Camera


class SpoofingAttempt(models.Model):
    ATTACK_TYPES = [
        ("photo", "Фото-атака"),
        ("video", "Відео-атака"),
        ("unknown", "Невідомий тип"),
    ]

    camera = models.ForeignKey(Camera, on_delete=models.PROTECT, related_name="spoofing_attempts")
    event = models.OneToOneField(
        "events.RecognitionEvent", on_delete=models.CASCADE, related_name="spoofing_detail"
    )
    attack_type = models.CharField(max_length=20, choices=ATTACK_TYPES, default="unknown")

    ear_value = models.FloatField(null=True, blank=True)
    texture_score = models.FloatField(null=True, blank=True)
    depth_score = models.FloatField(null=True, blank=True)

    frame_evidence = models.ImageField(upload_to="security/spoofing/", null=True, blank=True)

    final_status = models.CharField(max_length=50, null=True, blank=True)
    final_reason_code = models.CharField(max_length=100, null=True, blank=True)
    final_module_name = models.CharField(max_length=100, null=True, blank=True)

    detected_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Спроба Spoofing"
        verbose_name_plural = "Спроби Spoofing"
        ordering = ["-detected_at"]

    def __str__(self):
        return f"Spoofing [{self.attack_type}] @ {self.camera.name} {self.detected_at:%Y-%m-%d %H:%M}"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=100, blank=True)
    details_json = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Аудит лог"
        verbose_name_plural = "Аудит логи"
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["user", "timestamp"])]

    def __str__(self):
        user_str = self.user.username if self.user else "anonymous"
        return f"[{user_str}] {self.action} at {self.timestamp:%Y-%m-%d %H:%M}"
