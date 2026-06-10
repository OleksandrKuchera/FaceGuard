"""
apps/cameras/views.py — CameraViewSet
"""
import logging

from django.core.cache import cache
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrAbove, IsGuardOrAbove
from apps.cameras.models import Camera, CameraZone
from apps.cameras.serializers import CameraListSerializer, CameraDetailSerializer, CameraZoneSerializer

logger = logging.getLogger(__name__)


class CameraViewSet(viewsets.ModelViewSet):

    def get_queryset(self):
        return Camera.objects.prefetch_related("zones").all()

    def get_serializer_class(self):
        if self.action == "list":
            return CameraListSerializer
        return CameraDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "snapshot"):
            return [IsGuardOrAbove()]
        return [IsAdminOrAbove()]

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test camera connectivity."""
        camera = self.get_object()
        try:
            import cv2
            url = int(camera.stream_url) if camera.stream_url.isdigit() else camera.stream_url
            cap = cv2.VideoCapture(url)
            connected = cap.isOpened()
            cap.release()
            return Response({"connected": connected})
        except Exception as e:
            return Response({"connected": False, "error": str(e)})

    @action(detail=True, methods=["get"])
    def snapshot(self, request, pk=None):
        """Return last frame from Redis cache."""
        frame_data = cache.get(f"camera_{pk}_last_frame")
        if not frame_data:
            return Response({"error": "No snapshot available. Is the camera running?"}, status=404)
        return Response({"frame": f"data:image/jpeg;base64,{frame_data}"})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Launch camera worker via Celery."""
        camera = self.get_object()
        if camera.status == "active":
            return Response({"detail": "Camera is already running."})
        from workers.tasks import start_camera_worker_task
        task = start_camera_worker_task.delay(camera.id)
        return Response({"task_id": task.id, "status": "starting"})

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        """Send stop signal to camera worker via Redis flag."""
        pk_int = int(pk)
        cache.set(f"camera_{pk_int}_stop", 1, timeout=60)
        return Response({"detail": "Stop signal sent."})

    # ── Zone CRUD ────────────────────────────────────────────────────────────

    @action(detail=True, methods=["get", "post"], url_path="zones")
    def zones(self, request, pk=None):
        """GET list / POST create zone for this camera."""
        camera = self.get_object()
        if request.method == "GET":
            ser = CameraZoneSerializer(camera.zones.all(), many=True)
            return Response(ser.data)
        # POST
        if not IsAdminOrAbove().has_permission(request, self):
            return Response(status=status.HTTP_403_FORBIDDEN)
        ser = CameraZoneSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(camera=camera)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["put", "patch", "delete"],
        url_path=r"zones/(?P<zone_id>[0-9]+)",
    )
    def zone_detail(self, request, pk=None, zone_id=None):
        """PUT/PATCH update / DELETE remove a zone."""
        if not IsAdminOrAbove().has_permission(request, self):
            return Response(status=status.HTTP_403_FORBIDDEN)
        camera = self.get_object()
        try:
            zone = camera.zones.get(id=zone_id)
        except CameraZone.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if request.method == "DELETE":
            zone.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        partial = request.method == "PATCH"
        ser = CameraZoneSerializer(zone, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
