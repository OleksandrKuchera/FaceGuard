"""
apps/cameras/serializers.py
"""
from rest_framework import serializers
from apps.cameras.models import Camera, CameraZone


class CameraZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = CameraZone
        fields = ["id", "name", "x1", "y1", "x2", "y2", "trigger_alert"]


class CameraListSerializer(serializers.ModelSerializer):
    """Full-field list serializer — frontend needs all fields for the Cameras table."""

    class Meta:
        model = Camera
        fields = [
            "id", "name", "location", "camera_code", "stream_url",
            "is_local", "status", "last_ping",
            "recognition_enabled", "detection_confidence",
            "frame_skip", "resolution_scale",
            "access_zone", "requires_mfa",
            "created_at",
        ]


class CameraDetailSerializer(serializers.ModelSerializer):
    zones = CameraZoneSerializer(many=True, read_only=True)

    class Meta:
        model = Camera
        fields = [
            "id", "name", "location", "camera_code", "stream_url",
            "is_local", "status", "last_ping",
            "recognition_enabled", "detection_confidence",
            "frame_skip", "resolution_scale",
            "access_zone", "requires_mfa",
            "zones", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "last_ping", "created_at", "updated_at"]


class CameraShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ["id", "name", "location", "status"]
