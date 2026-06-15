"""
apps/security/serializers.py
"""
from rest_framework import serializers
from apps.security.models import SpoofingAttempt, AuditLog


class SpoofingAttemptSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source="camera.name", read_only=True)

    class Meta:
        model = SpoofingAttempt
        fields = [
            "id", "camera", "camera_name", "event",
            "attack_type", "ear_value", "texture_score",
            "frame_evidence", "detected_at", "ip_address",
            "final_status", "final_reason_code", "final_module_name",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "user", "username", "action",
            "resource_type", "resource_id",
            "details_json", "ip_address", "timestamp",
        ]
