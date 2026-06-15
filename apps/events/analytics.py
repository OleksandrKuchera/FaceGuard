"""
Helpers for consistent event analytics across dashboard, tasks and reports.
"""
from __future__ import annotations

from datetime import date

from django.db.models import Count, Q

from apps.events.models import DailyStats, RecognitionEvent


EVENT_TYPE_LABELS = {
    "recognized": "Розпізнано",
    "unknown": "Невідома особа",
    "spoofing": "Спуфінг",
    "multi_face": "Кілька облич",
    "low_quality": "Низька якість",
}


def event_type_label(event_type: str) -> str:
    return EVENT_TYPE_LABELS.get(event_type, event_type)


def aggregate_stats_for_date(target_date: date) -> dict[str, int | date]:
    stats = RecognitionEvent.objects.filter(
        timestamp__date=target_date
    ).aggregate(
        total_events=Count("id"),
        recognized=Count("id", filter=Q(event_type="recognized")),
        unknown=Count("id", filter=Q(event_type="unknown")),
        spoofing_attempts=Count("id", filter=Q(event_type="spoofing")),
        unique_persons=Count("person", distinct=True),
    )
    return {
        "date": target_date,
        "total_events": stats["total_events"] or 0,
        "recognized": stats["recognized"] or 0,
        "unknown": stats["unknown"] or 0,
        "spoofing_attempts": stats["spoofing_attempts"] or 0,
        "unique_persons": stats["unique_persons"] or 0,
    }


def get_or_build_daily_stats(target_date: date) -> dict[str, int | date]:
    stored = DailyStats.objects.filter(date=target_date).values(
        "date",
        "total_events",
        "recognized",
        "unknown",
        "spoofing_attempts",
        "unique_persons",
    ).first()
    return stored or aggregate_stats_for_date(target_date)
