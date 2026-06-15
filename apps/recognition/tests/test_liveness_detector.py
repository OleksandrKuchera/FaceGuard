from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.modules.setdefault("cv2", types.SimpleNamespace())
sys.modules.setdefault("face_recognition", types.SimpleNamespace())

from ml.pipeline import LivenessDetector


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _landmarks(ear_state: str) -> dict:
    eye = _landmarks_for_ear(0.30 if ear_state == "open" else 0.10)["left_eye"]
    return {"left_eye": eye, "right_eye": eye}


def _landmarks_for_ear(ear: float) -> dict:
    vertical = ear * 2.0
    eye = [(0, 0), (1, vertical), (2, vertical), (4, 0), (2, -vertical), (1, -vertical)]
    return {"left_eye": eye, "right_eye": eye}


def _detector(clock: FakeClock) -> LivenessDetector:
    return LivenessDetector(
        ear_threshold=0.2,
        warmup_seconds=3.0,
        cooldown_seconds=5.0,
        required_blinks=1,
        min_closed_frames=1,
        max_closed_frames=8,
        min_open_frames_before_blink=2,
        min_valid_ear_frames_for_baseline=4,
        ear_relative_drop_ratio=0.78,
        ear_recovery_ratio=0.88,
        ear_smoothing_alpha=0.5,
        max_missing_frames=2,
        clock=clock,
    )


def test_real_face_with_valid_blink_becomes_live():
    clock = FakeClock()
    detector = _detector(clock)

    for _ in range(4):
        assert detector.check(_landmarks("open")).state == "WARMING_UP"
        clock.advance(0.4)
    detector.check(_landmarks("closed"))
    clock.advance(0.4)
    detector.check(_landmarks("closed"))
    clock.advance(1.5)
    result = detector.check(_landmarks("open"))

    assert result.state == "LIVE"
    assert result.allow_matching is True
    assert result.is_spoofing is False
    assert result.blinks_detected == 1
    assert result.reason_code == "blink_requirement_met"


def test_no_blink_during_warmup_fails_liveness():
    clock = FakeClock()
    detector = _detector(clock)

    for _ in range(4):
        detector.check(_landmarks("open"))
        clock.advance(0.8)
    result = detector.check(_landmarks("open"))

    assert result.state == "LIVENESS_FAILED"
    assert result.is_spoofing is True
    assert result.allow_matching is False


def test_missing_landmarks_returns_insufficient_data():
    clock = FakeClock()
    detector = _detector(clock)

    detector.check({})
    clock.advance(1.0)
    detector.check({})
    clock.advance(1.0)
    detector.check({})
    clock.advance(1.1)
    result = detector.check({})

    assert result.state == "INSUFFICIENT_DATA"
    assert result.is_spoofing is False
    assert result.allow_matching is False


def test_cooldown_blocks_immediate_recheck_and_then_restarts():
    clock = FakeClock()
    detector = _detector(clock)

    for _ in range(4):
        detector.check(_landmarks("open"))
        clock.advance(0.4)
    detector.check(_landmarks("closed"))
    clock.advance(0.4)
    detector.check(_landmarks("closed"))
    clock.advance(1.5)
    live_result = detector.check(_landmarks("open"))
    assert live_result.state == "LIVE"

    clock.advance(0.2)
    cooldown_result = detector.check(_landmarks("open"))
    assert cooldown_result.state == "COOLDOWN"
    assert cooldown_result.is_in_cooldown is True
    assert cooldown_result.allow_matching is False

    clock.advance(5.1)
    restarted = detector.check(_landmarks("open"))
    assert restarted.state == "WARMING_UP"
    assert restarted.is_warming_up is True
    assert restarted.blinks_detected == 0


def test_long_eye_closure_counts_as_one_blink():
    clock = FakeClock()
    detector = _detector(clock)

    for _ in range(4):
        detector.check(_landmarks("open"))
        clock.advance(0.3)
    for _ in range(2):
        clock.advance(0.6)
        detector.check(_landmarks("closed"))
    clock.advance(1.0)
    result = detector.check(_landmarks("open"))

    assert result.state == "LIVE"
    assert result.blinks_detected == 1


def test_natural_blink_is_detected_by_relative_drop_from_baseline():
    clock = FakeClock()
    detector = _detector(clock)

    # Baseline EAR ~0.26, natural blink dip only to ~0.21; this would often miss a fixed 0.20 threshold.
    for _ in range(5):
        detector.check(_landmarks_for_ear(0.26))
        clock.advance(0.35)

    detector.check(_landmarks_for_ear(0.21))
    clock.advance(0.35)
    detector.check(_landmarks_for_ear(0.20))
    clock.advance(1.7)
    result = detector.check(_landmarks_for_ear(0.25))

    assert result.state == "LIVE"
    assert result.blinks_detected == 1
    assert result.open_eye_baseline is not None
    assert result.blink_down_threshold is not None
    assert result.blink_down_threshold == pytest.approx(result.open_eye_baseline * 0.78, abs=1e-4)
    assert result.blink_recovery_threshold == pytest.approx(result.open_eye_baseline * 0.88, abs=1e-4)
    assert result.blink_down_threshold < result.open_eye_baseline
    assert result.blink_recovery_threshold < result.open_eye_baseline


def test_baseline_initializes_after_enough_valid_ear_frames_without_eye_state_dependency():
    clock = FakeClock()
    detector = _detector(clock)

    states = []
    for _ in range(4):
        result = detector.check(_landmarks_for_ear(0.26))
        states.append(result)
        clock.advance(0.2)

    collecting = states[0]
    ready = states[-1]

    assert collecting.open_eye_baseline is None
    assert collecting.eyes_state == "baseline_collecting"
    assert collecting.baseline_state == "COLLECTING"
    assert ready.open_eye_baseline is not None
    assert ready.baseline_ready is True
    assert ready.baseline_state == "READY"
    assert ready.eyes_state == "open"
    assert ready.frames_open_count >= 1
    assert ready.valid_eye_frames == 4


def test_baseline_is_not_reset_every_frame_after_initialization():
    clock = FakeClock()
    detector = _detector(clock)

    baselines = []
    for _ in range(6):
        result = detector.check(_landmarks_for_ear(0.26))
        baselines.append(result.open_eye_baseline)
        clock.advance(0.2)

    assert baselines[3] is not None
    assert baselines[4] is not None
    assert baselines[5] is not None
    assert detector.check(_landmarks_for_ear(0.26)).baseline_buffer_size >= 4


def test_configured_fixed_threshold_does_not_block_baseline_collection():
    clock = FakeClock()
    detector = LivenessDetector(
        ear_threshold=0.5,
        warmup_seconds=3.0,
        cooldown_seconds=5.0,
        required_blinks=1,
        min_closed_frames=1,
        max_closed_frames=8,
        min_open_frames_before_blink=2,
        min_valid_ear_frames_for_baseline=4,
        ear_relative_drop_ratio=0.75,
        ear_recovery_ratio=0.88,
        ear_smoothing_alpha=0.5,
        max_missing_frames=2,
        clock=clock,
    )

    for _ in range(4):
        result = detector.check(_landmarks_for_ear(0.26))
        clock.advance(0.2)

    assert result.open_eye_baseline is not None
    assert result.blink_down_threshold == pytest.approx(result.open_eye_baseline * 0.75, abs=1e-4)
    assert result.blink_recovery_threshold == pytest.approx(result.open_eye_baseline * 0.88, abs=1e-4)
    assert result.eyes_state == "open"


def test_baseline_not_initialized_bug_reason_is_exposed_when_baseline_calculation_fails():
    clock = FakeClock()
    detector = _detector(clock)
    detector._calculate_open_eye_baseline = lambda: None

    for _ in range(4):
        result = detector.check(_landmarks_for_ear(0.26))
        clock.advance(0.2)

    assert result.open_eye_baseline is None
    assert result.valid_eye_frames >= result.baseline_required_frames
    assert result.reason_code == "baseline_not_initialized_bug"
    assert result.baseline_state == "FAILED"
