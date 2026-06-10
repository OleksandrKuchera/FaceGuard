"""
apps/reports/models.py — Report model
"""
from django.conf import settings
from django.db import models


class Report(models.Model):
    REPORT_TYPES = [
        ("attendance", "Відвідуваність"),
        ("unknown_persons", "Невідомі особи"),
        ("security_audit", "Аудит безпеки"),
        ("daily_summary", "Денний підсумок"),
        ("custom", "Власний"),
    ]
    FORMAT_CHOICES = [
        ("pdf", "PDF"),
        ("csv", "CSV"),
        ("xlsx", "Excel"),
    ]
    STATUS_CHOICES = [
        ("pending", "Очікує"),
        ("generating", "Генерується"),
        ("ready", "Готово"),
        ("failed", "Помилка"),
    ]

    name = models.CharField(max_length=300, verbose_name="Назва")
    report_type = models.CharField(max_length=30, choices=REPORT_TYPES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default="pdf")

    # Параметри фільтрації (зберігаємо для повторної генерації)
    params_json = models.JSONField(default=dict)

    # Файл результату
    file = models.FileField(upload_to="reports/%Y/%m/", null=True, blank=True)

    # Статус
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Звіт"
        verbose_name_plural = "Звіти"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} [{self.status}]"

    @property
    def download_url(self):
        if self.file:
            return self.file.url
        return None
