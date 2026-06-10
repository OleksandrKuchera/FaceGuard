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
            )

            state.pipeline = FaceRecognitionPipeline(pipeline_settings)
            # Load encodings from DB (will be empty on first run)
            state.pipeline.reload_encodings()
            logger.info("ML Pipeline initialized and encodings loaded.")

        except Exception as e:
            logger.error(f"Failed to initialize ML Pipeline: {e}")
