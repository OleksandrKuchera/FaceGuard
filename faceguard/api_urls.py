"""
FaceGuard — Aggregate API URL Router
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)

from apps.core.views import UserViewSet, health_check, system_settings
from apps.persons.views import PersonViewSet, DepartmentViewSet
from apps.cameras.views import CameraViewSet
from apps.events.views import RecognitionEventViewSet
from apps.reports.views import ReportViewSet
from apps.security.views import SpoofingAttemptViewSet, AuditLogViewSet


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """Login endpoint — rate-limited to prevent brute-force attacks."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class ThrottledTokenRefreshView(TokenRefreshView):
    """Refresh endpoint — same auth scope throttle."""
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"persons", PersonViewSet, basename="person")
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"cameras", CameraViewSet, basename="camera")
router.register(r"events", RecognitionEventViewSet, basename="event")
router.register(r"reports", ReportViewSet, basename="report")
router.register(r"security/spoofing", SpoofingAttemptViewSet, basename="spoofing")
router.register(r"security/audit-log", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    # System
    path("health/", health_check, name="health_check"),
    path("settings/", system_settings, name="system_settings"),
    # JWT Auth (throttled)
    path("auth/token/", ThrottledTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", ThrottledTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="token_blacklist"),
    # REST API
    path("", include(router.urls)),
]
