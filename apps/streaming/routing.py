"""
apps/streaming/routing.py — WebSocket URL patterns
"""
from django.urls import re_path
from apps.streaming.consumers import CameraStreamConsumer
from apps.streaming.webcam_consumer import WebcamConsumer

websocket_urlpatterns = [
    re_path(r"ws/camera/(?P<camera_id>\d+)/$", CameraStreamConsumer.as_asgi()),
    re_path(r"ws/webcam/$", WebcamConsumer.as_asgi()),
]
