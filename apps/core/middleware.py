"""
apps/core/middleware.py — Security Audit Middleware
"""
import logging
from apps.security.models import AuditLog

logger = logging.getLogger(__name__)

SENSITIVE_PATHS = [
    "/api/v1/persons/",
    "/api/v1/security/",
]


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _extract_resource_type(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    return parts[2] if len(parts) >= 3 else (parts[-1] if parts else "")


class SecurityAuditMiddleware:
    """
    Logs all mutating API requests and accesses to sensitive paths.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        should_log = (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            or any(request.path.startswith(p) for p in SENSITIVE_PATHS)
        )

        if should_log and request.user.is_authenticated:
            try:
                AuditLog.objects.create(
                    user=request.user,
                    action=f"{request.method} {request.path}",
                    resource_type=_extract_resource_type(request.path),
                    ip_address=_get_client_ip(request),
                    details_json={
                        "method": request.method,
                        "path": request.path,
                        "status_code": response.status_code,
                    },
                )
            except Exception as e:
                logger.error(f"AuditLog write failed: {e}")

        return response
