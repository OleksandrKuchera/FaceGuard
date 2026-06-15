import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cameras.models import Camera
from apps.events.models import RecognitionEvent
from apps.security.models import SpoofingAttempt


@pytest.mark.django_db
def test_event_endpoint_without_spoofing_detail():
    # 1. Create a user and authenticate
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="guard1",
        password="secret123",
        role="guard",
    )
    
    # 2. Create camera and event (without spoofing_detail)
    camera = Camera.objects.create(
        name="Front Gate",
        location="Lobby",
        camera_code="CAM-001",
        stream_url="0",
    )
    
    event = RecognitionEvent.objects.create(
        camera=camera,
        event_type="recognized",
        timestamp=timezone.now(),
    )
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    # 3. GET /api/v1/events/ should return 200 and spoofing_meta should be null
    response = client.get(reverse("event-list"))
    assert response.status_code == 200
    
    payload = response.json()
    assert payload["count"] == 1
    
    serialized_event = payload["results"][0]
    assert serialized_event["id"] == event.id
    assert serialized_event["spoofing_meta"] is None


@pytest.mark.django_db
def test_event_endpoint_with_spoofing_detail():
    # 1. Create a user and authenticate
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="guard2",
        password="secret123",
        role="guard",
    )
    
    # 2. Create camera and event
    camera = Camera.objects.create(
        name="Front Gate",
        location="Lobby",
        camera_code="CAM-002",
        stream_url="0",
    )
    
    event = RecognitionEvent.objects.create(
        camera=camera,
        event_type="spoofing",
        timestamp=timezone.now(),
    )
    
    # 3. Create spoofing_detail (SpoofingAttempt)
    spoofing_detail = SpoofingAttempt.objects.create(
        camera=camera,
        event=event,
        attack_type="photo",
        ear_value=0.15,
        texture_score=0.22,
        final_status="SPOOF",
        final_reason_code="texture_check_failed",
        final_module_name="TextureAntiSpoofing",
    )
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    # 4. GET /api/v1/events/ should return 200 and spoofing_meta with final_status/final_reason_code/final_module_name
    response = client.get(reverse("event-list"))
    assert response.status_code == 200
    
    payload = response.json()
    assert payload["count"] == 1
    
    serialized_event = payload["results"][0]
    assert serialized_event["id"] == event.id
    
    meta = serialized_event["spoofing_meta"]
    assert meta is not None
    assert meta["attack_type"] == "photo"
    assert meta["ear_value"] == 0.15
    assert meta["texture_score"] == 0.22
    assert meta["final_status"] == "SPOOF"
    assert meta["final_reason_code"] == "texture_check_failed"
    assert meta["final_module_name"] == "TextureAntiSpoofing"
