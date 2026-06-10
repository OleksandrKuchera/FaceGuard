"""
apps/persons/views.py — PersonViewSet, DepartmentViewSet
"""
import logging

from django.core.cache import cache
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.core.permissions import IsAdminOrAbove, IsGuardOrAbove, IsSuperAdmin
from apps.persons.models import Person, PersonPhoto, Department
from apps.persons.serializers import (
    PersonListSerializer, PersonDetailSerializer,
    PersonPhotoSerializer, DepartmentSerializer,
)

logger = logging.getLogger(__name__)

# Cache key pattern for Celery train task IDs
_TRAIN_TASK_KEY = "person_{person_id}_train_task_id"


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsGuardOrAbove()]
        return [IsAdminOrAbove()]


class PersonViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    search_fields = ["first_name", "last_name", "middle_name", "person_id"]

    def get_queryset(self):
        qs = Person.objects.select_related("department").all()
        if dept := self.request.query_params.get("department"):
            qs = qs.filter(department_id=dept)
        if role := self.request.query_params.get("role"):
            qs = qs.filter(role=role)
        if is_active := self.request.query_params.get("is_active"):
            qs = qs.filter(is_active=is_active.lower() == "true")
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return PersonListSerializer
        return PersonDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsGuardOrAbove()]
        return [IsAdminOrAbove()]

    def perform_update(self, serializer):
        """Reload encoding cache when is_active changes (deactivation/reactivation)."""
        old_active = serializer.instance.is_active
        old_consent = serializer.instance.consent_given
        instance = serializer.save()
        if instance.consent_given and not instance.consent_date:
            instance.consent_date = timezone.now()
            instance.save(update_fields=["consent_date"])
        elif not instance.consent_given and old_consent:
            instance.consent_date = None
            instance.save(update_fields=["consent_date"])
        if instance.is_active != old_active or instance.consent_given != old_consent:
            try:
                from apps.recognition.state import get_pipeline
                get_pipeline().reload_encodings()
                logger.info(
                    f"Encoding cache reloaded: person {instance.id} "
                    f"state changed active={old_active}→{instance.is_active}, consent={old_consent}→{instance.consent_given}"
                )
            except Exception as e:
                logger.error(f"Failed to reload encodings after person update: {e}")

    def perform_create(self, serializer):
        instance = serializer.save()
        if instance.consent_given and not instance.consent_date:
            instance.consent_date = timezone.now()
            instance.save(update_fields=["consent_date"])

    def destroy(self, request, *args, **kwargs):
        """Soft delete — deactivation, not deletion."""
        person = self.get_object()
        was_active = person.is_active
        person.is_active = False
        person.save(update_fields=["is_active"])

        if was_active:
            try:
                from apps.recognition.state import get_pipeline
                get_pipeline().reload_encodings()
            except Exception:
                pass

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, JSONParser])
    def photos(self, request, pk=None):
        """List or upload training photos for a person."""
        person = self.get_object()

        if request.method == "GET":
            qs = PersonPhoto.objects.filter(person=person).order_by("-uploaded_at")
            return Response(PersonPhotoSerializer(qs, many=True, context={"request": request}).data)

        # POST — upload
        if not person.consent_given or person.deletion_requested:
            return Response(
                {"error": "Biometric processing is not allowed for this person."},
                status=status.HTTP_403_FORBIDDEN,
            )

        files = request.FILES.getlist("image")
        if not files:
            return Response({"error": "No image file provided."}, status=400)

        photos = []
        for f in files:
            photo = PersonPhoto.objects.create(person=person, image=f)
            photos.append(PersonPhotoSerializer(photo, context={"request": request}).data)

        from workers.tasks import validate_and_encode_photos
        validate_and_encode_photos.delay(person.id)

        return Response(photos, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path=r"photos/(?P<photo_id>\d+)")
    def delete_photo(self, request, pk=None, photo_id=None):
        photo = PersonPhoto.objects.filter(person_id=pk, id=photo_id).first()
        if not photo:
            return Response(status=404)
        photo.image.delete(save=False)
        photo.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def train(self, request, pk=None):
        """Trigger encoding training for this person."""
        person = self.get_object()
        if not person.consent_given or person.deletion_requested:
            return Response(
                {"error": "Biometric processing is not allowed for this person."},
                status=status.HTTP_403_FORBIDDEN,
            )
        from workers.tasks import train_person_task
        task = train_person_task.delay(person.id)

        # Store task ID in cache so train_status can report it
        cache.set(_TRAIN_TASK_KEY.format(person_id=person.id), task.id, timeout=3600)

        return Response({"task_id": task.id, "status": "pending"})

    @action(detail=True, methods=["get"], url_path="train/status")
    def train_status(self, request, pk=None):
        """Get training status and Celery task state for this person."""
        person = self.get_object()
        encodings = person.encodings.filter(
            person__is_active=True,
            person__consent_given=True,
            person__deletion_requested=False,
        ).count()
        processed = person.photos.filter(is_processed=True).count()
        total_photos = person.photos.count()
        failed_photos = person.photos.filter(face_detected=False).count()

        # Celery task status
        task_id = cache.get(_TRAIN_TASK_KEY.format(person_id=person.id))
        task_state = None
        if task_id:
            try:
                from celery.result import AsyncResult
                result = AsyncResult(task_id)
                task_state = result.state  # PENDING / STARTED / SUCCESS / FAILURE
            except Exception:
                pass

        # Best quality photo score
        best_quality = (
            person.photos
            .filter(face_detected=True)
            .order_by("-quality_score")
            .values_list("quality_score", flat=True)
            .first()
        )

        return Response({
            "encodings_created": encodings,
            "photos_processed": processed,
            "photos_failed": failed_photos,
            "total_photos": total_photos,
            "best_quality_score": best_quality,
            "task_id": task_id,
            "task_state": task_state,
            "is_ready": encodings > 0 and person.consent_given and not person.deletion_requested and person.is_active,
        })

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsSuperAdmin],
    )
    def anonymize(self, request, pk=None):
        """GDPR right to erasure — irreversible. Restricted to superadmin."""
        person = self.get_object()
        from apps.persons.services import anonymize_person
        anonymize_person(person)
        # Reload cache to remove anonymized person's encodings immediately
        try:
            from apps.recognition.state import get_pipeline
            get_pipeline().reload_encodings()
        except Exception:
            pass
        return Response({"detail": "Person anonymized successfully."})
