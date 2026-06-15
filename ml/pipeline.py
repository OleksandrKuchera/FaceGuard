"""
ml/pipeline.py — Головний ML Pipeline

Singleton клас що тримає в пам'яті:
- Завантажені моделі dlib
- Кешований список encodings з БД

Ініціалізується один раз при старті Django (apps.py ready())
"""

from __future__ import annotations

import logging
import time
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from typing import Optional

import cv2
import face_recognition
import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────── Data Classes ────────────────────────────────

@dataclass
class EncodingRecord:
    """Один запис в кеші encodings"""
    person_id: int
    person_name: str
    encoding: np.ndarray


@dataclass
class FaceLocation:
    top: int
    right: int
    bottom: int
    left: int

    def as_tuple(self):
        return (self.top, self.right, self.bottom, self.left)

    def _asdict(self):
        return {"top": self.top, "right": self.right, "bottom": self.bottom, "left": self.left}

    @property
    def center(self):
        return ((self.top + self.bottom) / 2, (self.left + self.right) / 2)


@dataclass
class FaceResult:
    location: FaceLocation
    person_id: Optional[int] = None
    person_name: Optional[str] = None
    confidence: float = 0.0
    distance: Optional[float] = None
    liveness_score: float = 0.5
    is_spoofing: bool = False
    texture_is_spoof: bool = False
    liveness_is_spoofing: bool = False
    is_warming_up: bool = True       # True during first 3-second liveness window
    texture_score: float = 1.0       # 0=likely spoofing, 1=likely real
    track_id: Optional[int] = None
    landmarks: Optional[dict] = None
    liveness_state: str = "IDLE"
    liveness_reason: str = ""
    is_in_cooldown: bool = False
    debug: Optional[dict] = None
    final_reason_code: str = ""
    final_module_name: str = ""


@dataclass
class FrameResult:
    faces: list[FaceResult]
    frame_size: tuple = (0, 0)
    processing_ms: float = 0.0


@dataclass
class PipelineSettings:
    detector_model: str = "hog"
    tolerance: float = 0.55
    min_confidence: float = 45.0
    liveness_enabled: bool = True
    liveness_threshold: float = 0.20
    liveness_warmup_seconds: float = 4.0
    liveness_cooldown_seconds: float = 5.0
    liveness_required_blinks: int = 1
    liveness_min_closed_frames: int = 1
    liveness_max_closed_frames: int = 8
    liveness_min_open_frames_before_blink: int = 2
    liveness_min_valid_ear_frames_for_baseline: int = 8
    liveness_ear_relative_drop_ratio: float = 0.78
    liveness_ear_recovery_ratio: float = 0.88
    liveness_ear_smoothing_alpha: float = 0.40
    liveness_max_missing_frames: int = 6
    frame_scale: float = 0.25
    texture_spoof_threshold: float = 0.25   # below this → texture spoofing detected
    texture_enabled: bool = True
    texture_min_face_size_px: int = 48
    texture_min_quality_score: float = 0.08
    liveness_debug_overlay: bool = False


@dataclass
class TextureCheckResult:
    status: str
    score: Optional[float] = None
    threshold: Optional[float] = None
    reason: str = ""
    lbp_score: Optional[float] = None
    sobel_score: Optional[float] = None
    fft_score: Optional[float] = None


@dataclass
class FaceQualityCheckResult:
    status: str
    reason: str
    landmarks_found: bool
    missing_frames: int
    face_confidence: float
    quality_score: float
    face_size_px: int


# ──────────────────────────────── Preprocessor ───────────────────────────────

class ImagePreprocessor:
    """
    CLAHE препроцесинг для покращення точності при поганому освітленні.
    Ефект: +9.8% при низькому освітленні, +16.7% при контровому світлі.
    """

    def __init__(self, clip_limit: float = 2.0, tile_grid: tuple = (8, 8)):
        self.clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)

    def process(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        enhanced = self.clahe.apply(gray)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def resize(image: np.ndarray, scale: float = 0.25) -> np.ndarray:
        return cv2.resize(image, (0, 0), fx=scale, fy=scale)


# ───────────────────────────────── Detector ──────────────────────────────────

class FaceDetector:
    """HOG або CNN детектор облич"""

    def __init__(self, model: str = "hog"):
        if model not in ("hog", "cnn"):
            raise ValueError(f"Невідома модель детектора: {model}")
        self.model = model

    def detect(self, rgb_frame: np.ndarray) -> list[tuple]:
        """Returns: список (top, right, bottom, left)"""
        return face_recognition.face_locations(rgb_frame, model=self.model)


# ────────────────────────────────── Encoder ──────────────────────────────────

class NoFaceDetectedError(Exception):
    pass


class MultipleFacesError(Exception):
    pass


class FaceEncoder:
    """Генерує 128-вимірні векторні представлення через ResNet-29 (dlib)"""

    def encode(
        self,
        rgb_image: np.ndarray,
        face_locations: list[tuple],
        num_jitters: int = 1,
    ) -> list[np.ndarray]:
        return face_recognition.face_encodings(
            rgb_image,
            known_face_locations=face_locations,
            num_jitters=num_jitters,
        )

    def encode_photo(self, image_path: str) -> tuple[np.ndarray, tuple, float]:
        """
        Кодування фото для реєстрації.
        Returns: (encoding, location_tuple, quality_score)
        Raises: NoFaceDetectedError, MultipleFacesError
        """
        image = face_recognition.load_image_file(image_path)
        locations = face_recognition.face_locations(image, model="hog")

        if len(locations) == 0:
            raise NoFaceDetectedError(f"Обличчя не знайдено: {image_path}")
        if len(locations) > 1:
            raise MultipleFacesError(f"Знайдено {len(locations)} облич на фото: {image_path}")

        encoding = face_recognition.face_encodings(image, locations)[0]
        quality = _compute_quality_score(image, locations[0])
        return encoding, locations[0], quality

    def encode_from_location(
        self,
        image_path: str,
        location: tuple,
    ) -> tuple[np.ndarray, float]:
        """
        Кодування з відомим location — пропускає повторну детекцію.
        Returns: (encoding, quality_score)
        """
        image = face_recognition.load_image_file(image_path)
        encoding = face_recognition.face_encodings(image, [location])[0]
        quality = _compute_quality_score(image, location)
        return encoding, quality


# ────────────────────────────────── Matcher ──────────────────────────────────

@dataclass
class MatchResult:
    person_id: int
    person_name: str
    confidence: float
    distance: float


class FaceMatcher:
    """
    Двоступенева фільтрація:
    1. Tolerance: Евклідова відстань < threshold
    2. Confidence: (1 - distance) * 100 > min_confidence

    Метрики при tolerance=0.55, min_confidence=45:
        FAR: 4.3%, FRR: 3.8%, Accuracy: 96.0%
    """

    def __init__(self, tolerance: float = 0.55, min_confidence: float = 45.0):
        self.tolerance = tolerance
        self.min_confidence = min_confidence

    def match(
        self,
        unknown_encoding: np.ndarray,
        known_encodings: list[EncodingRecord],
        tolerance_override: Optional[float] = None,
    ) -> Optional[MatchResult]:

        if not known_encodings:
            return None

        tolerance = tolerance_override if tolerance_override is not None else self.tolerance

        # Векторизоване обчислення (NumPy BLAS — в 5-10x швидше ніж цикл)
        encoding_matrix = np.array([r.encoding for r in known_encodings])
        distances = np.linalg.norm(encoding_matrix - unknown_encoding, axis=1)

        # Поріг 1: відсіваємо за tolerance
        if np.min(distances) > tolerance:
            return None

        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        confidence = (1.0 - best_distance) * 100.0

        # Поріг 2: перевірка впевненості
        if confidence < self.min_confidence:
            return None

        record = known_encodings[best_idx]
        return MatchResult(
            person_id=record.person_id,
            person_name=record.person_name,
            confidence=round(confidence, 2),
            distance=round(best_distance, 4),
        )


# ─────────────────────────────── Liveness ────────────────────────────────────

@dataclass
class LivenessResult:
    score: float            # 0.0=підробка, 1.0=справжнє
    is_spoofing: bool
    blinks_detected: int = 0
    avg_ear: float = 0.0
    is_warming_up: bool = True   # True during first window — recognition blocked
    state: str = "IDLE"
    reason: str = ""
    allow_matching: bool = False
    is_in_cooldown: bool = False
    warmup_elapsed: float = 0.0
    warmup_remaining: float = 0.0
    cooldown_remaining: float = 0.0
    left_ear: Optional[float] = None
    right_ear: Optional[float] = None
    eyes_state: str = "unknown"
    frames_closed_count: int = 0
    frames_open_count: int = 0
    missing_landmarks_count: int = 0
    valid_eye_frames: int = 0
    smoothed_ear: float = 0.0
    open_eye_baseline: Optional[float] = None
    blink_down_threshold: Optional[float] = None
    blink_recovery_threshold: Optional[float] = None
    blink_debug_reason: str = ""
    blink_internal_state: str = "BASELINE_COLLECTING"
    baseline_buffer_size: int = 0
    baseline_required_frames: int = 0
    baseline_ready: bool = False
    baseline_state: str = "COLLECTING"
    min_ear_seen_during_warmup: Optional[float] = None
    max_ear_seen_during_warmup: Optional[float] = None
    previous_eyes_state: str = "unknown"
    drop_ratio: Optional[float] = None
    recovery_ratio: Optional[float] = None
    blink_event_detected_this_frame: bool = False
    blink_event_history: tuple[str, ...] = field(default_factory=tuple)
    last_blink_event_time: Optional[float] = None
    reason_code: str = ""


class LivenessDetector:
    """
    EAR (Eye Aspect Ratio) Blink Detection.

    EAR = (||p2-p6|| + ||p3-p5||) / (2 × ||p1-p4||)
    Відкрите: EAR ≈ 0.25-0.35
    Кліпання: EAR < 0.20

    Захищає від:
    - ~90% фото-атак
    - ~70% відео-атак без кліпання

    Вразливість: перше вікно (~3 с) — `is_warming_up=True`, розпізнавання заблоковано
    щоб запобігти атаці в перші кілька секунд до накопичення blink-статистики.
    """

    def __init__(
        self,
        ear_threshold: float = 0.20,
        *,
        warmup_seconds: float = 3.5,
        cooldown_seconds: float = 5.0,
        required_blinks: int = 1,
        min_closed_frames: int = 1,
        max_closed_frames: int = 8,
        min_open_frames_before_blink: int = 2,
        min_valid_ear_frames_for_baseline: int = 8,
        ear_relative_drop_ratio: float = 0.78,
        ear_recovery_ratio: float = 0.88,
        ear_smoothing_alpha: float = 0.40,
        max_missing_frames: int = 6,
        clock=None,
    ):
        self.EAR_THRESHOLD = ear_threshold
        self.WARMUP_SECONDS = warmup_seconds
        self.COOLDOWN_SECONDS = cooldown_seconds
        self.REQUIRED_BLINKS = required_blinks
        self.MIN_CLOSED_FRAMES = min_closed_frames
        self.MAX_CLOSED_FRAMES = max_closed_frames
        self.MIN_OPEN_FRAMES_BEFORE_BLINK = min_open_frames_before_blink
        self.MIN_VALID_EAR_FRAMES_FOR_BASELINE = min_valid_ear_frames_for_baseline
        self.EAR_RELATIVE_DROP_RATIO = ear_relative_drop_ratio
        self.EAR_RECOVERY_RATIO = ear_recovery_ratio
        self.EAR_SMOOTHING_ALPHA = ear_smoothing_alpha
        self.MAX_MISSING_FRAMES = max_missing_frames
        self._clock = clock or time.monotonic
        self._blink_count: int = 0
        self._frames_closed_count: int = 0
        self._frames_open_count: int = 0
        self._missing_landmarks_count: int = 0
        self._valid_eye_frames: int = 0
        self._phase: str = "WARMUP_LIVENESS"
        self._warmup_started_at: float = self._clock()
        self._cooldown_started_at: Optional[float] = None
        self._eyes_state: str = "unknown"
        self._previous_eyes_state: str = "unknown"
        self._smoothed_ear: Optional[float] = None
        self._baseline_samples: deque[float] = deque(maxlen=24)
        self._open_eye_baseline: Optional[float] = None
        self._open_frames_before_closure: int = 0
        self._last_blink_debug_reason: str = "awaiting eye baseline"
        self._min_ear_seen_during_warmup: Optional[float] = None
        self._max_ear_seen_during_warmup: Optional[float] = None
        self._blink_event_detected_this_frame: bool = False
        self._blink_event_history: deque[str] = deque(maxlen=8)
        self._last_blink_event_time: Optional[float] = None
        self._last_reason_code: str = "collecting_baseline"
        self._last_decision: Optional[LivenessResult] = None

    def _calculate_ear(self, eye_points: list) -> float:
        if len(eye_points) < 6:
            return 0.0
        p = np.array(eye_points, dtype=np.float64)
        v1 = np.linalg.norm(p[1] - p[5])
        v2 = np.linalg.norm(p[2] - p[4])
        h = np.linalg.norm(p[0] - p[3])
        if h < 1e-6:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    def _reset_for_new_cycle(self, now: Optional[float] = None) -> None:
        self._phase = "WARMUP_LIVENESS"
        self._warmup_started_at = self._clock() if now is None else now
        self._cooldown_started_at = None
        self._blink_count = 0
        self._frames_closed_count = 0
        self._frames_open_count = 0
        self._missing_landmarks_count = 0
        self._valid_eye_frames = 0
        self._eyes_state = "unknown"
        self._previous_eyes_state = "unknown"
        self._smoothed_ear = None
        self._baseline_samples.clear()
        self._open_eye_baseline = None
        self._open_frames_before_closure = 0
        self._last_blink_debug_reason = "awaiting eye baseline"
        self._min_ear_seen_during_warmup = None
        self._max_ear_seen_during_warmup = None
        self._blink_event_detected_this_frame = False
        self._blink_event_history.clear()
        self._last_blink_event_time = None
        self._last_reason_code = "collecting_baseline"

    def _is_valid_baseline_candidate(self, smoothed_ear: float) -> bool:
        return 0.08 <= smoothed_ear <= 0.60

    def _calculate_open_eye_baseline(self) -> Optional[float]:
        if len(self._baseline_samples) < self.MIN_VALID_EAR_FRAMES_FOR_BASELINE:
            return None
        sorted_samples = np.sort(np.array(self._baseline_samples, dtype=np.float64))
        open_eye_window = sorted_samples[len(sorted_samples) // 2:]
        if open_eye_window.size == 0:
            return None
        return float(np.median(open_eye_window))

    def _update_baseline(self, smoothed_ear: float) -> None:
        # Baseline collection must not depend on eye_state or configured blink threshold.
        if not self._is_valid_baseline_candidate(smoothed_ear):
            return
        self._baseline_samples.append(smoothed_ear)
        if len(self._baseline_samples) >= self.MIN_VALID_EAR_FRAMES_FOR_BASELINE:
            self._open_eye_baseline = self._calculate_open_eye_baseline()

    def _compute_thresholds(self) -> tuple[Optional[float], Optional[float]]:
        if self._open_eye_baseline is None:
            return None, None
        down_threshold = self._open_eye_baseline * self.EAR_RELATIVE_DROP_RATIO
        recovery_threshold = max(
            down_threshold + 0.015,
            self._open_eye_baseline * self.EAR_RECOVERY_RATIO,
        )
        return down_threshold, recovery_threshold

    def _baseline_state(self) -> str:
        if self._open_eye_baseline is not None:
            return "READY"
        if self._valid_eye_frames >= self.MIN_VALID_EAR_FRAMES_FOR_BASELINE:
            return "FAILED"
        return "COLLECTING"

    def _blink_internal_state(self) -> str:
        if self._blink_count >= self.REQUIRED_BLINKS:
            return "BLINK_PASSED"
        if self._open_eye_baseline is not None:
            return "BLINK_DETECTION_ACTIVE"
        return "BASELINE_COLLECTING"

    def _record_blink_event(self, event: str, now: float) -> None:
        self._blink_event_detected_this_frame = True
        self._last_blink_event_time = now
        self._blink_event_history.append(event)

    def _build_result(
        self,
        *,
        state: str,
        reason: str,
        score: float,
        is_spoofing: bool,
        is_warming_up: bool,
        allow_matching: bool,
        is_in_cooldown: bool,
        warmup_elapsed: float,
        warmup_remaining: float,
        cooldown_remaining: float,
        left_ear: Optional[float],
        right_ear: Optional[float],
        avg_ear: float,
        eyes_state: str,
        smoothed_ear: float = 0.0,
        open_eye_baseline: Optional[float] = None,
        blink_down_threshold: Optional[float] = None,
        blink_recovery_threshold: Optional[float] = None,
        blink_event_detected_this_frame: bool = False,
        reason_code: str = "",
    ) -> LivenessResult:
        return LivenessResult(
            score=score,
            is_spoofing=is_spoofing,
            blinks_detected=self._blink_count,
            avg_ear=avg_ear,
            is_warming_up=is_warming_up,
            state=state,
            reason=reason,
            allow_matching=allow_matching,
            is_in_cooldown=is_in_cooldown,
            warmup_elapsed=warmup_elapsed,
            warmup_remaining=warmup_remaining,
            cooldown_remaining=cooldown_remaining,
            left_ear=left_ear,
            right_ear=right_ear,
            eyes_state=eyes_state,
            frames_closed_count=self._frames_closed_count,
            frames_open_count=self._frames_open_count,
            missing_landmarks_count=self._missing_landmarks_count,
            valid_eye_frames=self._valid_eye_frames,
            smoothed_ear=smoothed_ear,
            open_eye_baseline=open_eye_baseline,
            blink_down_threshold=blink_down_threshold,
            blink_recovery_threshold=blink_recovery_threshold,
            blink_debug_reason=self._last_blink_debug_reason,
            blink_internal_state=self._blink_internal_state(),
            baseline_buffer_size=len(self._baseline_samples),
            baseline_required_frames=self.MIN_VALID_EAR_FRAMES_FOR_BASELINE,
            baseline_ready=self._open_eye_baseline is not None,
            baseline_state=self._baseline_state(),
            min_ear_seen_during_warmup=self._min_ear_seen_during_warmup,
            max_ear_seen_during_warmup=self._max_ear_seen_during_warmup,
            previous_eyes_state=self._previous_eyes_state,
            drop_ratio=self.EAR_RELATIVE_DROP_RATIO,
            recovery_ratio=self.EAR_RECOVERY_RATIO,
            blink_event_detected_this_frame=blink_event_detected_this_frame,
            blink_event_history=tuple(self._blink_event_history),
            last_blink_event_time=self._last_blink_event_time,
            reason_code=reason_code or self._last_reason_code,
        )

    def check(self, landmarks: Optional[dict]) -> LivenessResult:
        now = self._clock()
        self._blink_event_detected_this_frame = False
        prior_eyes_state = self._eyes_state
        left_eye = (landmarks or {}).get("left_eye", [])
        right_eye = (landmarks or {}).get("right_eye", [])
        has_valid_eyes = len(left_eye) >= 6 and len(right_eye) >= 6
        down_threshold, recovery_threshold = self._compute_thresholds()

        if self._phase == "COOLDOWN":
            cooldown_elapsed = now - (self._cooldown_started_at or now)
            cooldown_remaining = max(0.0, self.COOLDOWN_SECONDS - cooldown_elapsed)
            if cooldown_remaining > 0:
                previous = self._last_decision
                return self._build_result(
                    state="COOLDOWN",
                    reason=(previous.reason if previous else "cooldown"),
                    score=(previous.score if previous else 0.5),
                    is_spoofing=bool(previous and previous.is_spoofing),
                    is_warming_up=False,
                    allow_matching=False,
                    is_in_cooldown=True,
                    warmup_elapsed=0.0,
                    warmup_remaining=0.0,
                    cooldown_remaining=cooldown_remaining,
                    left_ear=previous.left_ear if previous else None,
                    right_ear=previous.right_ear if previous else None,
                    avg_ear=previous.avg_ear if previous else 0.0,
                    eyes_state="unknown",
                    smoothed_ear=previous.smoothed_ear if previous else 0.0,
                    open_eye_baseline=previous.open_eye_baseline if previous else None,
                    blink_down_threshold=previous.blink_down_threshold if previous else None,
                    blink_recovery_threshold=previous.blink_recovery_threshold if previous else None,
                    blink_event_detected_this_frame=False,
                    reason_code=previous.reason_code if previous else "cooldown_active",
                )
            self._reset_for_new_cycle(now=now)
            down_threshold, recovery_threshold = self._compute_thresholds()

        left_ear = self._calculate_ear(left_eye) if has_valid_eyes else None
        right_ear = self._calculate_ear(right_eye) if has_valid_eyes else None
        avg_ear = ((left_ear or 0.0) + (right_ear or 0.0)) / 2.0 if has_valid_eyes else 0.0

        if has_valid_eyes:
            self._valid_eye_frames += 1
            if self._smoothed_ear is None:
                self._smoothed_ear = avg_ear
            else:
                alpha = self.EAR_SMOOTHING_ALPHA
                self._smoothed_ear = (alpha * avg_ear) + ((1.0 - alpha) * self._smoothed_ear)

            smoothed_ear = self._smoothed_ear
            self._min_ear_seen_during_warmup = (
                smoothed_ear if self._min_ear_seen_during_warmup is None
                else min(self._min_ear_seen_during_warmup, smoothed_ear)
            )
            self._max_ear_seen_during_warmup = (
                smoothed_ear if self._max_ear_seen_during_warmup is None
                else max(self._max_ear_seen_during_warmup, smoothed_ear)
            )

            self._update_baseline(smoothed_ear)
            down_threshold, recovery_threshold = self._compute_thresholds()

            if self._open_eye_baseline is None:
                current_eyes_state = "baseline_collecting"
                if self._valid_eye_frames >= self.MIN_VALID_EAR_FRAMES_FOR_BASELINE:
                    self._last_reason_code = "baseline_not_initialized_bug"
                    self._last_blink_debug_reason = (
                        "valid EAR frames reached baseline requirement but baseline is still unavailable"
                    )
                else:
                    self._last_reason_code = "collecting_baseline"
                    self._last_blink_debug_reason = (
                        f"collecting baseline {len(self._baseline_samples)}/{self.MIN_VALID_EAR_FRAMES_FOR_BASELINE}"
                    )
            else:
                raw_supports_closed = avg_ear <= down_threshold
                raw_supports_open = avg_ear >= recovery_threshold

                if raw_supports_closed and smoothed_ear <= recovery_threshold:
                    current_eyes_state = "closed"
                elif raw_supports_open or smoothed_ear >= recovery_threshold:
                    current_eyes_state = "open"
                else:
                    current_eyes_state = prior_eyes_state if prior_eyes_state in {"open", "closed"} else "unknown"

                if prior_eyes_state in {"unknown", "baseline_collecting"}:
                    self._frames_open_count = (
                        max(1, self.MIN_OPEN_FRAMES_BEFORE_BLINK)
                        if current_eyes_state == "open"
                        else 0
                    )
                    self._frames_closed_count = 1 if current_eyes_state == "closed" else 0
                    self._last_reason_code = "watching_for_blink"
                    if current_eyes_state == "open":
                        self._last_blink_debug_reason = "baseline ready; eyes classified as open"
                    else:
                        self._last_blink_debug_reason = "baseline ready; eyes classified as closed"
                elif prior_eyes_state in {"open"}:
                    if current_eyes_state == "closed":
                        if self._frames_open_count >= self.MIN_OPEN_FRAMES_BEFORE_BLINK:
                            self._open_frames_before_closure = self._frames_open_count
                            self._frames_closed_count = 1
                            self._frames_open_count = 0
                            self._last_reason_code = "watching_for_blink"
                            self._last_blink_debug_reason = (
                                f"entered closed state at smoothed EAR {smoothed_ear:.3f}"
                            )
                        else:
                            self._last_reason_code = "watching_for_blink"
                            self._last_blink_debug_reason = (
                                f"ignored closed dip; only {self._frames_open_count} open frame(s) before closure"
                            )
                            current_eyes_state = "unknown"
                    elif current_eyes_state == "open":
                        self._frames_open_count += 1
                        self._last_reason_code = "watching_for_blink"
                        self._last_blink_debug_reason = "eyes open; baseline stable"
                    else:
                        self._last_reason_code = "watching_for_blink"
                        self._last_blink_debug_reason = "EAR between down/recovery thresholds; waiting"
                elif prior_eyes_state == "closed":
                    if current_eyes_state == "closed":
                        self._frames_closed_count += 1
                        self._last_reason_code = "watching_for_blink"
                        if self._frames_closed_count > self.MAX_CLOSED_FRAMES:
                            self._last_blink_debug_reason = (
                                f"closed state too long ({self._frames_closed_count} frames); will not count repeated blinks"
                            )
                        else:
                            self._last_blink_debug_reason = (
                                f"eyes remain closed for {self._frames_closed_count} frame(s)"
                            )
                    elif current_eyes_state == "open":
                        closed_frames = self._frames_closed_count
                        if (
                            closed_frames >= self.MIN_CLOSED_FRAMES
                            and closed_frames <= self.MAX_CLOSED_FRAMES
                            and self._open_frames_before_closure >= self.MIN_OPEN_FRAMES_BEFORE_BLINK
                        ):
                            self._blink_count += 1
                            event = (
                                f"open({self._open_frames_before_closure}) -> "
                                f"closed({closed_frames}) -> open"
                            )
                            self._record_blink_event(event, now)
                            self._last_reason_code = "blink_detected"
                            self._last_blink_debug_reason = f"counted blink: {event}"
                            logger.debug(
                                "Blink detected smoothed_ear=%.3f baseline=%.3f total=%d",
                                smoothed_ear,
                                self._open_eye_baseline or 0.0,
                                self._blink_count,
                            )
                        else:
                            self._last_reason_code = "watching_for_blink"
                            self._last_blink_debug_reason = (
                                f"did not count blink: open_before={self._open_frames_before_closure}, closed={closed_frames}"
                            )
                        self._frames_closed_count = 0
                        self._frames_open_count = 1
                    else:
                        self._last_reason_code = "watching_for_blink"
                        self._last_blink_debug_reason = "waiting for recovery threshold after closure"
        else:
            self._missing_landmarks_count += 1
            current_eyes_state = "unknown"
            smoothed_ear = self._smoothed_ear or 0.0
            self._last_reason_code = "missing_landmarks"
            self._last_blink_debug_reason = "eye landmarks missing; blink not evaluated"

        self._previous_eyes_state = prior_eyes_state
        self._eyes_state = current_eyes_state

        warmup_elapsed = now - self._warmup_started_at
        warmup_remaining = max(0.0, self.WARMUP_SECONDS - warmup_elapsed)
        if warmup_elapsed < self.WARMUP_SECONDS:
            return self._build_result(
                state="WARMING_UP",
                reason=self._last_blink_debug_reason,
                score=0.5,
                is_spoofing=False,
                is_warming_up=True,
                allow_matching=False,
                is_in_cooldown=False,
                warmup_elapsed=warmup_elapsed,
                warmup_remaining=warmup_remaining,
                cooldown_remaining=0.0,
                left_ear=left_ear,
                right_ear=right_ear,
                avg_ear=avg_ear,
                eyes_state=current_eyes_state,
                smoothed_ear=smoothed_ear,
                open_eye_baseline=self._open_eye_baseline,
                blink_down_threshold=down_threshold,
                blink_recovery_threshold=recovery_threshold,
                blink_event_detected_this_frame=self._blink_event_detected_this_frame,
                reason_code=self._last_reason_code,
            )

        if self._valid_eye_frames == 0:
            decision_state = "INSUFFICIENT_DATA"
            decision_reason = "no valid eye landmarks during warmup"
            self._last_reason_code = "no_valid_ear_frames"
            score = 0.0
            is_spoofing = False
            allow_matching = False
        elif (
            self._missing_landmarks_count > self.MAX_MISSING_FRAMES
            and self._blink_count == 0
            and self._open_eye_baseline is None
        ):
            decision_state = "INSUFFICIENT_DATA"
            decision_reason = "landmarks unstable during warmup"
            self._last_reason_code = "landmarks_unstable"
            score = 0.0
            is_spoofing = False
            allow_matching = False
        elif self._blink_count >= self.REQUIRED_BLINKS:
            decision_state = "LIVE"
            decision_reason = f"observed {self._blink_count} completed blink(s)"
            self._last_reason_code = "blink_requirement_met"
            score = 1.0
            is_spoofing = False
            allow_matching = True
        else:
            decision_state = "LIVENESS_FAILED"
            decision_reason = f"warmup ended with {self._blink_count} completed blink(s)"
            self._last_reason_code = "blink_requirement_not_met"
            score = 0.0
            is_spoofing = True
            allow_matching = False

        result = self._build_result(
            state=decision_state,
            reason=decision_reason,
            score=score,
            is_spoofing=is_spoofing,
            is_warming_up=False,
            allow_matching=allow_matching,
            is_in_cooldown=False,
            warmup_elapsed=warmup_elapsed,
            warmup_remaining=0.0,
            cooldown_remaining=0.0,
            left_ear=left_ear,
            right_ear=right_ear,
            avg_ear=avg_ear,
            eyes_state=current_eyes_state,
            smoothed_ear=smoothed_ear,
            open_eye_baseline=self._open_eye_baseline,
            blink_down_threshold=down_threshold,
            blink_recovery_threshold=recovery_threshold,
            blink_event_detected_this_frame=self._blink_event_detected_this_frame,
            reason_code=self._last_reason_code,
        )
        self._last_decision = result
        self._phase = "COOLDOWN"
        self._cooldown_started_at = now
        return result


# ─────────────────────────── Texture Anti-Spoofing ───────────────────────────

class TextureAntiSpoofing:
    """
    Текстурний аналіз обличчя для виявлення фото/відео-атак.

    Алгоритм: три незалежних сигнали → зважений score:

    1. LBP (Local Binary Patterns) entropy
       Справжнє обличчя: висока ентропія (~7.0-7.5 біт)
       Роздрукована фото: нижча ентропія (~5.5-6.5 біт) — менше унікальних мікроструктур

    2. Gradient variance (Sobel)
       Справжнє обличчя: висока дисперсія країв (~400-800)
       Фото на екрані: рівномірніші краї

    3. High-frequency energy ratio (FFT)
       Справжнє обличчя: плавний спад в частотній області
       Екран: переодичні піки (Муар-ефект); Друк: обрізані високі частоти

    Threshold: score < 0.25 → spoofing
    """

    def __init__(self, threshold: float = 0.25):
        self.threshold = threshold

    def analyze(self, face_bgr: np.ndarray, *, threshold: Optional[float] = None) -> TextureCheckResult:
        if face_bgr is None or face_bgr.size == 0:
            return TextureCheckResult(status="UNKNOWN", reason="empty_face_crop")

        # Нормалізуємо до 64×64 для стабільних метрик
        try:
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        except cv2.error:
            return TextureCheckResult(status="UNKNOWN", reason="grayscale_conversion_failed")
        gray = cv2.resize(gray, (64, 64))

        s1 = self._lbp_entropy(gray)
        s2 = self._gradient_variance(gray)
        s3 = self._frequency_ratio(gray)

        combined = s1 * 0.40 + s2 * 0.35 + s3 * 0.25
        score = round(float(np.clip(combined, 0.0, 1.0)), 3)
        effective_threshold = self.threshold if threshold is None else threshold
        status = "FAIL" if score < effective_threshold else "PASS"
        return TextureCheckResult(
            status=status,
            score=score,
            threshold=effective_threshold,
            reason="texture_check_failed" if status == "FAIL" else "texture_check_passed",
            lbp_score=round(s1, 3),
            sobel_score=round(s2, 3),
            fft_score=round(s3, 3),
        )

    def score(self, face_bgr: np.ndarray) -> float:
        """Returns 0.0 (spoofing) .. 1.0 (real face)."""
        result = self.analyze(face_bgr)
        return result.score if result.score is not None else 0.0

    def is_spoofing(self, face_bgr: np.ndarray) -> bool:
        return self.score(face_bgr) < self.threshold

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _lbp_entropy(gray: np.ndarray) -> float:
        """Vectorized LBP histogram entropy."""
        h, w = gray.shape
        padded = np.pad(gray, 1, mode="edge").astype(np.int32)
        center = padded[1:-1, 1:-1]
        lbp = np.zeros((h, w), dtype=np.uint8)

        # 8 neighbors clockwise
        offsets = [(-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1)]
        for bit, (dy, dx) in enumerate(offsets):
            neighbor = padded[1 + dy: 1 + dy + h, 1 + dx: 1 + dx + w]
            lbp |= (center >= neighbor).astype(np.uint8) * (1 << bit)

        hist, _ = np.histogram(lbp, bins=256, range=(0, 255))
        p = hist / (hist.sum() + 1e-9)
        entropy = float(-np.sum(p * np.log2(p + 1e-10)))
        # Max entropy ~8 bits; real faces typically 6.8-7.5
        return min(1.0, entropy / 7.5)

    @staticmethod
    def _gradient_variance(gray: np.ndarray) -> float:
        """Sobel gradient magnitude variance — real faces have more edge variety."""
        sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(sx ** 2 + sy ** 2)
        var = float(np.var(magnitude))
        # Normalize: 500 is typical for a sharp face portrait
        return min(1.0, var / 500.0)

    @staticmethod
    def _frequency_ratio(gray: np.ndarray) -> float:
        """
        Порівнює енергію у середніх і високих частотах.
        Реальні обличчя: плавний спад. Фото/екран: різкий обрив або переодичні піки.
        """
        f = np.fft.fft2(gray.astype(np.float32))
        fshift = np.fft.fftshift(f)
        magnitude = np.log(np.abs(fshift) + 1.0)

        h, w = magnitude.shape
        cy, cx = h // 2, w // 2
        y_idx, x_idx = np.ogrid[:h, :w]
        dist = np.sqrt((x_idx - cx) ** 2 + (y_idx - cy) ** 2)

        mid_mask = (dist >= 4) & (dist < 14)
        high_mask = dist >= 18

        mid_energy = float(magnitude[mid_mask].mean()) if mid_mask.any() else 1.0
        high_energy = float(magnitude[high_mask].mean()) if high_mask.any() else 0.0

        if mid_energy < 1e-6:
            return 0.5

        ratio = high_energy / mid_energy
        # Real faces ratio ≈ 0.45-0.75; flat photos ≈ 0.2-0.4; screens may spike
        return float(np.clip(ratio * 1.4, 0.0, 1.0))


# ─────────────────────────────── Face Tracker ────────────────────────────────

class FaceTracker:
    """
    IoU-based face tracker — підтримує стабільні track_id для кожного обличчя.

    Проблема яку вирішує: якщо у кадрі 2 особи і одна йде, індекси face_locations
    зсуваються. LivenessDetector[0] переходить до іншої людини → помилковий
    liveness-стан. FaceTracker прив'язує детектор до фізичного обличчя за позицією.

    Алгоритм: мінімальна евклідова відстань між центрами bbox-ів між кадрами.
    """

    MAX_CENTER_DIST = 0.25  # нормалізована (0-1) макс. відстань для match

    def __init__(self):
        self._next_id: int = 0
        # track_id → (norm_cy, norm_cx)
        self._tracks: dict[int, tuple[float, float]] = {}

    def clear(self) -> None:
        """Drop active tracks when frame has no faces."""
        self._tracks = {}

    def update(
        self,
        locations: list[tuple],
        frame_h: int,
        frame_w: int,
    ) -> list[int]:
        """
        Повертає список track_id тієї ж довжини що й locations.
        Нові обличчя отримують новий ID. Відомі — той самий що й у попередньому кадрі.
        """
        new_tracks: dict[int, tuple[float, float]] = {}
        used_existing: set[int] = set()
        result_ids: list[int] = []

        for loc in locations:
            top, right, bottom, left = loc
            cy = (top + bottom) / 2.0 / max(frame_h, 1)
            cx = (left + right) / 2.0 / max(frame_w, 1)

            # Пошук найближчого ще не використаного треку
            best_id: Optional[int] = None
            best_dist = self.MAX_CENTER_DIST

            for tid, (prev_cy, prev_cx) in self._tracks.items():
                if tid in used_existing:
                    continue
                dist = float(np.sqrt((cy - prev_cy) ** 2 + (cx - prev_cx) ** 2))
                if dist < best_dist:
                    best_dist = dist
                    best_id = tid

            if best_id is not None:
                used_existing.add(best_id)
                new_tracks[best_id] = (cy, cx)
                result_ids.append(best_id)
            else:
                new_id = self._next_id
                self._next_id += 1
                new_tracks[new_id] = (cy, cx)
                result_ids.append(new_id)

        self._tracks = new_tracks
        return result_ids


# ─────────────────────────────── FPS Tracker ─────────────────────────────────

class FPSTracker:
    def __init__(self, window: int = 30):
        self._times: deque = deque(maxlen=window)

    def tick(self):
        self._times.append(time.time())

    @property
    def current_fps(self) -> float:
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        if elapsed <= 0:
            return 0.0
        return round((len(self._times) - 1) / elapsed, 1)


# ─────────────────────────────── Helpers ─────────────────────────────────────

def _compute_quality_score(image: np.ndarray, location: tuple) -> float:
    """
    Laplacian variance sharpness score for the face crop.
    Returns 0.0 (blurry/small) … 1.0 (sharp).
    """
    top, right, bottom, left = location
    face_crop = image[top:bottom, left:right]
    if face_crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_crop, cv2.COLOR_RGB2GRAY) if len(face_crop.shape) == 3 else face_crop
    lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    # Normalize: 500 variance ≈ sharp portrait photo
    return round(min(1.0, lap_var / 500.0), 3)


# ──────────────────────────────── Pipeline ───────────────────────────────────

_LIVENESS_MAX_ENTRIES = 64  # LRU cap for liveness detector cache


class FaceRecognitionPipeline:
    """
    Головний ML Pipeline — singleton, ініціалізується при старті Django.

    Утримує в пам'яті:
    - Всі компоненти (detector, encoder, matcher, liveness, texture, tracker)
    - Кеш encodings з БД (_encoding_cache)

    Потокобезпека: _encoding_cache оновлюється атомарно через reload_encodings()

    Порядок перевірок у process_frame():
    ┌─────────────────────────────────────────────┐
    │ 1. CLAHE + resize                           │
    │ 2. Detect faces                             │
    │ 3. FaceTracker → stable track_ids           │
    │ 4. Landmarks (для liveness)                 │
    │ 5. Encode (128-dim)                         │
    │ Per face:                                   │
    │   6. TextureAntiSpoofing score              │
    │   7. LivenessDetector (EAR blink)           │
    │   8. Combined spoof decision:               │
    │      texture < threshold → spoofing         │
    │      liveness.is_spoofing → spoofing        │
    │      liveness.is_warming_up → block match   │
    │   9. FaceMatcher (only if not spoofing      │
    │      and not warming_up)                    │
    └─────────────────────────────────────────────┘
    """

    def __init__(self, settings: PipelineSettings):
        self.settings = settings
        self.preprocessor = ImagePreprocessor()
        self.detector = FaceDetector(model=settings.detector_model)
        self.encoder = FaceEncoder()
        self.matcher = FaceMatcher(
            tolerance=settings.tolerance,
            min_confidence=settings.min_confidence,
        )
        self._texture_detector = TextureAntiSpoofing(
            threshold=settings.texture_spoof_threshold
        )

        # LRU dict: key = "{camera_id}_{track_id}", max _LIVENESS_MAX_ENTRIES entries
        self._liveness_detectors: OrderedDict[str, LivenessDetector] = OrderedDict()
        self._liveness_last_centers: dict[str, tuple[float, float]] = {}
        self._liveness_last_seen: dict[str, float] = {}
        self._liveness_state_ttl_seconds: float = 6.0

        # Per-camera face trackers (stable track IDs across frames)
        self._face_trackers: dict[int, FaceTracker] = {}

        self._encoding_cache: list[EncodingRecord] = []
        self._cache_version: int = 0
        self._frame_count: int = 0

        logger.info(f"Pipeline ініціалізовано: {settings}")

    def process_frame(
        self,
        frame: np.ndarray,
        camera_id: int,
        *,
        tolerance: Optional[float] = None,
        scale: Optional[float] = None,
        strict_liveness: bool = True,
        texture_threshold: Optional[float] = None,
    ) -> FrameResult:
        """
        Повний цикл обробки одного кадру.

        Args:
            frame:     BGR numpy array (з OpenCV)
            camera_id: ID камери для ізоляції liveness/tracker state
            tolerance: per-camera confidence override (uses global default if None)
            scale:     per-camera resize scale override (uses global default if None)

        Returns:
            FrameResult з результатами для кожного знайденого обличчя
        """
        t_start = time.time()
        self._frame_count += 1

        effective_scale = scale if scale is not None else self.settings.frame_scale

        # 1. Препроцесинг + resize
        processed = self.preprocessor.process(frame)
        small = self.preprocessor.resize(processed, scale=effective_scale)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        # 2. Детекція
        face_locations_small = self.detector.detect(rgb_small)
        if not face_locations_small:
            tracker = self._face_trackers.get(camera_id)
            if tracker is not None:
                tracker.clear()
            self._cleanup_liveness_for_camera(camera_id, drop_all=True)
            return FrameResult(faces=[], frame_size=frame.shape[:2])

        # 3. FaceTracker → стабільні ID замість індексів
        if camera_id not in self._face_trackers:
            self._face_trackers[camera_id] = FaceTracker()
        track_ids = self._face_trackers[camera_id].update(
            face_locations_small, rgb_small.shape[0], rgb_small.shape[1]
        )

        # 4. Landmarks для liveness
        landmarks_list = face_recognition.face_landmarks(rgb_small, face_locations_small)

        # 5. Encoding
        encodings = self.encoder.encode(rgb_small, face_locations_small)

        # 6–9. Обробка кожного обличчя
        scale_inv = int(round(1.0 / effective_scale))
        faces = []

        for loc_small, encoding, landmarks, track_id in zip(
            face_locations_small, encodings, landmarks_list, track_ids
        ):
            # Масштабуємо координати назад до оригінального розміру
            top, right, bottom, left = [v * scale_inv for v in loc_small]
            frame_h, frame_w = frame.shape[:2]
            top = max(0, min(top, frame_h))
            bottom = max(0, min(bottom, frame_h))
            left = max(0, min(left, frame_w))
            right = max(0, min(right, frame_w))
            location = FaceLocation(top=top, right=right, bottom=bottom, left=left)

            # 6. Texture anti-spoofing (на кропі з повного кадру)
            texture_score = 1.0
            texture_is_spoof = False
            texture_result = TextureCheckResult(status="UNKNOWN", reason="texture_disabled")
            face_size_px = max(0, min(bottom - top, right - left))
            face_quality_score = _compute_quality_score(frame, (top, right, bottom, left))
            face_quality_result = FaceQualityCheckResult(
                status="PASS",
                reason="quality_ok",
                landmarks_found=bool(landmarks),
                missing_frames=0,
                face_confidence=0.0,
                quality_score=face_quality_score,
                face_size_px=face_size_px,
            )
            if self.settings.texture_enabled:
                # Texture cues are measured on raw BGR frame; CLAHE-enhanced frame can mask screen artifacts.
                face_crop = frame[top:bottom, left:right]
                effective_texture_threshold = (
                    texture_threshold if texture_threshold is not None
                    else self.settings.texture_spoof_threshold
                )
                if face_size_px < self.settings.texture_min_face_size_px:
                    texture_result = TextureCheckResult(
                        status="UNKNOWN",
                        threshold=effective_texture_threshold,
                        reason="face_crop_too_small_for_texture",
                    )
                    face_quality_result = FaceQualityCheckResult(
                        status="UNKNOWN",
                        reason="face_crop_too_small",
                        landmarks_found=bool(landmarks),
                        missing_frames=0,
                        face_confidence=0.0,
                        quality_score=face_quality_score,
                        face_size_px=face_size_px,
                    )
                elif face_quality_score < self.settings.texture_min_quality_score:
                    texture_result = TextureCheckResult(
                        status="UNKNOWN",
                        threshold=effective_texture_threshold,
                        reason="face_quality_too_low_for_texture",
                    )
                    face_quality_result = FaceQualityCheckResult(
                        status="UNKNOWN",
                        reason="blurred_or_low_quality_face_crop",
                        landmarks_found=bool(landmarks),
                        missing_frames=0,
                        face_confidence=0.0,
                        quality_score=face_quality_score,
                        face_size_px=face_size_px,
                    )
                else:
                    texture_result = self._texture_detector.analyze(
                        face_crop,
                        threshold=effective_texture_threshold,
                    )
                texture_score = texture_result.score if texture_result.score is not None else 0.0
                texture_is_spoof = texture_result.status == "FAIL"

            # 7. Liveness (EAR) — LRU cache з СТАБІЛЬНИМ ключем (track_id, не індексом)
            if self.settings.liveness_enabled:
                liveness_result = LivenessResult(score=0.5, is_spoofing=False, is_warming_up=True)
                liveness_key = f"{camera_id}_{track_id}"
                cy = (loc_small[0] + loc_small[2]) / 2.0 / max(rgb_small.shape[0], 1)
                cx = (loc_small[3] + loc_small[1]) / 2.0 / max(rgb_small.shape[1], 1)
                prev_center = self._liveness_last_centers.get(liveness_key)
                jumped = False
                if prev_center is not None:
                    dist = float(np.sqrt((cy - prev_center[0]) ** 2 + (cx - prev_center[1]) ** 2))
                    jumped = dist > 0.10
                if liveness_key not in self._liveness_detectors:
                    if len(self._liveness_detectors) >= _LIVENESS_MAX_ENTRIES:
                        old_key, _ = self._liveness_detectors.popitem(last=False)
                        self._liveness_last_centers.pop(old_key, None)
                    self._liveness_detectors[liveness_key] = LivenessDetector(
                        ear_threshold=self.settings.liveness_threshold,
                        warmup_seconds=self.settings.liveness_warmup_seconds,
                        cooldown_seconds=self.settings.liveness_cooldown_seconds,
                        required_blinks=self.settings.liveness_required_blinks,
                        min_closed_frames=self.settings.liveness_min_closed_frames,
                        max_closed_frames=self.settings.liveness_max_closed_frames,
                        min_open_frames_before_blink=self.settings.liveness_min_open_frames_before_blink,
                        min_valid_ear_frames_for_baseline=self.settings.liveness_min_valid_ear_frames_for_baseline,
                        ear_relative_drop_ratio=self.settings.liveness_ear_relative_drop_ratio,
                        ear_recovery_ratio=self.settings.liveness_ear_recovery_ratio,
                        ear_smoothing_alpha=self.settings.liveness_ear_smoothing_alpha,
                        max_missing_frames=self.settings.liveness_max_missing_frames,
                    )
                elif jumped:
                    # Track was reused for a different face position; reset liveness state to avoid leakage.
                    self._liveness_detectors[liveness_key] = LivenessDetector(
                        ear_threshold=self.settings.liveness_threshold,
                        warmup_seconds=self.settings.liveness_warmup_seconds,
                        cooldown_seconds=self.settings.liveness_cooldown_seconds,
                        required_blinks=self.settings.liveness_required_blinks,
                        min_closed_frames=self.settings.liveness_min_closed_frames,
                        max_closed_frames=self.settings.liveness_max_closed_frames,
                        min_open_frames_before_blink=self.settings.liveness_min_open_frames_before_blink,
                        min_valid_ear_frames_for_baseline=self.settings.liveness_min_valid_ear_frames_for_baseline,
                        ear_relative_drop_ratio=self.settings.liveness_ear_relative_drop_ratio,
                        ear_recovery_ratio=self.settings.liveness_ear_recovery_ratio,
                        ear_smoothing_alpha=self.settings.liveness_ear_smoothing_alpha,
                        max_missing_frames=self.settings.liveness_max_missing_frames,
                    )
                else:
                    self._liveness_detectors.move_to_end(liveness_key)
                self._liveness_last_centers[liveness_key] = (cy, cx)
                self._liveness_last_seen[liveness_key] = time.time()
                liveness_result = self._liveness_detectors[liveness_key].check(landmarks)
            else:
                liveness_result = LivenessResult(
                    score=1.0,
                    is_spoofing=False,
                    avg_ear=0.0,
                    is_warming_up=False,
                    state="LIVE",
                    reason="liveness disabled",
                    allow_matching=True,
                )
                face_quality_result.face_confidence = 1.0

            face_quality_result.missing_frames = liveness_result.missing_landmarks_count
            face_quality_result.face_confidence = 1.0

            # 8. Final verdict trace / aggregation
            if liveness_result.blinks_detected >= self.settings.liveness_required_blinks:
                blink_status = "PASS"
            elif liveness_result.is_warming_up and not liveness_result.baseline_ready:
                blink_status = "COLLECTING_BASELINE"
            elif liveness_result.is_warming_up and liveness_result.baseline_ready:
                blink_status = "WATCHING_FOR_BLINK"
            elif liveness_result.state == "LIVENESS_FAILED":
                blink_status = "FAIL"
            else:
                blink_status = "UNKNOWN"
            final_status = liveness_result.state
            final_reason_code = ""
            final_module_name = ""
            final_reason = liveness_result.reason
            is_warming_up = liveness_result.is_warming_up if strict_liveness else False
            is_in_cooldown = liveness_result.is_in_cooldown if strict_liveness else False
            is_spoofing = False

            if is_warming_up:
                final_status = "WARMING_UP"
                final_reason_code = "warmup_in_progress"
                final_module_name = "LivenessDetector"
                final_reason = liveness_result.reason
            elif is_in_cooldown:
                final_status = "COOLDOWN"
                final_reason_code = "cooldown_active"
                final_module_name = "LivenessDetector"
                final_reason = liveness_result.reason
            elif liveness_result.state == "INSUFFICIENT_DATA":
                final_status = "INSUFFICIENT_DATA"
                final_reason_code = "insufficient_data"
                final_module_name = "LivenessDetector"
                final_reason = liveness_result.reason
            elif blink_status == "FAIL":
                final_status = "LIVENESS_FAILED"
                final_reason_code = "blink_liveness_failed"
                final_module_name = "LivenessDetector"
                final_reason = liveness_result.reason
                is_spoofing = strict_liveness
            elif texture_result.status == "FAIL":
                final_status = "SPOOF"
                final_reason_code = "texture_check_failed"
                final_module_name = "TextureAntiSpoofing"
                final_reason = (
                    f"texture score {texture_score:.3f} below threshold {texture_result.threshold:.3f}"
                )
                is_spoofing = strict_liveness
            elif texture_result.status == "UNKNOWN":
                final_status = "INSUFFICIENT_DATA"
                final_reason_code = texture_result.reason or "texture_unknown"
                final_module_name = "TextureAntiSpoofing"
                final_reason = texture_result.reason
            elif blink_status == "PASS" and texture_result.status == "PASS":
                final_status = "LIVE"
                final_reason_code = "all_checks_passed"
                final_module_name = "DecisionAggregator"
                final_reason = "blink and texture checks passed"
            else:
                final_status = "INSUFFICIENT_DATA"
                final_reason_code = "verdict_inconclusive"
                final_module_name = "DecisionAggregator"
                final_reason = "insufficient diagnostic consensus"

            # 9. Matching — тільки якщо не спуфінг і не warmup
            match = None
            if (
                not is_spoofing
                and not is_warming_up
                and not is_in_cooldown
                and final_status == "LIVE"
                and liveness_result.allow_matching
            ):
                match = self.matcher.match(
                    encoding,
                    self._encoding_cache,
                    tolerance_override=tolerance,
                )

            checks_payload = {
                "blink_liveness": {
                    "status": blink_status,
                    "reason": liveness_result.reason,
                    "reason_code": liveness_result.reason_code,
                    "blink_count": liveness_result.blinks_detected,
                    "min_required": self.settings.liveness_required_blinks,
                    "internal_state": liveness_result.blink_internal_state,
                    "ear_baseline": round(liveness_result.open_eye_baseline, 4) if liveness_result.open_eye_baseline is not None else None,
                    "ear_current": round(liveness_result.avg_ear, 4),
                    "ear_smoothed": round(liveness_result.smoothed_ear, 4),
                    "down_threshold": round(liveness_result.blink_down_threshold, 4) if liveness_result.blink_down_threshold is not None else None,
                    "recovery_threshold": round(liveness_result.blink_recovery_threshold, 4) if liveness_result.blink_recovery_threshold is not None else None,
                    "drop_ratio": round(liveness_result.drop_ratio, 4) if liveness_result.drop_ratio is not None else None,
                    "recovery_ratio": round(liveness_result.recovery_ratio, 4) if liveness_result.recovery_ratio is not None else None,
                    "blink_debug_reason": liveness_result.blink_debug_reason,
                    "baseline_buffer_size": liveness_result.baseline_buffer_size,
                    "baseline_required_frames": liveness_result.baseline_required_frames,
                    "baseline_ready": liveness_result.baseline_ready,
                    "baseline_state": liveness_result.baseline_state,
                    "previous_eye_state": liveness_result.previous_eyes_state,
                    "blink_event_detected_this_frame": liveness_result.blink_event_detected_this_frame,
                    "blink_event_history": list(liveness_result.blink_event_history),
                    "last_blink_event_time": round(liveness_result.last_blink_event_time, 4) if liveness_result.last_blink_event_time is not None else None,
                    "min_ear_seen_during_warmup": round(liveness_result.min_ear_seen_during_warmup, 4) if liveness_result.min_ear_seen_during_warmup is not None else None,
                    "max_ear_seen_during_warmup": round(liveness_result.max_ear_seen_during_warmup, 4) if liveness_result.max_ear_seen_during_warmup is not None else None,
                },
                "texture_lbp": {
                    "status": texture_result.status,
                    "score": texture_result.lbp_score,
                    "threshold": None,
                    "reason": texture_result.reason,
                },
                "texture_sobel": {
                    "status": texture_result.status,
                    "score": texture_result.sobel_score,
                    "threshold": None,
                    "reason": texture_result.reason,
                },
                "texture_fft": {
                    "status": texture_result.status,
                    "score": texture_result.fft_score,
                    "threshold": None,
                    "reason": texture_result.reason,
                },
                "texture_combined": {
                    "status": texture_result.status,
                    "score": texture_result.score,
                    "threshold": texture_result.threshold,
                    "reason": texture_result.reason,
                },
                "face_quality": {
                    "status": face_quality_result.status,
                    "reason": face_quality_result.reason,
                    "landmarks_found": face_quality_result.landmarks_found,
                    "missing_frames": face_quality_result.missing_frames,
                    "face_confidence": face_quality_result.face_confidence,
                    "quality_score": round(face_quality_result.quality_score, 4),
                    "face_size_px": face_quality_result.face_size_px,
                },
            }

            debug_payload = {
                "track_id": track_id,
                "state": final_status,
                "reason": final_reason,
                "reason_code": liveness_result.reason_code,
                "final_reason_code": final_reason_code,
                "final_module_name": final_module_name,
                "debug_enabled": bool(self.settings.liveness_debug_overlay),
                "blink_detector_called": True,
                "landmarks_found": bool(landmarks),
                "warmup_elapsed": round(liveness_result.warmup_elapsed, 3),
                "warmup_remaining": round(liveness_result.warmup_remaining, 3),
                "cooldown_remaining": round(liveness_result.cooldown_remaining, 3),
                "blink_count": liveness_result.blinks_detected,
                "ear_left": round(liveness_result.left_ear, 4) if liveness_result.left_ear is not None else None,
                "ear_right": round(liveness_result.right_ear, 4) if liveness_result.right_ear is not None else None,
                "ear_avg": round(liveness_result.avg_ear, 4),
                "ear_smoothed": round(liveness_result.smoothed_ear, 4),
                "open_eye_baseline": round(liveness_result.open_eye_baseline, 4) if liveness_result.open_eye_baseline is not None else None,
                "blink_down_threshold": round(liveness_result.blink_down_threshold, 4) if liveness_result.blink_down_threshold is not None else None,
                "blink_recovery_threshold": round(liveness_result.blink_recovery_threshold, 4) if liveness_result.blink_recovery_threshold is not None else None,
                "eyes_state": liveness_result.eyes_state,
                "previous_eyes_state": liveness_result.previous_eyes_state,
                "blink_internal_state": liveness_result.blink_internal_state,
                "frames_closed_count": liveness_result.frames_closed_count,
                "frames_open_count": liveness_result.frames_open_count,
                "missing_landmarks_count": liveness_result.missing_landmarks_count,
                "valid_eye_frames": liveness_result.valid_eye_frames,
                "baseline_buffer_size": liveness_result.baseline_buffer_size,
                "baseline_required_frames": liveness_result.baseline_required_frames,
                "baseline_ready": liveness_result.baseline_ready,
                "baseline_state": liveness_result.baseline_state,
                "min_ear_seen_during_warmup": round(liveness_result.min_ear_seen_during_warmup, 4) if liveness_result.min_ear_seen_during_warmup is not None else None,
                "max_ear_seen_during_warmup": round(liveness_result.max_ear_seen_during_warmup, 4) if liveness_result.max_ear_seen_during_warmup is not None else None,
                "drop_ratio": round(liveness_result.drop_ratio, 4) if liveness_result.drop_ratio is not None else None,
                "recovery_ratio": round(liveness_result.recovery_ratio, 4) if liveness_result.recovery_ratio is not None else None,
                "blink_event_detected_this_frame": liveness_result.blink_event_detected_this_frame,
                "blink_event_history": list(liveness_result.blink_event_history),
                "last_blink_event_time": round(liveness_result.last_blink_event_time, 4) if liveness_result.last_blink_event_time is not None else None,
                "blink_debug_reason": liveness_result.blink_debug_reason,
                "texture_score": texture_score,
                "texture_is_spoof": texture_is_spoof,
                "texture_status": texture_result.status,
                "texture_reason": texture_result.reason,
                "face_quality_status": face_quality_result.status,
                "final_is_spoofing": is_spoofing,
                "checks": checks_payload,
            }
            if final_status == "WARMING_UP":
                logger.debug(
                    "[LIVENESS_BASELINE_DEBUG] track_id=%s state=%s blink_internal_state=%s ear_avg=%s smoothed_ear=%s valid_ear_frames=%s baseline_buffer_size=%s baseline_required_frames=%s baseline_ready=%s baseline=%s drop_ratio=%s recovery_ratio=%s computed_down_threshold=%s computed_recovery_threshold=%s eye_state=%s previous_eye_state=%s closed_frames=%s open_frames=%s blink_count=%s min_ear_seen_during_warmup=%s max_ear_seen_during_warmup=%s reason=%s",
                    track_id,
                    final_status,
                    debug_payload["blink_internal_state"],
                    debug_payload["ear_avg"],
                    debug_payload["ear_smoothed"],
                    debug_payload["valid_eye_frames"],
                    debug_payload["baseline_buffer_size"],
                    debug_payload["baseline_required_frames"],
                    debug_payload["baseline_ready"],
                    debug_payload["open_eye_baseline"],
                    debug_payload["drop_ratio"],
                    debug_payload["recovery_ratio"],
                    debug_payload["blink_down_threshold"],
                    debug_payload["blink_recovery_threshold"],
                    debug_payload["eyes_state"],
                    debug_payload["previous_eyes_state"],
                    debug_payload["frames_closed_count"],
                    debug_payload["frames_open_count"],
                    debug_payload["blink_count"],
                    debug_payload["min_ear_seen_during_warmup"],
                    debug_payload["max_ear_seen_during_warmup"],
                    debug_payload["reason_code"],
                )
            logger.debug(
                "[ANTI_SPOOF_TRACE] track=%s final=%s reason_code=%s module=%s checks=%s",
                liveness_key if self.settings.liveness_enabled else track_id,
                final_status,
                final_reason_code,
                final_module_name,
                checks_payload,
            )
            if self.settings.liveness_debug_overlay:
                logger.debug(
                    "[LIVENESS_DEBUG] track_id=%s state=%s blink_count=%s min_blinks_required=%s eye_state=%s previous_eye_state=%s ear_avg=%.4f baseline=%s drop_ratio=%s recovery_ratio=%s down_threshold=%s recovery_threshold=%s baseline_state=%s blink_status=%s texture_status=%s face_quality_status=%s final_status=%s final_reason_code=%s final_module_name=%s",
                    track_id,
                    liveness_result.state,
                    liveness_result.blinks_detected,
                    self.settings.liveness_required_blinks,
                    liveness_result.eyes_state,
                    liveness_result.previous_eyes_state,
                    liveness_result.avg_ear,
                    f"{liveness_result.open_eye_baseline:.4f}" if liveness_result.open_eye_baseline is not None else "None",
                    f"{liveness_result.drop_ratio:.4f}" if liveness_result.drop_ratio is not None else "None",
                    f"{liveness_result.recovery_ratio:.4f}" if liveness_result.recovery_ratio is not None else "None",
                    f"{liveness_result.blink_down_threshold:.4f}" if liveness_result.blink_down_threshold is not None else "None",
                    f"{liveness_result.blink_recovery_threshold:.4f}" if liveness_result.blink_recovery_threshold is not None else "None",
                    liveness_result.baseline_state,
                    blink_status,
                    texture_result.status,
                    face_quality_result.status,
                    final_status,
                    final_reason_code,
                    final_module_name,
                )

            face = FaceResult(
                location=location,
                person_id=match.person_id if match else None,
                person_name=match.person_name if match else None,
                confidence=match.confidence if match else 0.0,
                distance=match.distance if match else None,
                liveness_score=liveness_result.score,
                is_spoofing=is_spoofing,
                texture_is_spoof=texture_is_spoof,
                liveness_is_spoofing=liveness_result.is_spoofing if strict_liveness else False,
                is_warming_up=is_warming_up,
                texture_score=texture_score,
                track_id=track_id,
                landmarks={k: [(x * scale_inv, y * scale_inv) for x, y in v]
                           for k, v in landmarks.items()},
                liveness_state=final_status,
                liveness_reason=final_reason,
                is_in_cooldown=is_in_cooldown,
                debug=debug_payload,
                final_reason_code=final_reason_code,
                final_module_name=final_module_name,
            )
            faces.append(face)

        self._cleanup_liveness_for_camera(
            camera_id,
            active_track_ids=set(track_ids),
            now=time.time(),
        )

        processing_ms = (time.time() - t_start) * 1000

        return FrameResult(
            faces=faces,
            frame_size=frame.shape[:2],
            processing_ms=round(processing_ms, 2),
        )

    def _cleanup_liveness_for_camera(
        self,
        camera_id: int,
        *,
        active_track_ids: Optional[set[int]] = None,
        drop_all: bool = False,
        now: Optional[float] = None,
    ) -> None:
        prefix = f"{camera_id}_"
        keys = [k for k in list(self._liveness_detectors.keys()) if k.startswith(prefix)]
        if not keys:
            return

        if drop_all:
            for key in keys:
                self._liveness_detectors.pop(key, None)
                self._liveness_last_centers.pop(key, None)
                self._liveness_last_seen.pop(key, None)
            return

        if active_track_ids is None:
            return

        ts = now if now is not None else time.time()
        active_keys = {f"{camera_id}_{track_id}" for track_id in active_track_ids}
        for key in keys:
            if key in active_keys:
                continue
            last_seen = self._liveness_last_seen.get(key, 0.0)
            if (ts - last_seen) > self._liveness_state_ttl_seconds:
                self._liveness_detectors.pop(key, None)
                self._liveness_last_centers.pop(key, None)
                self._liveness_last_seen.pop(key, None)

    def empty_result(self, frame: np.ndarray) -> FrameResult:
        """Return a no-faces result (used when recognition is disabled)."""
        return FrameResult(faces=[], frame_size=frame.shape[:2], processing_ms=0.0)

    def reload_encodings(self):
        """
        Перезавантажує encodings з БД.
        Викликати після реєстрації нової особи або зміни фото.
        """
        try:
            from apps.persons.services import load_all_encodings
            new_cache = load_all_encodings()
            self._encoding_cache = new_cache
            self._cache_version += 1
            logger.info(
                f"Encodings перезавантажено: {len(new_cache)} записів "
                f"(version={self._cache_version})"
            )
        except Exception as e:
            logger.error(f"Помилка при завантаженні encodings: {e}")

    @property
    def cache_size(self) -> int:
        return len(self._encoding_cache)

    @property
    def cache_version(self) -> int:
        return self._cache_version
