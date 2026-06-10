"""
apps/security/admin.py
"""
from django.contrib import admin
from apps.security.models import SpoofingAttempt, AuditLog


@admin.register(SpoofingAttempt)
class SpoofingAttemptAdmin(admin.ModelAdmin):
    list_display = ["detected_at", "camera", "attack_type", "ear_value", "ip_address"]
    list_filter = ["attack_type", "camera"]
    readonly_fields = ["detected_at"]

    def has_add_permission(self, request):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "resource_type", "ip_address"]
    list_filter = ["resource_type"]
    search_fields = ["action", "user__username"]
    readonly_fields = ["timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
