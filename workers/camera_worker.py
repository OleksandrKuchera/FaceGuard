"""
workers/camera_worker.py — Async Camera Worker
Captures frames, runs ML pipeline, saves events, broadcasts via WebSocket.
"""
import asyncio
import base64
import logging
import time

import cv2
import numpy as np
from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.conf import settings as django_settings
from django.utils import timezone

from apps.cameras.models import Camera
from apps.events.services import EventService
from ml.pipeline import FPSTracker

logger = logging.getLogger(__name__)

STOP_FLAG_TTL = 300  # seconds


class CameraWorker:
    """
    Independent process for processing a single camera stream.
    Started via Celery task (start_camera_worker_task).

    Architecture:
        CameraWorker
            ├── OpenCV VideoCapture
            ├── FaceRecognitionPipeline (ML singleton)
            ├── EventService (saves events to DB)
            └── ChannelLayer (WebSocket broadcast)
    """

    HEARTBEAT_INTERVAL = 30   # write last_ping to DB every N seconds
    HEARTBEAT_KEY      = "camera_{}_last_heartbeat"  # also stored in Redis

    def __init__(self, camera: Camera):
        self.camera = camera
        self.event_service = EventService()
        self._frame_count = 0
        self._fps_tracker = FPSTracker()
        self._stop_flag_key = f"camera_{camera.id}_stop"
        self._last_heartbeat = 0.0

    async def run(self):
        from apps.recognition.state import get_pipeline
        from channels.layers import get_channel_layer

        pipeline = get_pipeline()
        channel_layer = get_channel_layer()

        cap = cv2.VideoCapture(self._parse_stream_url(self.camera.stream_url))

        if not cap.isOpened():
            logger.error(f"Cannot open stream: {self.camera.stream_url}")
            await self._update_status("offline")
            return

        await self._update_status("active")
        logger.info(f"Camera worker started: {self.camera.name}")

        try:
            while True:
                # Graceful stop check
                if await sync_to_async(cache.get)(self._stop_flag_key):
                    logger.info(f"Stop signal received for camera {self.camera.id}")
                    break

                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Camera {self.camera.id}: frame read failed")
                    await asyncio.sleep(0.5)
                    continue

                self._frame_count += 1

                # Frame skipping for performance
                if self._frame_count % self.camera.frame_skip != 0:
                    continue

                if self.camera.recognition_enabled:
                    # ML processing with per-camera settings
                    result = pipeline.process_frame(
                        frame,
                        self.camera.id,
                        tolerance=self.camera.detection_confidence,
                        scale=self.camera.resolution_scale,
                    )
                    # Save events to DB
                    await self.event_service.create_events_from_result(
                        result, self.camera, frame
                    )
                else:
                    # Recognition disabled: broadcast raw frame without ML
                    result = pipeline.empty_result(frame)

                # Broadcast to WebSocket clients
                await self._broadcast_frame(channel_layer, frame, result)

                self._fps_tracker.tick()

                # Heartbeat: write last_ping to DB + Redis every 30 s
                now = time.monotonic()
                if now - self._last_heartbeat >= self.HEARTBEAT_INTERVAL:
                    self._last_heartbeat = now
                    ts = timezone.now()
                    await sync_to_async(
                        Camera.objects.filter(id=self.camera.id).update
                    )(last_ping=ts)
                    cache.set(
                        self.HEARTBEAT_KEY.format(self.camera.id),
                        ts.isoformat(),
                        timeout=self.HEARTBEAT_INTERVAL * 4,
                    )

                # Tiny sleep to prevent CPU starvation
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(f"Camera worker {self.camera.id} cancelled.")
        except Exception as e:
            logger.error(f"Camera worker {self.camera.id} error: {e}", exc_info=True)
        finally:
            cap.release()
            await self._update_status("offline")
            await sync_to_async(cache.delete)(self._stop_flag_key)
            logger.info(f"Camera worker stopped: {self.camera.name}")

    async def _broadcast_frame(self, channel_layer, frame: np.ndarray, result):
        """Encode frame as JPEG base64 and send to all WS clients of this camera."""
        try:
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buffer).decode()

            faces_data = [
                {
                    "bbox": face.location._asdict(),
                    "person_id": face.person_id,
                    "person_name": face.person_name,
                    "confidence": round(face.confidence, 1),
                    "is_known": face.person_id is not None,
                    "is_spoofing": face.is_spoofing,
                    "liveness_score": round(face.liveness_score, 2),
                    "is_warming_up": face.is_warming_up,
                    "is_in_cooldown": face.is_in_cooldown,
                    "liveness_state": face.liveness_state,
                    "liveness_reason": face.liveness_reason,
                    "final_status": face.liveness_state,
                    "final_reason_code": getattr(face, "final_reason_code", ""),
                    "final_module_name": getattr(face, "final_module_name", ""),
                    "texture_score": round(face.texture_score, 3),
                    "track_id": face.track_id,
                    "debug_enabled": bool(django_settings.LIVENESS_DEBUG_OVERLAY),
                    "debug": face.debug if django_settings.LIVENESS_DEBUG_OVERLAY else None,
                }
                for face in result.faces
            ]
            for face_data, face in zip(faces_data, result.faces):
                if not face.debug:
                    face_data.update({
                        "debug_hint": "diagnostic_payload_not_provided",
                    })
                    continue

                checks = (face.debug or {}).get("checks", {})
                blink = checks.get("blink_liveness", {})
                texture = checks.get("texture_combined", {})
                face_quality = checks.get("face_quality", {})
                face_data.update({
                    "blink_count": (face.debug or {}).get("blink_count"),
                    "min_blinks_required": blink.get("min_required"),
                    "blink_liveness_status": blink.get("status"),
                    "eye_state": (face.debug or {}).get("eyes_state"),
                    "current_ear_left": (face.debug or {}).get("ear_left"),
                    "current_ear_right": (face.debug or {}).get("ear_right"),
                    "current_ear_avg": (face.debug or {}).get("ear_avg"),
                    "smoothed_ear": (face.debug or {}).get("ear_smoothed"),
                    "open_eye_baseline": (face.debug or {}).get("open_eye_baseline"),
                    "drop_ratio": blink.get("drop_ratio"),
                    "recovery_ratio": blink.get("recovery_ratio"),
                    "blink_down_threshold": (face.debug or {}).get("blink_down_threshold"),
                    "blink_recovery_threshold": (face.debug or {}).get("blink_recovery_threshold"),
                    "baseline_buffer_size": (face.debug or {}).get("baseline_buffer_size"),
                    "baseline_required_frames": (face.debug or {}).get("baseline_required_frames"),
                    "baseline_ready": (face.debug or {}).get("baseline_ready"),
                    "baseline_state": (face.debug or {}).get("baseline_state"),
                    "frames_closed_count": (face.debug or {}).get("frames_closed_count"),
                    "frames_open_count": (face.debug or {}).get("frames_open_count"),
                    "valid_ear_frames_count": (face.debug or {}).get("valid_eye_frames"),
                    "missing_landmarks_count": (face.debug or {}).get("missing_landmarks_count"),
                    "previous_eye_state": (face.debug or {}).get("previous_eyes_state"),
                    "blink_internal_state": (face.debug or {}).get("blink_internal_state"),
                    "blink_event_detected_this_frame": (face.debug or {}).get("blink_event_detected_this_frame"),
                    "blink_event_history": blink.get("blink_event_history"),
                    "last_blink_event_time": blink.get("last_blink_event_time"),
                    "min_ear_seen_during_warmup": (face.debug or {}).get("min_ear_seen_during_warmup"),
                    "max_ear_seen_during_warmup": (face.debug or {}).get("max_ear_seen_during_warmup"),
                    "blink_reason_code": blink.get("reason_code") or (face.debug or {}).get("reason_code"),
                    "warmup_elapsed_seconds": (face.debug or {}).get("warmup_elapsed"),
                    "warmup_remaining_seconds": (face.debug or {}).get("warmup_remaining"),
                    "cooldown_remaining_seconds": (face.debug or {}).get("cooldown_remaining"),
                    "texture_combined_status": texture.get("status"),
                    "texture_lbp_status": checks.get("texture_lbp", {}).get("status"),
                    "texture_sobel_status": checks.get("texture_sobel", {}).get("status"),
                    "texture_fft_status": checks.get("texture_fft", {}).get("status"),
                    "face_quality_status": face_quality.get("status"),
                    "blink_detector_called": (face.debug or {}).get("blink_detector_called"),
                    "landmarks_found": (face.debug or {}).get("landmarks_found"),
                    "debug_hint": None if django_settings.LIVENESS_DEBUG_OVERLAY else "Set LIVENESS_DEBUG_OVERLAY=True for raw debug object and structured logs",
                })
            if django_settings.LIVENESS_DEBUG_OVERLAY:
                for face_data, face in zip(faces_data, result.faces):
                    face_data["debug"] = face.debug

            await channel_layer.group_send(
                f"camera_{self.camera.id}",
                {
                    "type": "camera_frame",
                    "data": {
                        "type": "frame",
                        "camera_id": self.camera.id,
                        "frame": f"data:image/jpeg;base64,{frame_b64}",
                        "faces": faces_data,
                        "fps": self._fps_tracker.current_fps,
                        "processing_ms": result.processing_ms,
                    },
                },
            )

            # Store last frame in Redis for snapshot endpoint
            await sync_to_async(cache.set)(
                f"camera_{self.camera.id}_last_frame",
                frame_b64,
                timeout=60,
            )

        except Exception as e:
            logger.debug(f"Broadcast error camera {self.camera.id}: {e}")

    async def _update_status(self, status: str):
        await sync_to_async(
            Camera.objects.filter(id=self.camera.id).update
        )(status=status)

    @staticmethod
    def _parse_stream_url(url: str):
        """Convert '0', '1' string to integer for USB cameras."""
        if url.isdigit():
            return int(url)
        return url
