# FaceGuard — ML Pipeline

> `ml/pipeline.py` — головний ML-конвеєр системи розпізнавання облич. Singleton, ініціалізується при старті Django (`apps.recognition.apps.ready()`).

---

## 📁 Структура

```
ml/
└── pipeline.py          # Єдиний файл — повний ML Pipeline
```

---

## 🧠 Компоненти Pipeline

### 1. `ImagePreprocessor`
- **CLAHE** (Contrast Limited Adaptive Histogram Equalization) — покращує зображення при слабкому освітленні.
- **Resize** — масштабування для прискорення обробки (frame_scale = 0.25).

### 2. `FaceDetector`
- Моделі: `hog` (швидко, CPU) або `cnn` (точніше, потребує GPU/RAM).
- Використовує `face_recognition.face_locations()`.

### 3. `FaceEncoder`
- Генерує **128-вимірні вектори** через ResNet-29 (dlib).
- `encode_photo()` — для реєстрації (перевірка: рівно одне обличчя).
- `encode_from_location()` — для швидкого кодування з відомим location (оптимізація для Celery tasks).

### 4. `FaceMatcher`
- **Двоступенева фільтрація:**
  1. Евклідова відстань < tolerance (0.55)
  2. Confidence = (1 − distance) × 100 > min_confidence (45%)
- Векторизоване обчислення (NumPy BLAS — в 5–10× швидше за цикл).

### 5. `LivenessDetector`
- **EAR (Eye Aspect Ratio) Blink Detection** — детекція кліпання очей.
- Захищає від ~90% фото-атак та ~70% відео-атак без кліпання.
- **Warming-up** — перше вікно (4 сек) розпізнавання заблоковано, поки не накопичиться статистика.

### 6. `TextureAntiSpoofing`
- **Три незалежні сигнали:**
  1. LBP entropy — реальне обличчя має вищу ентропію.
  2. Sobel gradient variance — справжні обличчя мають різноманітніші краї.
  3. FFT frequency ratio — реальні обличчя мають плавний спад частот.
- Threshold: score < 0.25 → spoofing.

### 7. `FaceTracker`
- Distance-based трекер — стабільні `track_id` для кожного фізичного обличчя.
- Розв'язує проблему зміщення індексів, коли одне обличчя зникає з кадру.
- Алгоритм: мінімальна евклідова відстань між центрами bbox між кадрами.

### 8. `FPSTracker`
- Sliding window FPS (останні 30 кадрів).

---

## 🔧 Головний клас: `FaceRecognitionPipeline`

### Singleton
Створюється один раз при старті Django:
```python
from apps.recognition.state import get_pipeline
pipeline = get_pipeline()
```

### Порядок обробки кадру (`process_frame()`)

```
1. CLAHE + resize
2. Detect faces (HOG/CNN)
3. FaceTracker → stable track_ids
4. Landmarks (68 точок) для liveness
5. Encode → 128-dim vectors
6. TextureAntiSpoofing score (per face)
7. LivenessDetector (EAR blink)
8. Combined spoof decision:
   texture < threshold → spoofing
   liveness.is_spoofing → spoofing
   liveness.is_warming_up → block match
9. FaceMatcher (only if not spoofing & not warming_up)
```

### Повернення: `FrameResult`
```python
@dataclass
class FrameResult:
    faces: list[FaceResult]       # Результати для кожного обличчя
    frame_size: tuple             # (width, height)
    processing_ms: float            # Час обробки в мс
```

### `FaceResult` поля
- `location` — bbox (top, right, bottom, left)
- `person_id`, `person_name` — якщо розпізнано
- `confidence` — впевненість у %
- `distance` — евклідова відстань
- `is_spoofing`, `texture_is_spoof`, `liveness_is_spoofing`
- `liveness_score`, `texture_score`
- `is_warming_up` — чи ще триває warming-up
- `track_id` — стабільний ID для трекінгу
- `landmarks` — 68 точок (scaled)

---

## 🔄 Кешування encodings

- `reload_encodings()` — перезавантажує всі active encodings з БД у пам'ять.
- Викликається:
  - При старті Django
  - Після реєстрації / оновлення / деактивації особи
  - Після видалення (anonymize)

---

## ⚙️ Налаштування

Через `.env` (зчитується в `faceguard.settings.base`):

```env
FACE_DETECTOR_MODEL=hog         # hog або cnn
FACE_TOLERANCE=0.55             # поріг відстані
MIN_CONFIDENCE=45.0              # мін. confidence %
LIVENESS_ENABLED=True            # увімкнути liveness
LIVENESS_THRESHOLD=0.20          # EAR threshold
```

---

## 📊 Метрики

При `tolerance=0.55`, `min_confidence=45`:

| Метрика | Значення |
|---------|----------|
| FAR | 4.3% |
| FRR | 3.8% |
| Accuracy | 96.0% |

---

## 🧪 Експерименти

Див. [`experiments/README.md`](../experiments/README.md) — 4 експерименти, що підтверджують роботу pipeline:
1. Верифікація (гістограма відстаней)
2. FAR/FRR/Accuracy sweep
3. Шифрування біометрії (Fernet)
4. Схема pipeline

---

## 📝 Примітки

- `pipeline.py` — єдиний файл ML. Усі компоненти в одному місці для простоти обслуговування.
- Потокобезпека: `_encoding_cache` оновлюється атомарно через `reload_encodings()`.
- LRU cache для liveness detectors (max 64 entries) — уникає витоку пам'яті при зміні камер.
