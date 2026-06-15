"""
apps/recognition/apps.py — ML Pipeline singleton initialization
"""
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RecognitionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.recognition"
    verbose_name = "Розпізнавання"

    def ready(self):
        """Initialize ML pipeline singleton when Django starts."""
        # Skip during migrations / management commands that don't need ML
        import sys
        if any(cmd in sys.argv for cmd in ["migrate", "makemigrations", "collectstatic", "shell"]):
            return

        try:
            from django.conf import settings as django_settings
            from ml.pipeline import FaceRecognitionPipeline, PipelineSettings
            import apps.recognition.state as state

            pipeline_settings = PipelineSettings(
                detector_model=django_settings.FACE_DETECTOR_MODEL,
                tolerance=django_settings.FACE_TOLERANCE,
                min_confidence=django_settings.FACE_MIN_CONFIDENCE,
                liveness_enabled=django_settings.LIVENESS_ENABLED,
                liveness_threshold=django_settings.LIVENESS_THRESHOLD,
                liveness_warmup_seconds=django_settings.LIVENESS_WARMUP_SECONDS,
                liveness_cooldown_seconds=django_settings.LIVENESS_COOLDOWN_SECONDS,
                liveness_required_blinks=django_settings.LIVENESS_REQUIRED_BLINKS,
                liveness_min_closed_frames=django_settings.LIVENESS_MIN_CLOSED_FRAMES,
                liveness_max_closed_frames=django_settings.LIVENESS_MAX_CLOSED_FRAMES,
                liveness_min_open_frames_before_blink=django_settings.LIVENESS_MIN_OPEN_FRAMES_BEFORE_BLINK,
                liveness_min_valid_ear_frames_for_baseline=django_settings.LIVENESS_MIN_VALID_EAR_FRAMES_FOR_BASELINE,
                liveness_ear_relative_drop_ratio=django_settings.LIVENESS_EAR_RELATIVE_DROP_RATIO,
                liveness_ear_recovery_ratio=django_settings.LIVENESS_EAR_RECOVERY_RATIO,
                liveness_ear_smoothing_alpha=django_settings.LIVENESS_EAR_SMOOTHING_ALPHA,
                liveness_max_missing_frames=django_settings.LIVENESS_MAX_MISSING_FRAMES,
                texture_min_face_size_px=django_settings.TEXTURE_MIN_FACE_SIZE_PX,
                texture_min_quality_score=django_settings.TEXTURE_MIN_QUALITY_SCORE,
                liveness_debug_overlay=django_settings.LIVENESS_DEBUG_OVERLAY,
            )

            state.pipeline = FaceRecognitionPipeline(pipeline_settings)
            # Load encodings from DB (will be empty on first run)
            state.pipeline.reload_encodings()
            logger.info("ML Pipeline initialized and encodings loaded.")

        except Exception as e:
            logger.error(f"Failed to initialize ML Pipeline: {e}")
