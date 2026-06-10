"""
apps/cameras/models.py — Camera, CameraZone
"""
from django.db import models

from apps.core.models import TimestampedModel


class Camera(TimestampedModel):
    STATUS_CHOICES = [
        ("active", "Активна"),
        ("offline", "Офлайн"),
        ("maintenance", "Обслуговування"),
    ]

    # Ідентифікація
    name = models.CharField(max_length=200, verbose_name="Назва")
    location = models.CharField(max_length=500, verbose_name="Розташування")
    camera_code = models.CharField(max_length=50, unique=True, verbose_name="Код камери")

    # Підключення
    stream_url = models.CharField(
        max_length=500,
        verbose_name="URL потоку (rtsp:// або 0,1,2 для USB)",
    )
    is_local = models.BooleanField(default=True, verbose_name="Локальна (USB)")

    # Статус
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active", verbose_name="Статус"
    )
    last_ping = models.DateTimeField(null=True, blank=True)

    # ML налаштування
    recognition_enabled = models.BooleanField(default=True, verbose_name="Розпізнавання ввімкнено")
    detection_confidence = models.FloatField(
        default=0.55, verbose_name="Поріг впевненості (0.0-1.0)"
    )
    frame_skip = models.IntegerField(
        default=2, verbose_name="Обробляти кожен N-й кадр"
    )
    resolution_scale = models.FloatField(
        default=0.25, verbose_name="Масштаб для ML (0.25 = чверть)"
    )

    # Зони доступу
    access_zone = models.CharField(max_length=100, blank=True, verbose_name="Зона доступу")
    requires_mfa = models.BooleanField(default=False, verbose_name="Потребує MFA")

    class Meta:
        verbose_name = "Камера"
        verbose_name_plural = "Камери"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} [{self.camera_code}] — {self.status}"


class CameraZone(models.Model):
    """Defines a rectangular region of interest within a camera frame."""

    camera = models.ForeignKey(Camera, related_name="zones", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    # Relative coordinates 0.0–1.0
    x1 = models.FloatField()
    y1 = models.FloatField()
    x2 = models.FloatField()
    y2 = models.FloatField()

    trigger_alert = models.BooleanField(
        default=False, verbose_name="Тригер сповіщення при вході в зону"
    )

    class Meta:
        verbose_name = "Зона камери"
        verbose_name_plural = "Зони камер"

    def __str__(self):
        return f"Zone '{self.name}' on {self.camera.name}"
