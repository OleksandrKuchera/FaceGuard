import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cameras.models import Camera
from apps.events.models import RecognitionEvent
from apps.persons.models import Person


@pytest.mark.django_db
def test_events_endpoint_filters_by_numeric_person_primary_key():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="guard1",
        password="secret123",
        role="guard",
    )
    person = Person.objects.create(
        first_name="Ivan",
        last_name="Petrenko",
        person_id="EMP-1001",
    )
    other_person = Person.objects.create(
        first_name="Olena",
        last_name="Shevchenko",
        person_id="EMP-1002",
    )
    camera = Camera.objects.create(
        name="Front Gate",
        location="Lobby",
        camera_code="CAM-001",
        stream_url="0",
    )
    RecognitionEvent.objects.create(
        camera=camera,
        person=person,
        event_type="recognized",
        timestamp=timezone.now(),
    )
    RecognitionEvent.objects.create(
        camera=camera,
        person=other_person,
        event_type="recognized",
        timestamp=timezone.now() - datetime.timedelta(minutes=5),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(reverse("event-list"), {"person": str(person.id)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["results"][0]["person"]["id"] == person.id
