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
from dataclasses import dataclass
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
    frame_scale: float = 0.25
    texture_spoof_threshold: float = 0.25   # below this → texture spoofing detected
    texture_enabled: bool = True


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


class LivenessDetector:
    """
    EAR (Eye Aspect Ratio) Blink Detection.

    EAR = (||p2-p6|| + ||p3-p5||) / (2 × ||p1-p4||)
    Відкрите: EAR ≈ 0.25-0.35
    Кліпання: EAR < 0.20

    Захищає від:
    - ~90% фото-атак
    - ~70% відео-атак без кліпання

    Вразливість: перше вікно (3 с) — `is_warming_up=True`, розпізнавання заблоковано
    щоб запобігти атаці в перші кілька секунд до накопичення blink-статистики.
    """

    CONSECUTIVE_FRAMES = 2
    REQUIRED_BLINKS = 1
    WINDOW_SECONDS = 4.0
    MAX_FAILED_WINDOWS = 1

    def __init__(self, ear_threshold: float = 0.20):
        self.EAR_THRESHOLD = ear_threshold
        self._blink_count: int = 0
        self._consecutive_below: int = 0
        self._failed_windows: int = 0
        self._window_start: float = time.time()
        self._window_completed: bool = False   # True after first full window
        self._last_result: Optional[LivenessResult] = None

    def _calculate_ear(self, eye_points: list) -> float:
        p = np.array(eye_points, dtype=np.float64)
        v1 = np.linalg.norm(p[1] - p[5])
        v2 = np.linalg.norm(p[2] - p[4])
        h = np.linalg.norm(p[0] - p[3])
        if h < 1e-6:
            return 0.0
        return (v1 + v2) / (2.0 * h)

    def check(self, landmarks: dict) -> LivenessResult:
        left_ear = self._calculate_ear(landmarks.get("left_eye", []))
        right_ear = self._calculate_ear(landmarks.get("right_eye", []))
        avg_ear = (left_ear + right_ear) / 2.0

        # Детекція кліпання
        if avg_ear < self.EAR_THRESHOLD:
            self._consecutive_below += 1
        else:
            if self._consecutive_below >= self.CONSECUTIVE_FRAMES:
                self._blink_count += 1
                logger.debug(f"Blink detected (EAR={avg_ear:.3f}, total={self._blink_count})")
            self._consecutive_below = 0

        # Перевірка вікна
        now = time.time()
        if (now - self._window_start) >= self.WINDOW_SECONDS:
            is_alive = self._blink_count >= self.REQUIRED_BLINKS
            if is_alive:
                self._failed_windows = 0
            else:
                self._failed_windows += 1
            # Allow one failed window to reduce false positives for real users who blink less often.
            is_spoofing = self._failed_windows > self.MAX_FAILED_WINDOWS
            score = 1.0 if not is_spoofing else 0.0
            self._window_completed = True

            self._last_result = LivenessResult(
                score=score,
                is_spoofing=is_spoofing,
                blinks_detected=self._blink_count,
                avg_ear=avg_ear,
                is_warming_up=False,
            )

            # Reset вікна
            self._blink_count = 0
            self._window_start = now
            return self._last_result

        # Вікно ще не завершено
        if self._last_result:
            # Повертаємо останній результат, але is_warming_up=False (вже є досвід)
            return LivenessResult(
                score=self._last_result.score,
                is_spoofing=self._last_result.is_spoofing,
                blinks_detected=self._last_result.blinks_detected,
                avg_ear=avg_ear,
                is_warming_up=False,
            )

        # Перше вікно ще не завершено — блокуємо розпізнавання
        return LivenessResult(score=0.5, is_spoofing=False, avg_ear=avg_ear, is_warming_up=True)


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

    def score(self, face_bgr: np.ndarray) -> float:
        """Returns 0.0 (spoofing) .. 1.0 (real face)."""
        if face_bgr is None or face_bgr.size == 0:
            return 0.0

        # Нормалізуємо до 64×64 для стабільних метрик
        try:
            gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        except cv2.error:
            return 0.0
        gray = cv2.resize(gray, (64, 64))

        s1 = self._lbp_entropy(gray)
        s2 = self._gradient_variance(gray)
        s3 = self._frequency_ratio(gray)

        combined = s1 * 0.40 + s2 * 0.35 + s3 * 0.25
        return round(float(np.clip(combined, 0.0, 1.0)), 3)

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
            if self.settings.texture_enabled:
                # Texture cues are measured on raw BGR frame; CLAHE-enhanced frame can mask screen artifacts.
                face_crop = frame[top:bottom, left:right]
                texture_score = self._texture_detector.score(face_crop)
                effective_texture_threshold = (
                    texture_threshold if texture_threshold is not None
                    else self.settings.texture_spoof_threshold
                )
                texture_is_spoof = texture_score < effective_texture_threshold

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
                        ear_threshold=self.settings.liveness_threshold
                    )
                elif jumped:
                    # Track was reused for a different face position; reset liveness state to avoid leakage.
                    self._liveness_detectors[liveness_key] = LivenessDetector(
                        ear_threshold=self.settings.liveness_threshold
                    )
                else:
                    self._liveness_detectors.move_to_end(liveness_key)
                self._liveness_last_centers[liveness_key] = (cy, cx)
                self._liveness_last_seen[liveness_key] = time.time()
                liveness_result = self._liveness_detectors[liveness_key].check(landmarks)
            else:
                liveness_result = LivenessResult(score=1.0, is_spoofing=False, is_warming_up=False)

            # 8. Фінальне рішення щодо спуфінгу
            #    Текстура АБО EAR → спуфінг
            is_spoofing = texture_is_spoof or (strict_liveness and liveness_result.is_spoofing)
            is_warming_up = liveness_result.is_warming_up if strict_liveness else False

            # 9. Matching — тільки якщо не спуфінг і не warmup
            match = None
            if not is_spoofing and not is_warming_up:
                match = self.matcher.match(
                    encoding,
                    self._encoding_cache,
                    tolerance_override=tolerance,
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
