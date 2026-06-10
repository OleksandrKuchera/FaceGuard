"""
apps/reports/admin.py
"""
from django.contrib import admin
from apps.reports.models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["name", "report_type", "format", "status", "created_by", "created_at"]
    list_filter = ["report_type", "format", "status"]
    search_fields = ["name"]
    readonly_fields = ["status", "error_message", "created_at", "generated_at", "file"]
