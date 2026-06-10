# FaceGuard — Workers (Celery + Camera Workers)

> Асинхронні задачі та обробники відео-потоків. Запускаються через Celery + Celery Beat.

---

## 📁 Структура

```
workers/
├── tasks.py             # Celery shared tasks
└── camera_worker.py     # Async camera worker (OpenCV + WebSocket)
```

---

## 🧠 Celery Tasks (`tasks.py`)

### `validate_and_encode_photos(person_id)`
- **Валідація фото** — перевіряє, що на кожному фото рівно одне обличчя.
- Зберігає `face_location` в `landmarks_json` для оптимізації.
- **Генерація encodings** — викликає `train_person_encodings()`.
- Запускається автоматично після завантаження фото в `PersonViewSet.photos()`.
- Respects GDPR: пропускає, якщо `consent_given=False` або `deletion_requested=True`.

### `train_person_task(person_id)`
- Ре-тренування encodings для конкретної особи (викликається з API endpoint `POST /persons/{id}/train/`).
- Retry: max 3 attempts, delay 10s.

### `generate_report(report_id)`
- Асинхронна генерація звіту (PDF / Excel / CSV).
- Змінює статус на `generating` → `ready` / `failed`.
- Використовує `ReportGeneratorFactory` з `apps.reports.generators`.

### `compute_daily_stats()`
- **Celery Beat task** — запускається щодня о 00:05.
- Агрегує події за вчора: total, recognized, unknown, spoofing, unique_persons.
- Зберігає в `DailyStats`.

### `cleanup_old_media(days=90)`
- **Celery Beat task** — запускається щодня о 03:00.
- Видаляє старі `frame_snapshot` та `face_crop` для подій старше 90 днів.

### `start_camera_worker_task(camera_id)`
- **Long-running Celery task** — запускає `CameraWorker` для конкретної камери.
- Реєструє `task_id` в Redis, щоб watchdog міг перевірити стан.

### `watchdog_camera_workers()`
- **Celery Beat task** — запускається кожні 60 секунд.
- Перевіряє, що для кожної активної камери `last_ping` < 90 секунд.
- Якщо worker мертвий — перезапускає `start_camera_worker_task`.

---

## 📷 Camera Worker (`camera_worker.py`)

### `CameraWorker`
Асинхронний процес для обробки однієї камери.

**Архітектура:**
```
CameraWorker
├── OpenCV VideoCapture (RTSP / USB / IP)
├── FaceRecognitionPipeline (ML singleton)
├── EventService (зберігає події в БД)
└── ChannelLayer (WebSocket broadcast)
```

**Логіка циклу:**
1. Відкриває потік (`cv2.VideoCapture`).
2. Читає кадри з `frame_skip` (пропуск кадрів для продуктивності).
3. Якщо `recognition_enabled=True` — запускає ML pipeline.
4. Зберігає події в БД через `EventService.create_events_from_result()`.
5. Бродкастить кадр + faces в WebSocket (`camera_{id}` група).
6. Оновлює `last_ping` в БД та Redis кожні 30 секунд (heartbeat).
7. Зупиняється за `stop_flag` в Redis або при помилці.

**Повідомлення WebSocket:**
```json
{
  "type": "frame",
  "camera_id": 1,
  "frame": "data:image/jpeg;base64,...",
  "faces": [...],
  "fps": 24.5,
  "processing_ms": 42.3
}
```

---

## 🕐 Celery Beat Schedule

Визначено в `faceguard.settings.base.CELERY_BEAT_SCHEDULE`:

| Задача | Розклад | Опис |
|--------|---------|------|
| `compute_daily_stats` | 00:05 щодня | Денна статистика |
| `cleanup_old_media` | 03:00 щодня | Очищення старих медіа |
| `watchdog_camera_workers` | кожні 60 сек | Моніторинг camera workers |

---

## 🚀 Запуск

```bash
# Всередині Docker (через docker-compose.yml)
# celery сервіс: 4 concurrent workers, черги default,cameras,reports
# celery-beat сервіс: scheduler з DatabaseScheduler

# Локально
make dev-celery
# або
celery -A faceguard worker -l info

# Beat локально
celery -A faceguard beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## 📝 Примітки

- Усі Celery tasks викликають `close_old_connections()` для уникнення витоку DB connections.
- `CameraWorker` — це **asyncio** цикл всередині Celery task.
- `frame_skip` налаштовується в моделі `Camera` (наприклад, 2 = обробляємо кожен 2-й кадр).
- Розпізнавання можна вимкнути для камери (`recognition_enabled=False`) — тоді просто бродкаст сирого відео.
