"""
apps/security/views.py — SpoofingAttemptViewSet, AuditLogViewSet
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrAbove, IsSuperAdmin
from apps.security.models import SpoofingAttempt, AuditLog
from apps.security.serializers import SpoofingAttemptSerializer, AuditLogSerializer


class SpoofingAttemptViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SpoofingAttempt.objects.select_related("camera", "event").order_by("-detected_at")
    serializer_class = SpoofingAttemptSerializer
    permission_classes = [IsAdminOrAbove]
    filterset_fields = ["camera", "attack_type"]

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregate spoofing statistics for the Security dashboard."""
        now = timezone.now()

        totals = SpoofingAttempt.objects.aggregate(
            total=Count("id"),
            photo_attacks=Count("id", filter=Q(attack_type="photo")),
            video_attacks=Count("id", filter=Q(attack_type="video")),
            unknown_attacks=Count("id", filter=Q(attack_type="unknown")),
        )

        last_24h = SpoofingAttempt.objects.filter(
            detected_at__gte=now - timedelta(hours=24)
        ).count()

        last_7d = SpoofingAttempt.objects.filter(
            detected_at__gte=now - timedelta(days=7)
        ).count()

        unique_cameras = (
            SpoofingAttempt.objects.values("camera").distinct().count()
        )

        return Response({
            "total_spoofing": totals["total"] or 0,
            "photo_attacks": totals["photo_attacks"] or 0,
            "video_attacks": totals["video_attacks"] or 0,
            "unknown_attacks": totals["unknown_attacks"] or 0,
            "last_24h": last_24h,
            "last_7d": last_7d,
            "unique_cameras_affected": unique_cameras,
        })


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ["user", "action", "resource_type"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        if date_from := self.request.query_params.get("date_from"):
            qs = qs.filter(timestamp__date__gte=date_from)
        return qs
