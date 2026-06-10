"""
apps/recognition/state.py — Global ML pipeline reference
"""
from typing import Optional

# Set by RecognitionConfig.ready()
pipeline = None  # type: Optional["ml.pipeline.FaceRecognitionPipeline"]


def get_pipeline():
    """Returns the global pipeline instance. Raises if not initialized."""
    if pipeline is None:
        raise RuntimeError("ML Pipeline is not initialized. Is RecognitionConfig.ready() called?")
    return pipeline
