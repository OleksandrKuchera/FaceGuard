"""
apps/events/serializers.py
"""
from rest_framework import serializers
from apps.events.models import RecognitionEvent, DailyStats
from apps.cameras.serializers import CameraShortSerializer
from apps.persons.serializers import PersonShortSerializer


class RecognitionEventSerializer(serializers.ModelSerializer):
    camera = CameraShortSerializer(read_only=True)
    person = PersonShortSerializer(read_only=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)

    class Meta:
        model = RecognitionEvent
        fields = [
            "id", "camera", "person",
            "event_type", "event_type_display",
            "confidence", "distance", "liveness_score",
            "timestamp", "processed_at",
            "is_alert", "alert_sent",
            "face_bbox_json",
            "frame_snapshot", "face_crop",
            "reviewed_by", "reviewed_at",
        ]
        read_only_fields = ["processed_at", "alert_sent"]


class DailyStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyStats
        fields = [
            "date", "total_events", "recognized",
            "unknown", "spoofing_attempts", "unique_persons", "computed_at",
        ]
