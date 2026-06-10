"""
apps/reports/serializers.py
"""
from rest_framework import serializers
from apps.reports.models import Report


class ReportSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    download_url = serializers.SerializerMethodField()

    def get_download_url(self, obj: Report) -> str | None:
        if obj.file:
            request = self.context.get("request")
            url = obj.file.url
            return request.build_absolute_uri(url) if request else url
        return None

    class Meta:
        model = Report
        fields = [
            "id", "name", "report_type", "format",
            "params_json", "status", "error_message",
            "created_by", "created_by_name",
            "created_at", "generated_at",
            "download_url",
        ]
        read_only_fields = [
            "status", "error_message", "created_by",
            "created_at", "generated_at", "download_url",
        ]
