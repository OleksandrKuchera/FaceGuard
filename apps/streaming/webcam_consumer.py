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
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

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
            texture_threshold=0.85,
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
                "liveness_score": round(face.liveness_score, 2),
                "texture_score": round(face.texture_score, 2),
                "texture_is_spoof": face.texture_is_spoof,
                "liveness_is_spoofing": face.liveness_is_spoofing,
                "track_id": face.track_id,
                "landmarks": face.landmarks or {},
            }
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
