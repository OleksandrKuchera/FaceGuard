"""
apps/reports/views.py — ReportViewSet
"""
from django.http import FileResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdminOrAbove, IsGuardOrAbove
from apps.reports.models import Report
from apps.reports.serializers import ReportSerializer


class ReportViewSet(viewsets.ModelViewSet):
    serializer_class = ReportSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Report.objects.filter(created_by=self.request.user).order_by("-created_at")

    def get_permissions(self):
        return [IsGuardOrAbove()]

    def perform_create(self, serializer):
        report = serializer.save(created_by=self.request.user, status="pending")
        from workers.tasks import generate_report
        generate_report.delay(report.id)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        report = self.get_object()
        if report.status != "ready" or not report.file:
            return Response({"error": "Report not ready."}, status=404)
        response = FileResponse(report.file.open("rb"), as_attachment=True)
        response["Content-Disposition"] = f'attachment; filename="{report.file.name.split("/")[-1]}"'
        return response
