"""
apps/streaming/webcam_consumer.py — WebSocket Consumer для браузерної веб-камери.

Клієнт (браузер) відправляє кадри з камери ноутбука через getUserMedia,
сервер обробляє їх через ML pipeline і повертає результати розпізнавання.
"""
import base64
import logging
import time

import cv2
import numpy as np
from asgiref.sync import sync_to_async, async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings as django_settings

from apps.events.services import EventService

logger = logging.getLogger(__name__)


class WebcamConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer для розпізнавання облич з браузерної веб-камери.

    Протокол:
      Клієнт → Сервер:  {"action": "frame", "frame": "data:image/jpeg;base64,..."}
      Сервер → Клієнт:  {"type": "result", "faces": [...], "fps": ..., "processing_ms": ...}
      Сервер → Клієнт:  {"type": "error", "message": "..."}

    Auth: JWT token через ?token=<access_token>
    """

    async def connect(self):
        token = self._extract_token()
        if not token:
            await self.close(code=4001)
            return

        user = await self._validate_jwt(token)
        if not user:
            await self.close(code=4001)
            return

        if not await self._has_access(user):
            await self.close(code=4003)
            return

        self.user = user
        self.webcam_session_id = abs(hash(self.channel_name)) % 1_000_000_000
        self.demo_camera_id = self._extract_camera_id()
        self.camera = await self._get_or_create_demo_camera(self.demo_camera_id)
        self.event_service = EventService()
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.fps = 0.0

        await self.accept()
        logger.info("WS webcam connected: user=%s", user.username)

    async def disconnect(self, close_code):
        logger.info("WS webcam disconnected: user=%s, code=%d", self.user.username, close_code)

    async def receive_json(self, content):
        action = content.get("action")

        if action == "frame":
            frame_b64 = content.get("frame", "")
            if not frame_b64:
                await self.send_json({"type": "error", "message": "Empty frame"})
                return

            try:
                # Decode base64 frame
                if "," in frame_b64:
                    frame_b64 = frame_b64.split(",", 1)[1]
                img_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    await self.send_json({"type": "error", "message": "Failed to decode frame"})
                    return

                # Process through ML pipeline (sync → async)
                result = await sync_to_async(self._process_frame)(frame)

                # FPS calculation
                self.frame_count += 1
                now = time.time()
                elapsed = now - self.last_fps_time
                if elapsed >= 1.0:
                    self.fps = self.frame_count / elapsed
                    self.frame_count = 0
                    self.last_fps_time = now

                await self.send_json({
                    "type": "result",
                    "faces": result["faces"],
                    "fps": round(self.fps, 1),
                    "processing_ms": result["processing_ms"],
                })

            except Exception as exc:
                logger.error("Webcam frame processing error: %s", exc)
                await self.send_json({"type": "error", "message": str(exc)})

        elif action == "ping":
            await self.send_json({"type": "pong"})

    def _process_frame(self, frame: np.ndarray) -> dict:
        """Run frame through ML pipeline. Runs in thread pool."""
        from apps.recognition.state import get_pipeline

        pipeline = get_pipeline()
        if pipeline is None:
            return {"faces": [], "processing_ms": 0}

        # Use a session-scoped camera id to keep tracker/liveness state isolated per browser tab.
        frame_result = pipeline.process_frame(
            frame,
            camera_id=self.webcam_session_id,
            strict_liveness=True,
            scale=0.25,
        )

        async_to_sync(self.event_service.create_events_from_result)(
            frame_result,
            self.camera,
            frame,
        )

        faces = []
        for face in frame_result.faces:
            face_data = {
                "bbox": {
                    "top": face.location.top,
                    "right": face.location.right,
                    "bottom": face.location.bottom,
                    "left": face.location.left,
                },
                "person_id": face.person_id,
                "person_name": face.person_name,
                "confidence": round(face.confidence, 1),
                "distance": round(face.distance, 4) if face.distance is not None else None,
                "is_known": face.person_id is not None,
                "is_spoofing": face.is_spoofing,
                "is_warming_up": face.is_warming_up,
                "is_in_cooldown": face.is_in_cooldown,
                "liveness_state": face.liveness_state,
                "liveness_reason": face.liveness_reason,
                "final_status": face.liveness_state,
                "final_reason_code": getattr(face, "final_reason_code", ""),
                "final_module_name": getattr(face, "final_module_name", ""),
                "liveness_score": round(face.liveness_score, 2),
                "texture_score": round(face.texture_score, 2),
                "texture_is_spoof": face.texture_is_spoof,
                "liveness_is_spoofing": face.liveness_is_spoofing,
                "track_id": face.track_id,
                "landmarks": face.landmarks or {},
                "debug_enabled": bool(django_settings.LIVENESS_DEBUG_OVERLAY),
                "debug": face.debug if django_settings.LIVENESS_DEBUG_OVERLAY else None,
            }
            if face.debug:
                checks = face.debug.get("checks", {})
                blink = checks.get("blink_liveness", {})
                texture = checks.get("texture_combined", {})
                face_quality = checks.get("face_quality", {})
                face_data.update({
                    "blink_count": face.debug.get("blink_count"),
                    "min_blinks_required": blink.get("min_required"),
                    "blink_liveness_status": blink.get("status"),
                    "eye_state": face.debug.get("eyes_state"),
                    "current_ear_left": face.debug.get("ear_left"),
                    "current_ear_right": face.debug.get("ear_right"),
                    "current_ear_avg": face.debug.get("ear_avg"),
                    "smoothed_ear": face.debug.get("ear_smoothed"),
                    "open_eye_baseline": face.debug.get("open_eye_baseline"),
                    "drop_ratio": blink.get("drop_ratio"),
                    "recovery_ratio": blink.get("recovery_ratio"),
                    "blink_down_threshold": face.debug.get("blink_down_threshold"),
                    "blink_recovery_threshold": face.debug.get("blink_recovery_threshold"),
                    "baseline_buffer_size": face.debug.get("baseline_buffer_size"),
                    "baseline_required_frames": face.debug.get("baseline_required_frames"),
                    "baseline_ready": face.debug.get("baseline_ready"),
                    "baseline_state": face.debug.get("baseline_state"),
                    "frames_closed_count": face.debug.get("frames_closed_count"),
                    "frames_open_count": face.debug.get("frames_open_count"),
                    "valid_ear_frames_count": face.debug.get("valid_eye_frames"),
                    "missing_landmarks_count": face.debug.get("missing_landmarks_count"),
                    "previous_eye_state": face.debug.get("previous_eyes_state"),
                    "blink_internal_state": face.debug.get("blink_internal_state"),
                    "blink_event_detected_this_frame": face.debug.get("blink_event_detected_this_frame"),
                    "blink_event_history": blink.get("blink_event_history"),
                    "last_blink_event_time": blink.get("last_blink_event_time"),
                    "min_ear_seen_during_warmup": face.debug.get("min_ear_seen_during_warmup"),
                    "max_ear_seen_during_warmup": face.debug.get("max_ear_seen_during_warmup"),
                    "blink_reason_code": blink.get("reason_code") or face.debug.get("reason_code"),
                    "warmup_elapsed_seconds": face.debug.get("warmup_elapsed"),
                    "warmup_remaining_seconds": face.debug.get("warmup_remaining"),
                    "cooldown_remaining_seconds": face.debug.get("cooldown_remaining"),
                    "texture_combined_status": texture.get("status"),
                    "texture_lbp_status": checks.get("texture_lbp", {}).get("status"),
                    "texture_sobel_status": checks.get("texture_sobel", {}).get("status"),
                    "texture_fft_status": checks.get("texture_fft", {}).get("status"),
                    "face_quality_status": face_quality.get("status"),
                    "blink_detector_called": face.debug.get("blink_detector_called"),
                    "landmarks_found": face.debug.get("landmarks_found"),
                    "debug_hint": None if django_settings.LIVENESS_DEBUG_OVERLAY else "Set LIVENESS_DEBUG_OVERLAY=True for raw debug object and structured logs",
                })
            else:
                face_data.update({
                    "debug_hint": "diagnostic_payload_not_provided",
                })
            faces.append(face_data)

        return {
            "faces": faces,
            "processing_ms": round(frame_result.processing_ms, 1),
        }

    # ── Helpers ────────────────────────────────────────────────────────

    def _extract_token(self) -> str | None:
        qs = self.scope.get("query_string", b"").decode()
        for part in qs.split("&"):
            if part.startswith("token="):
                return part[6:]
        return None

    def _extract_camera_id(self) -> int:
        qs = self.scope.get("query_string", b"").decode()
        for part in qs.split("&"):
            if part.startswith("camera_id="):
                try:
                    return int(part.split("=", 1)[1])
                except ValueError:
                    return 1
        return 1

    @database_sync_to_async
    def _validate_jwt(self, token_str: str):
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            from apps.core.models import User
            token = AccessToken(token_str)
            return User.objects.get(id=token["user_id"])
        except Exception as e:
            logger.warning("Webcam WS JWT validation failed: %s", e)
            return None

    @database_sync_to_async
    def _has_access(self, user) -> bool:
        # All authenticated users can use webcam
        return True

    @database_sync_to_async
    def _get_or_create_demo_camera(self, demo_camera_id: int):
        from apps.cameras.models import Camera

        camera_code = f"DEMO-{demo_camera_id}"
        camera, created = Camera.objects.get_or_create(
            camera_code=camera_code,
            defaults={
                "name": f"Камера {demo_camera_id}",
                "location": "Локальна веб-камера",
                "stream_url": "0",
                "is_local": True,
                "status": "active",
                "recognition_enabled": True,
                "detection_confidence": 0.55,
                "frame_skip": 2,
                "resolution_scale": 0.25,
            },
        )
        if not created and camera.status != "active":
            camera.status = "active"
            camera.save(update_fields=["status"])
        return camera
