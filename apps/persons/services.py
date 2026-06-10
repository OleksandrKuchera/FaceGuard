"""
apps/persons/services.py — Business logic for person management
"""
import logging

from django.utils import timezone

from apps.persons.models import Person, PersonPhoto, FaceEncoding
from ml.pipeline import EncodingRecord, NoFaceDetectedError, MultipleFacesError

logger = logging.getLogger(__name__)


def register_person(data: dict, photo_files=None) -> Person:
    """Register a new person and optionally upload photos, then trigger encoding."""
    person = Person.objects.create(**data)
    if person.consent_given and not person.consent_date:
        person.consent_date = timezone.now()
        person.save(update_fields=["consent_date"])
    logger.info(f"Person registered: {person}")

    if photo_files:
        for photo_file in photo_files:
            PersonPhoto.objects.create(person=person, image=photo_file)

    if photo_files and person.consent_given and not person.deletion_requested:
        from workers.tasks import validate_and_encode_photos
        validate_and_encode_photos.delay(person.id)

    return person


def train_person_encodings(person_id: int) -> dict:
    """
    Generate FaceEncoding records from validated photos. Called by Celery task.

    Uses encode_from_location() to avoid re-running face detection that was
    already done in the validation step — cuts encoding time roughly in half.
    Sets quality_score on PersonPhoto and marks the first encoding as primary.
    """
    from apps.recognition.state import get_pipeline

    person = Person.objects.get(id=person_id)
    if not person.consent_given or person.deletion_requested or not person.is_active:
        logger.info(
            "Skip training for person %s: consent=%s deletion_requested=%s active=%s",
            person_id,
            person.consent_given,
            person.deletion_requested,
            person.is_active,
        )
        return {"person_id": person_id, "success": 0, "errors": ["biometric_processing_not_allowed"]}
    photos = person.photos.filter(face_detected=True, is_processed=False)

    results = {"person_id": person_id, "success": 0, "errors": []}

    # Determine if this person already has any encodings (for is_primary logic)
    already_has_encodings = person.encodings.exists()

    for photo in photos:
        try:
            pipeline = get_pipeline()

            # Use location stored during validation to skip redundant face detection.
            # Fall back to full encode_photo() if location not cached (older photos).
            if photo.landmarks_json and "face_location" in photo.landmarks_json:
                loc = tuple(photo.landmarks_json["face_location"])
                encoding_array, quality = pipeline.encoder.encode_from_location(
                    photo.image.path, loc
                )
            else:
                encoding_array, loc, quality = pipeline.encoder.encode_photo(photo.image.path)

            # Persist quality score
            photo.quality_score = quality
            photo.landmarks_json = {**(photo.landmarks_json or {}), "face_location": list(loc)}

            enc = FaceEncoding(person=person, model_version="resnet_v1")
            enc.set_encoding(encoding_array)
            # First encoding for this person is marked primary
            enc.is_primary = not already_has_encodings and results["success"] == 0
            enc.save()

            photo.is_processed = True
            photo.save(update_fields=["is_processed", "quality_score", "landmarks_json"])
            results["success"] += 1

        except (NoFaceDetectedError, MultipleFacesError) as e:
            results["errors"].append(str(e))
            logger.warning(f"Photo {photo.id}: {e}")
        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"Unexpected error photo {photo.id}: {e}")

    # Reload pipeline encoding cache
    try:
        get_pipeline().reload_encodings()
    except Exception as e:
        logger.error(f"Failed to reload encodings cache: {e}")

    return results


def load_all_encodings() -> list[EncodingRecord]:
    """Load all active face encodings from DB for the pipeline in-memory cache."""
    records = []
    qs = FaceEncoding.objects.filter(
        person__is_active=True,
        person__consent_given=True,
        person__deletion_requested=False,
    ).select_related("person")

    for enc in qs:
        try:
            records.append(
                EncodingRecord(
                    person_id=enc.person_id,
                    person_name=enc.person.full_name,
                    encoding=enc.get_encoding(),
                )
            )
        except Exception as e:
            logger.error(f"Failed to load encoding {enc.id}: {e}")

    logger.info(f"Loaded {len(records)} face encodings from DB.")
    return records


def anonymize_person(person: Person):
    """GDPR right to erasure — removes all biometric data."""
    person.encodings.all().delete()

    for photo in person.photos.all():
        photo.image.delete(save=False)
        photo.delete()

    person.first_name = "ANONYMIZED"
    person.last_name = ""
    person.middle_name = ""
    person.person_id = f"ANON-{person.id}"
    person.is_active = False
    person.deletion_date = timezone.now()
    person.save()

    from apps.events.models import RecognitionEvent
    RecognitionEvent.objects.filter(person=person).update(person=None)

    from apps.security.models import AuditLog
    AuditLog.objects.create(
        action="person_anonymized",
        resource_type="Person",
        resource_id=str(person.id),
    )
