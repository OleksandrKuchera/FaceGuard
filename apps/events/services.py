"""
apps/events/services.py — EventService: creating events from ML results
"""
import logging
import time

import cv2
import numpy as np
from django.core.files.base import ContentFile
from django.utils import timezone
from asgiref.sync import sync_to_async

from apps.events.models import RecognitionEvent
from apps.cameras.models import Camera

logger = logging.getLogger(__name__)

# ── Cooldown seconds per event type ──────────────────────────────────────────
# Prevents DB flooding when the same face stays in frame across many frames.
_COOLDOWN: dict[str, int] = {
    "recognized": 30,   # log same person at same camera at most once per 30s
    "unknown":    15,   # unknown face: re-log every 15s
    "spoofing":    5,   # spoofing: alert frequently but not every frame
    "multi_face": 20,
    "low_quality": 60,  # rarely interesting to repeat
}
_DEFAULT_COOLDOWN = 30


class EventService:
    def __init__(self):
        # key: "{camera_id}_{event_type}_{person_id_or_none}" → last_event_time
        self._last_event: dict[str, float] = {}

    def _cooldown_key(self, camera_id: int, event_type: str, person_id) -> str:
        return f"{camera_id}_{event_type}_{person_id or 'unknown'}"

    def _should_create_event(self, camera_id: int, event_type: str, person_id) -> bool:
        """Return True if the cooldown period has elapsed since the last event."""
        key = self._cooldown_key(camera_id, event_type, person_id)
        cooldown = _COOLDOWN.get(event_type, _DEFAULT_COOLDOWN)
        last = self._last_event.get(key, 0.0)
        return (time.monotonic() - last) >= cooldown

    def _record_event(self, camera_id: int, event_type: str, person_id) -> None:
        key = self._cooldown_key(camera_id, event_type, person_id)
        self._last_event[key] = time.monotonic()

    async def create_events_from_result(
        self,
        result,           # FrameResult from ml.pipeline
        camera: Camera,
        frame: np.ndarray,
    ) -> list[RecognitionEvent]:
        events = []

        # Exclude faces still in the liveness warm-up window — no real decision yet.
        active_faces = [f for f in result.faces if not f.is_warming_up]

        if not active_faces:
            return events

        # ── Multi-face event (2+ simultaneous faces after warmup) ────────────
        if len(active_faces) > 1:
            if self._should_create_event(camera.id, "multi_face", None):
                self._record_event(camera.id, "multi_face", None)
                now = timezone.now()
                event = await sync_to_async(RecognitionEvent.objects.create)(
                    camera=camera,
                    person_id=None,
                    event_type="multi_face",
                    confidence=0.0,
                    distance=None,
                    liveness_score=0.5,
                    timestamp=now,
                    face_bbox_json={},
                    is_alert=bool(camera.access_zone),
                )
                await sync_to_async(self._save_snapshots)(event, frame, None)
                events.append(event)
                if camera.access_zone:
                    await self._send_alert(event, camera)

        for face in active_faces:
            if face.is_spoofing:
                event_type = "spoofing"
            elif face.person_id:
                event_type = "recognized"
            else:
                event_type = "unknown"

            # ── Cooldown guard ────────────────────────────────────────────────
            if not self._should_create_event(camera.id, event_type, face.person_id):
                continue

            self._record_event(camera.id, event_type, face.person_id)

            is_alert = event_type in ("spoofing", "unknown") and bool(camera.access_zone)

            event = await sync_to_async(RecognitionEvent.objects.create)(
                camera=camera,
                person_id=face.person_id,
                event_type=event_type,
                confidence=face.confidence,
                distance=face.distance,
                liveness_score=face.liveness_score,
                timestamp=timezone.now(),
                face_bbox_json=face.location._asdict(),
                is_alert=is_alert,
            )

            await sync_to_async(self._save_snapshots)(event, frame, face.location)

            if face.is_spoofing:
                await sync_to_async(self._create_spoofing_attempt)(event, camera, face)

            events.append(event)

            if is_alert:
                await self._send_alert(event, camera)

        return events

    def _save_snapshots(self, event: RecognitionEvent, frame: np.ndarray, location) -> None:
        try:
            update_fields = []

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            event.frame_snapshot.save(
                f"event_{event.id}_frame.jpg",
                ContentFile(buf.tobytes()),
                save=False,
            )
            update_fields.append("frame_snapshot")

            if location is not None:
                top, right, bottom, left = (
                    location.top, location.right, location.bottom, location.left
                )
                face_img = frame[top:bottom, left:right]
                if face_img.size > 0:
                    _, face_buf = cv2.imencode(".jpg", face_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    event.face_crop.save(
                        f"event_{event.id}_face.jpg",
                        ContentFile(face_buf.tobytes()),
                        save=False,
                    )
                    update_fields.append("face_crop")

            event.save(update_fields=update_fields)
        except Exception as e:
            logger.error(f"Failed to save snapshots for event {event.id}: {e}")

    def _create_spoofing_attempt(self, event: RecognitionEvent, camera: Camera, face) -> None:
        """Create a SpoofingAttempt record linked to the spoofing event."""
        try:
            from apps.security.models import SpoofingAttempt

            ear_value = None
            if face.landmarks:
                left_eye = face.landmarks.get("left_eye", [])
                right_eye = face.landmarks.get("right_eye", [])
                if left_eye and right_eye:
                    ear_value = self._estimate_ear(left_eye, right_eye)

            texture_score = getattr(face, "texture_score", None)
            attack_type = self._classify_attack_type(ear_value, texture_score)

            SpoofingAttempt.objects.create(
                camera=camera,
                event=event,
                attack_type=attack_type,
                ear_value=ear_value,
                texture_score=texture_score,
            )
        except Exception as e:
            logger.error(f"Failed to create SpoofingAttempt for event {event.id}: {e}")

    @staticmethod
    def _classify_attack_type(ear_value, texture_score) -> str:
        """
        Infer spoofing method from EAR and texture signals.

        Photo attack: printed/displayed still image — no eye movement (low EAR) +
                      flat texture (low entropy / poor gradient variance).
        Video attack: replayed video that may contain blinks — some texture variation
                      but still below the liveness threshold.
        """
        if texture_score is None:
            return "unknown"

        # Low texture score = very flat surface (photo or screen with little variation)
        flat_texture = texture_score < 0.35

        # Low EAR = no convincing eye-open state detected (static image)
        no_movement = ear_value is None or ear_value < 0.18

        if flat_texture and no_movement:
            return "photo"

        if flat_texture and not no_movement:
            # Texture is bad but eyes seem to move → video replay
            return "video"

        # texture_score >= 0.35 but still flagged as spoof → ambiguous
        return "unknown"

    @staticmethod
    def _estimate_ear(left_eye: list, right_eye: list) -> float:
        """Estimate average EAR from landmark tuples for the SpoofingAttempt record."""
        import numpy as np

        def ear(eye):
            p = np.array(eye, dtype=np.float64)
            if len(p) < 6:
                return 0.0
            v1 = np.linalg.norm(p[1] - p[5])
            v2 = np.linalg.norm(p[2] - p[4])
            h = np.linalg.norm(p[0] - p[3])
            return (v1 + v2) / (2.0 * h) if h > 1e-6 else 0.0

        return round((ear(left_eye) + ear(right_eye)) / 2.0, 4)

    async def _send_alert(self, event: RecognitionEvent, camera: Camera):
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                "alerts",
                {
                    "type": "camera_alert",
                    "data": {
                        "alert_level": "high" if event.event_type == "spoofing" else "medium",
                        "message": self._alert_message(event),
                        "camera_id": camera.id,
                        "event_id": event.id,
                        "timestamp": event.timestamp.isoformat(),
                    },
                },
            )
        except Exception as e:
            logger.error(f"Failed to send alert for event {event.id}: {e}")

    @staticmethod
    def _alert_message(event: RecognitionEvent) -> str:
        msgs = {
            "spoofing":   f"Виявлено спробу підробки на камері {event.camera.name}!",
            "multi_face": f"Декілька осіб одночасно на камері {event.camera.name}!",
        }
        return msgs.get(event.event_type, f"Невідома особа на камері {event.camera.name}!")
