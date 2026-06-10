"""
apps/events/admin.py
"""
from django.contrib import admin
from apps.events.models import RecognitionEvent, DailyStats


@admin.register(RecognitionEvent)
class RecognitionEventAdmin(admin.ModelAdmin):
    list_display = ["id", "event_type", "person", "camera", "confidence", "is_alert", "timestamp"]
    list_filter = ["event_type", "is_alert", "camera"]
    search_fields = ["person__first_name", "person__last_name", "camera__name"]
    readonly_fields = ["timestamp", "processed_at", "reviewed_at"]
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False


@admin.register(DailyStats)
class DailyStatsAdmin(admin.ModelAdmin):
    list_display = ["date", "total_events", "recognized", "unknown", "spoofing_attempts", "unique_persons"]
    readonly_fields = ["computed_at"]
