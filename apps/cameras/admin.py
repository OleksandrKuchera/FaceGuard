"""
apps/cameras/admin.py
"""
from django.contrib import admin
from apps.cameras.models import Camera, CameraZone


class CameraZoneInline(admin.TabularInline):
    model = CameraZone
    extra = 0


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ["camera_code", "name", "location", "status", "recognition_enabled"]
    list_filter = ["status", "recognition_enabled", "is_local"]
    search_fields = ["name", "camera_code", "location"]
    inlines = [CameraZoneInline]
    readonly_fields = ["last_ping", "status"]

    actions = ["mark_active", "mark_offline"]

    @admin.action(description="Позначити як Активна")
    def mark_active(self, request, queryset):
        queryset.update(status="active")

    @admin.action(description="Позначити як Офлайн")
    def mark_offline(self, request, queryset):
        queryset.update(status="offline")
