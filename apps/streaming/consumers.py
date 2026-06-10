"""
apps/streaming/consumers.py — WebSocket Consumer for live camera stream
"""
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)


class CameraStreamConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time camera streaming.

    Auth: JWT token via ?token=<access_token> query string
    Channel groups:
        camera_{camera_id} — all clients watching this camera
        alerts             — all authenticated clients (for global alerts)
    """

    async def connect(self):
        self.camera_id = self.scope["url_route"]["kwargs"]["camera_id"]
        self.camera_group = f"camera_{self.camera_id}"

        # JWT authentication
        token = self._extract_token()
        if not token:
            await self.close(code=4001)
            return

        user = await self._validate_jwt(token)
        if not user:
            await self.close(code=4001)
            return

        # RBAC check
        if not await self._has_camera_access(user, self.camera_id):
            await self.close(code=4003)
            return

        self.user = user

        # Join camera group + global alerts group
        await self.channel_layer.group_add(self.camera_group, self.channel_name)
        await self.channel_layer.group_add("alerts", self.channel_name)
        await self.accept()
        logger.info(f"WS connected: user={user.username}, camera={self.camera_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.camera_group, self.channel_name)
        await self.channel_layer.group_discard("alerts", self.channel_name)

    async def receive_json(self, content):
        action = content.get("action")
        if action == "request_snapshot":
            from django.core.cache import cache
            frame = await database_sync_to_async(cache.get)(
                f"camera_{self.camera_id}_last_frame"
            )
            if frame:
                await self.send_json({"type": "snapshot", "frame": f"data:image/jpeg;base64,{frame}"})

    # ── Handlers (called by channel layer) ─────────────────────────────

    async def camera_frame(self, event):
        """Forward frame from camera worker to this WS client."""
        await self.send_json(event["data"])

    async def camera_alert(self, event):
        """Forward alert to this WS client."""
        await self.send_json({"type": "alert", **event["data"]})

    async def camera_status(self, event):
        """Forward camera status change."""
        await self.send_json({"type": "camera_status", **event["data"]})

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
            logger.warning(f"WS JWT validation failed: {e}")
            return None

    @database_sync_to_async
    def _has_camera_access(self, user, camera_id: str) -> bool:
        if user.role in ("superadmin", "admin"):
            return True
        if user.role in ("guard", "readonly"):
            from apps.cameras.models import Camera
            return Camera.objects.filter(id=camera_id, status="active").exists()
        return False
