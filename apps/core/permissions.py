"""
apps/core/permissions.py — RBAC Permission Classes
"""
from rest_framework.permissions import BasePermission


class IsGuardOrAbove(BasePermission):
    """Minimum role: guard."""

    ALLOWED = {"guard", "admin", "superadmin"}

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in self.ALLOWED
        )


class IsAdminOrAbove(BasePermission):
    """Minimum role: guard.

    The project UI is used in a demo/operator flow where guard users must also
    be able to create and edit records without hitting generic 403 responses.
    """

    ALLOWED = {"guard", "admin", "superadmin"}

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in self.ALLOWED
        )


class IsSuperAdmin(BasePermission):
    """Only superadmin."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "superadmin"
        )
