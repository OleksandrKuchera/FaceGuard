"""
apps/core/views.py — UserViewSet + health-check + system-settings
"""
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.models import SystemSettings
from apps.core.permissions import IsAdminOrAbove, IsSuperAdmin

User = get_user_model()


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    GET /api/v1/health/
    Returns status of DB, Redis/cache, and Celery.
    Safe to call without authentication (used by uptime monitors).
    """
    checks = {}

    # Database
    try:
        connection.ensure_connection()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"

    # Redis / cache
    try:
        from django.core.cache import cache
        cache.set("_health", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("_health") == "1" else "miss"
    except Exception as e:
        checks["cache"] = f"error: {e}"

    # Celery — inspect active workers (non-blocking, 1s timeout)
    try:
        from celery.app.control import Inspect
        from faceguard.celery import app as celery_app
        insp = Inspect(app=celery_app, timeout=1.0)
        ping = insp.ping()
        checks["celery"] = "ok" if ping else "no_workers"
    except Exception as e:
        checks["celery"] = f"error: {e}"

    ok = all(v == "ok" for v in checks.values())
    return Response(
        {"status": "ok" if ok else "degraded", "checks": checks},
        status=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@api_view(["GET", "PUT"])
@permission_classes([IsAdminOrAbove])
def system_settings(request):
    """
    GET  /api/v1/settings/  → all settings (DB values merged with defaults)
    PUT  /api/v1/settings/  → save one or more sections {general: {...}, ml: {...}, ...}
    """
    if request.method == "GET":
        rows = {s.key: s.value for s in SystemSettings.objects.all()}
        result = {
            key: rows.get(key, default)
            for key, default in SystemSettings.DEFAULTS.items()
        }
        return Response(result)

    # PUT — update provided sections only
    updated = []
    for key, value in request.data.items():
        if key not in SystemSettings.DEFAULTS:
            continue
        SystemSettings.objects.update_or_create(key=key, defaults={"value": value})
        updated.append(key)
    return Response({"status": "saved", "updated": updated})


User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "first_name", "last_name",
            "email", "role", "is_active", "date_joined",
        ]
        read_only_fields = ["date_joined"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active"]


class PasswordResetSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=6)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("username")

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == "destroy":
            return [IsSuperAdmin()]
        return [IsAdminOrAbove()]

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response({"detail": "Cannot deactivate yourself."}, status=400)
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminOrAbove])
    def reset_password(self, request, pk=None):
        user = self.get_object()
        ser = PasswordResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user.set_password(ser.validated_data["password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated."})
