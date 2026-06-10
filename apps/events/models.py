"""
apps/events/models.py — RecognitionEvent, DailyStats
"""
from django.conf import settings
from django.db import models

from apps.cameras.models import Camera
from apps.persons.models import Person


class RecognitionEvent(models.Model):
    EVENT_TYPES = [
        ("recognized", "Розпізнано"),
        ("unknown", "Невідома особа"),
        ("spoofing", "Спроба підробки"),
        ("multi_face", "Декілька облич"),
        ("low_quality", "Низька якість кадру"),
    ]

    # Прив'язки
    camera = models.ForeignKey(Camera, on_delete=models.PROTECT, related_name="events")
    person = models.ForeignKey(
        Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )

    # Тип події
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)

    # ML метрики
    confidence = models.FloatField(null=True, blank=True)
    distance = models.FloatField(null=True, blank=True)
    liveness_score = models.FloatField(null=True, blank=True)

    # Знімки
    frame_snapshot = models.ImageField(
        upload_to="events/%Y/%m/%d/", null=True, blank=True
    )
    face_crop = models.ImageField(
        upload_to="events/faces/%Y/%m/", null=True, blank=True
    )

    # Координати обличчя в кадрі
    face_bbox_json = models.JSONField(null=True, blank=True)

    # Час
    timestamp = models.DateTimeField(db_index=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    # Безпека
    is_alert = models.BooleanField(default=False)
    alert_sent = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_events",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Подія розпізнавання"
        verbose_name_plural = "Події розпізнавання"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["timestamp"]),
            models.Index(fields=["camera", "timestamp"]),
            models.Index(fields=["person", "timestamp"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["is_alert", "alert_sent"]),
        ]

    def __str__(self):
        person_str = str(self.person) if self.person else "Unknown"
        return f"[{self.event_type}] {person_str} @ {self.camera.name} {self.timestamp:%Y-%m-%d %H:%M}"


class DailyStats(models.Model):
    """Pre-aggregated daily statistics for fast dashboard queries."""

    date = models.DateField(unique=True)
    total_events = models.IntegerField(default=0)
    recognized = models.IntegerField(default=0)
    unknown = models.IntegerField(default=0)
    spoofing_attempts = models.IntegerField(default=0)
    unique_persons = models.IntegerField(default=0)

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Денна статистика"
        verbose_name_plural = "Денна статистика"
        ordering = ["-date"]

    def __str__(self):
        return f"Stats {self.date}: total={self.total_events}"
