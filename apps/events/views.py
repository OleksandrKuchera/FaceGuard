"""
apps/events/views.py — RecognitionEventViewSet
"""
import datetime
from django.db.models import Count, Q, F, Value
from django.db.models.functions import ExtractHour, Concat
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsGuardOrAbove
from apps.events.analytics import get_or_build_daily_stats
from apps.events.models import RecognitionEvent
from apps.events.serializers import RecognitionEventSerializer


class RecognitionEventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecognitionEventSerializer
    permission_classes = [IsGuardOrAbove]
    filterset_fields = ["camera", "person", "event_type", "is_alert"]
    ordering_fields = ["timestamp", "confidence"]
    ordering = ["-timestamp"]
    search_fields = ["person__person_id", "person__first_name", "person__last_name", "camera__name"]

    def get_queryset(self):
        qs = RecognitionEvent.objects.select_related("camera", "person", "reviewed_by")

        if date_from := self.request.query_params.get("date_from"):
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to := self.request.query_params.get("date_to"):
            qs = qs.filter(timestamp__date__lte=date_to)
        if person := self.request.query_params.get("person"):
            person_filter = (
                Q(person__person_id__icontains=person)
                | Q(person__first_name__icontains=person)
                | Q(person__last_name__icontains=person)
            )
            if person.isdigit():
                person_filter |= Q(person__id=int(person))
            qs = qs.filter(person_filter)

        return qs

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Today's quick stats for dashboard."""
        today = timezone.now().date()
        agg = RecognitionEvent.objects.filter(timestamp__date=today).aggregate(
            today=Count("id"),
            recognized=Count("id", filter=Q(event_type="recognized")),
            unknown=Count("id", filter=Q(event_type="unknown")),
            spoofing=Count("id", filter=Q(event_type="spoofing")),
            alerts=Count("id", filter=Q(is_alert=True)),
        )
        return Response(agg)

    @action(detail=False, methods=["get"])
    def daily_stats(self, request):
        """Historical daily stats."""
        today = timezone.localdate()
        rows = [
            get_or_build_daily_stats(today - datetime.timedelta(days=offset))
            for offset in range(29, -1, -1)
        ]
        return Response(rows)

    @action(detail=False, methods=["get"])
    def hourly_heatmap(self, request):
        """
        Events per hour-of-day for the last 14 days.
        Returns list of {hour: 0-23, count: N} — enough for a 24-column heatmap.
        """
        since = timezone.now() - datetime.timedelta(days=14)
        rows = (
            RecognitionEvent.objects
            .filter(timestamp__gte=since)
            .annotate(hour=ExtractHour("timestamp"))
            .values("hour")
            .annotate(count=Count("id"))
            .order_by("hour")
        )
        return Response(list(rows))

    @action(detail=False, methods=["get"])
    def top_visitors(self, request):
        """Top-5 recognized persons by visit count over the last 30 days."""
        since = timezone.now() - datetime.timedelta(days=30)
        rows = (
            RecognitionEvent.objects
            .filter(event_type="recognized", timestamp__gte=since, person__isnull=False)
            .values(
                person_id=F("person__id"),
                full_name=Concat(
                    F("person__last_name"),
                    Value(" "),
                    F("person__first_name"),
                ),
                department=F("person__department__name"),
            )
            .annotate(visits=Count("id"))
            .order_by("-visits")[:5]
        )
        return Response(list(rows))

    @action(detail=False, methods=["get"])
    def camera_stats(self, request):
        """Event counts per camera for the last 7 days (for bar chart)."""
        since = timezone.now() - datetime.timedelta(days=7)
        rows = (
            RecognitionEvent.objects
            .filter(timestamp__gte=since)
            .values(camera_name=F("camera__name"))
            .annotate(
                total=Count("id"),
                recognized=Count("id", filter=Q(event_type="recognized")),
                unknown=Count("id", filter=Q(event_type="unknown")),
                spoofing=Count("id", filter=Q(event_type="spoofing")),
            )
            .order_by("-total")
        )
        return Response(list(rows))

    @action(detail=True, methods=["patch"])
    def review(self, request, pk=None):
        """Mark event as reviewed."""
        event = self.get_object()
        event.reviewed_by = request.user
        event.reviewed_at = timezone.now()
        event.save(update_fields=["reviewed_by", "reviewed_at"])
        return Response(RecognitionEventSerializer(event).data)
