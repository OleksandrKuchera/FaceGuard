"""
FaceGuard — Celery Application
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "faceguard.settings.development")

app = Celery("faceguard")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["workers"])
