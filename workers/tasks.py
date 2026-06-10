"""
workers/tasks.py — Celery Tasks
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def validate_and_encode_photos(self, person_id: int):
    """
    Validate photos (detect face presence) then generate encodings.
    Stores face_location in landmarks_json so train_person_encodings can
    skip redundant face detection — avoids running face_locations twice.
    """
    from django.db import close_old_connections
    close_old_connections()
    try:
        from apps.persons.models import PersonPhoto
        from apps.persons.services import train_person_encodings
        import face_recognition
        from apps.persons.models import Person

        person = Person.objects.get(id=person_id)
        if not person.consent_given or person.deletion_requested or not person.is_active:
            logger.info(
                "Skip validation for person %s: consent=%s deletion_requested=%s active=%s",
                person_id,
                person.consent_given,
                person.deletion_requested,
                person.is_active,
            )
            return {"person_id": person_id, "success": 0, "errors": ["biometric_processing_not_allowed"]}

        photos = PersonPhoto.objects.filter(
            person_id=person_id, face_detected__isnull=True
        )
        for photo in photos:
            try:
                image = face_recognition.load_image_file(photo.image.path)
                locations = face_recognition.face_locations(image, model="hog")
                has_one_face = len(locations) == 1
                photo.face_detected = has_one_face
                photo.is_processed = False
                # Cache the detected location so train step can skip re-detection
                if has_one_face:
                    existing = photo.landmarks_json or {}
                    photo.landmarks_json = {**existing, "face_location": list(locations[0])}
                    photo.save(update_fields=["face_detected", "is_processed", "landmarks_json"])
                else:
                    photo.save(update_fields=["face_detected", "is_processed"])
            except Exception as e:
                logger.warning(f"Photo {photo.id} validation error: {e}")

        return train_person_encodings(person_id)

    except Exception as exc:
        logger.error(f"validate_and_encode_photos failed for person {person_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3)
def train_person_task(self, person_id: int):
    """Re-train encodings for a person (called from API)."""
    from django.db import close_old_connections
    close_old_connections()
    try:
        from apps.persons.services import train_person_encodings
        return train_person_encodings(person_id)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def generate_report(report_id: int):
    """Generate a report file (PDF/CSV/Excel) asynchronously."""
    from django.db import close_old_connections
    close_old_connections()
    from apps.reports.models import Report
    from apps.reports.generators import ReportGeneratorFactory

    report = Report.objects.get(id=report_id)
    report.status = "generating"
    report.save(update_fields=["status"])

    try:
        generator = ReportGeneratorFactory.get(report.report_type)
        file_bytes, filename = generator.generate(report.format, report.params_json)

        from django.core.files.base import ContentFile
        report.file.save(filename, ContentFile(file_bytes), save=False)
        report.status = "ready"
        report.generated_at = timezone.now()
        report.save(update_fields=["file", "status", "generated_at"])
        logger.info(f"Report {report_id} generated: {filename}")

    except Exception as e:
        logger.error(f"Report {report_id} generation failed: {e}")
        report.status = "failed"
        report.error_message = str(e)
        report.save(update_fields=["status", "error_message"])


@shared_task
def compute_daily_stats():
    """Celery beat task: compute daily stats for yesterday (runs at 00:05)."""
    from django.db import close_old_connections
    close_old_connections()
    from apps.events.models import RecognitionEvent, DailyStats

    yesterday = (timezone.now() - timedelta(days=1)).date()

    stats = RecognitionEvent.objects.filter(
        timestamp__date=yesterday
    ).aggregate(
        total=Count("id"),
        recognized=Count("id", filter=Q(event_type="recognized")),
        unknown=Count("id", filter=Q(event_type="unknown")),
        spoofing=Count("id", filter=Q(event_type="spoofing")),
        unique_persons=Count("person", distinct=True),
    )

    DailyStats.objects.update_or_create(
        date=yesterday,
        defaults={
            "total_events": stats["total"] or 0,
            "recognized": stats["recognized"] or 0,
            "unknown": stats["unknown"] or 0,
            "spoofing_attempts": stats["spoofing"] or 0,
            "unique_persons": stats["unique_persons"] or 0,
        },
    )
    logger.info(f"Daily stats computed for {yesterday}: {stats}")


@shared_task
def cleanup_old_media(days: int = 90):
    """Delete old event media files (runs at 03:00 daily)."""
    from django.db import close_old_connections
    close_old_connections()
    from apps.events.models import RecognitionEvent

    cutoff = timezone.now() - timedelta(days=days)
    old_events = RecognitionEvent.objects.filter(timestamp__lt=cutoff)
    deleted = 0

    for event in old_events.iterator(chunk_size=500):
        if event.frame_snapshot:
            try:
                event.frame_snapshot.delete(save=False)
            except Exception:
                pass
        if event.face_crop:
            try:
                event.face_crop.delete(save=False)
            except Exception:
                pass
        deleted += 1

    logger.info(f"Cleaned up media for {deleted} events older than {days} days.")
    return deleted


@shared_task(bind=True)
def start_camera_worker_task(self, camera_id: int):
    """Start the async CameraWorker for a given camera (long-running Celery task)."""
    from django.db import close_old_connections
    close_old_connections()
    import asyncio
    from django.core.cache import cache
    from workers.camera_worker import CameraWorker
    from apps.cameras.models import Camera

    try:
        # Register this task so the watchdog can check its state
        cache.set(f"camera_{camera_id}_worker_task_id", self.request.id, timeout=None)
        camera = Camera.objects.get(id=camera_id)
        worker = CameraWorker(camera)
        asyncio.run(worker.run())
    except Exception as exc:
        logger.error(f"Camera worker {camera_id} failed: {exc}")
        raise
    finally:
        from django.core.cache import cache as _cache
        _cache.delete(f"camera_{camera_id}_worker_task_id")


@shared_task
def watchdog_camera_workers():
    """
    Celery beat task — runs every 60 s.
    For every camera with status='active', check if its worker is alive
    (last_ping within 90 s). If not, fire a new start_camera_worker_task.
    """
    from django.db import close_old_connections
    close_old_connections()
    from django.core.cache import cache
    from celery.result import AsyncResult
    from apps.cameras.models import Camera

    stale_threshold = timezone.now() - timedelta(seconds=90)
    candidates = Camera.objects.filter(
        status="active",
    ).filter(
        # last_ping either never set or older than threshold
        last_ping__lt=stale_threshold,
    ) | Camera.objects.filter(status="active", last_ping__isnull=True)

    restarted = []
    for camera in candidates.distinct():
        task_id = cache.get(f"camera_{camera.id}_worker_task_id")
        if task_id:
            state = AsyncResult(task_id).state
            if state in ("PENDING", "STARTED", "RETRY"):
                # Task appears to be running; skip
                continue

        logger.warning(
            f"Watchdog: camera {camera.id} ({camera.name}) worker is dead "
            f"(last_ping={camera.last_ping}). Restarting..."
        )
        start_camera_worker_task.delay(camera.id)
        restarted.append(camera.id)

    if restarted:
        logger.info(f"Watchdog restarted workers for cameras: {restarted}")
    return restarted
