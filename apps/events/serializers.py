"""
apps/events/serializers.py
"""
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from apps.events.models import RecognitionEvent, DailyStats
from apps.cameras.serializers import CameraShortSerializer
from apps.persons.serializers import PersonShortSerializer
from apps.events.analytics import event_type_label


class RecognitionEventSerializer(serializers.ModelSerializer):
    camera = CameraShortSerializer(read_only=True)
    person = PersonShortSerializer(read_only=True)
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    spoofing_meta = serializers.SerializerMethodField()
    person_display = serializers.SerializerMethodField()

    class Meta:
        model = RecognitionEvent
        fields = [
            "id", "camera", "person",
            "person_display",
            "event_type", "event_type_display",
            "confidence", "distance", "liveness_score",
            "timestamp", "processed_at",
            "is_alert", "alert_sent",
            "face_bbox_json",
            "frame_snapshot", "face_crop",
            "spoofing_meta",
            "reviewed_by", "reviewed_at",
        ]
        read_only_fields = ["processed_at", "alert_sent"]

    def get_spoofing_meta(self, obj):
        try:
            spoof = obj.spoofing_detail
        except ObjectDoesNotExist:
            return None

        return {
            "attack_type": spoof.attack_type,
            "attack_type_display": spoof.get_attack_type_display(),
            "ear_value": spoof.ear_value,
            "texture_score": spoof.texture_score,
            "detected_at": spoof.detected_at,
            "final_status": spoof.final_status,
            "final_reason_code": spoof.final_reason_code,
            "final_module_name": spoof.final_module_name,
        }

    def get_person_display(self, obj):
        if obj.person:
            return f"{obj.person.full_name} ({obj.person.person_id})"
        if obj.event_type == "spoofing":
            return event_type_label("spoofing")
        if obj.event_type == "multi_face":
            return event_type_label("multi_face")
        return "Невідома особа"


class DailyStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyStats
        fields = [
            "date", "total_events", "recognized",
            "unknown", "spoofing_attempts", "unique_persons", "computed_at",
        ]
