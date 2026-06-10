# 🛡️ FaceGuard — Система розпізнавання облич для СКУД

> **Django + React + ML** — повнофункціональна система контролю доступу (СКУД) з біометричною ідентифікацією, анти-спуфінгом, живістю (liveness) та GDPR-compliant шифруванням біометричних даних.

---

## 🔥 Основні можливості

| Функція | Опис |
|---------|------|
| **Розпізнавання облич** | 128-вимірні вектори (dlib ResNet-29) з точністю ~96% |
| **Анти-спуфінг** | Двоступенева перевірка: LBP/FFT/Sobel текстурний аналіз + EAR blink detection |
| **Liveness (живість)** | Детекція кліпання очей для захисту від фото/відео-атак |
| **Real-time відео** | WebSocket трансляція з камер + ML-обробка в реальному часі |
| **GDPR** | Шифрування біометрії (Fernet AES-128-CBC + HMAC-SHA256), право на забуття |
| **Звіти** | PDF / Excel / CSV згенеровані асинхронно через Celery |
| **Масштабування** | Celery workers + PostgreSQL + Redis + Nginx |
| **REST API** | JWT-авторизація, rate limiting, фільтрація, пагінація |

---

## 🏗️ Архітектура

```
┌─────────────────────────────────────────────────────────────┐
│  Nginx (порт 80)                                            │
│  ├── /          → React SPA (frontend/dist)                 │
│  ├── /api/      → Django REST API (порт 8000)               │
│  ├── /ws/       → Django Channels (WebSocket)               │
│  └── /media/    → Django media files                        │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐       ┌──────────┐       ┌─────────────┐
   │  React  │       │  Django  │       │ Celery      │
   │  (Vite) │       │  (Daphne)│       │ Worker      │
   │  5173   │       │  8000    │       │ + Beat      │
   └─────────┘       └──────────┘       └─────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐       ┌──────────┐       ┌─────────────┐
   │PostgreSQL│       │  Redis   │       │  ML Pipeline │
   │  5432   │       │  6379    │       │  (dlib/CV)   │
   └─────────┘       └──────────┘       └─────────────┘
```

---

## 📁 Структура проєкту

```
faceguard/
├── apps/                    # Django applications
│   ├── core/                # Користувачі, системні налаштування, health-check
│   ├── persons/             # Особи, фото, FaceEncoding, GDPR anonymize
│   ├── cameras/             # Камери, RTSP/USB streams, налаштування
│   ├── events/              # RecognitionEvent, DailyStats, snapshots
│   ├── recognition/         # ML pipeline singleton (state.py)
│   ├── reports/             # PDF/Excel/CSV генератори
│   ├── security/            # SpoofingAttempt, AuditLog
│   └── streaming/           # WebSocket consumers (камери + веб-камера)
├── faceguard/               # Django project settings
│   ├── settings/            # base.py, development.py, production.py
│   ├── urls.py              # Головний роутер
│   ├── asgi.py              # ASGI + Channels
│   ├── celery.py            # Celery app config
│   └── api_urls.py          # API v1 роутер
├── ml/                      # ML Pipeline
│   └── pipeline.py          # FaceRecognitionPipeline, Detector, Encoder, Matcher, Liveness, TextureAntiSpoofing, FaceTracker
├── workers/                 # Celery tasks
│   ├── tasks.py             # validate_and_encode_photos, train_person_task, generate_report, compute_daily_stats, cleanup_old_media, camera workers
│   └── camera_worker.py     # Async camera worker (OpenCV + WS broadcast)
├── frontend/                # React 19 + TypeScript + Vite + Tailwind CSS
│   ├── src/                 # Компоненти, сторінки, API client
│   ├── Dockerfile           # Multi-stage build (Node → nginx)
│   └── nginx.conf           # Конфіг nginx для SPA
├── experiments/             # 4 експерименти для дипломної роботи
│   ├── exp_01_distances.py  # Верифікація: гістограма відстаней
│   ├── exp_02_metrics.py    # FAR / FRR / Accuracy
│   ├── exp_03_encryption.py # Шифрування біометрії (Fernet)
│   ├── exp_04_pipeline.py   # Схема pipeline системи
│   ├── run.sh               # Запуск всіх 4 локально
│   ├── docker-compose.yml   # Запуск всіх 4 через Docker
│   └── Dockerfile           # Один образ для експериментів
├── docker-compose.yml       # Головний compose (postgres, redis, web, celery, beat, frontend)
├── Dockerfile               # Django backend (multi-stage)
├── nginx.conf               # Кореневий nginx (якщо запуск без frontend container)
├── Makefile                 # Зручні команди
├── requirements.txt         # Python залежності
├── .env.example             # Шаблон змінних середовища
└── manage.py                # Django CLI
```

---

## 🚀 Швидкий старт (Docker)

### Вимоги

- Docker Engine 24.0+
- Docker Compose v2+
- 4 GB RAM (рекомендовано)
- ~2 GB вільного місця

### Перше розгортання

```bash
# 1. Клонування
https://github.com/ТВОЄ-ІМ'Я/faceguard.git
cd faceguard

# 2. Одна команда — все збілдить, запустить, мігрує
make setup

# 3. Створити адміна
make superuser
```

Після `make setup` сервіси доступні за адресами:

| Сервіс | URL | Опис |
|--------|-----|------|
| **Frontend** | http://localhost | React SPA (через nginx) |
| **Backend API** | http://localhost:8000/api/v1/ | Django REST |
| **Admin** | http://localhost:8000/admin/ | Django Admin |
| **Health** | http://localhost:8000/api/v1/health/ | Статус системи |

### Щоденні команди

```bash
make up          # Запустити всі сервіси
make down        # Зупинити
make restart     # Перезапустити
make logs        # Логи всіх сервісів
make logs-web    # Логи Django
make migrate     # Застосувати міграції
make shell       # Django shell
make shell-db    # PostgreSQL shell
make health      # Health-check
```

---

## 🛠️ Локальна розробка (без Docker)

### 1. PostgreSQL + Redis

```bash
# macOS (Homebrew)
brew install postgresql redis
brew services start postgresql
brew services start redis

# Ubuntu
sudo apt update && sudo apt install postgresql redis-server
sudo systemctl start postgresql redis-server
```

### 2. Python оточення

```bash
# Створити БД та користувача
psql -U postgres -c "CREATE DATABASE faceguard;"
psql -U postgres -c "CREATE USER faceguard WITH PASSWORD 'faceguard_secret';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE faceguard TO faceguard;"

# Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env для локального запуску
cp .env.example .env
# Відредагуй: DB_HOST=localhost, REDIS_URL=redis://localhost:6379/0
```

### 3. Запуск backend

```bash
# Міграції
python manage.py migrate --settings=faceguard.settings.development

# Збір статики
python manage.py collectstatic --noinput --settings=faceguard.settings.development

# Dev-сервер
make dev-back
# або
DJANGO_SETTINGS_MODULE=faceguard.settings.development python manage.py runserver 0.0.0.0:8000
```

### 4. Запуск frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### 5. Celery (опціонально)

```bash
# Worker
make dev-celery
# або
celery -A faceguard worker -l info

# Beat (scheduler)
celery -A faceguard beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## 🧠 ML Pipeline

Головний компонент — `ml.pipeline.FaceRecognitionPipeline` (singleton), який ініціалізується при старті Django (`apps.recognition.apps.ready()`).

### Порядок обробки кадру

```
1. CLAHE препроцесинг (покращення при слабкому освітленні)
2. Детекція облич (HOG або CNN)
3. FaceTracker — стабільні ID для кожного обличчя
4. Landmarks (68 точок) для liveness
5. Encoding → 128-вимірний вектор (ResNet-29)
6. TextureAntiSpoofing (LBP + Sobel + FFT)
7. LivenessDetector (EAR blink detection)
8. Фінальне рішення: spoofing / warming_up / match
9. FaceMatcher (евклідова відстань + confidence threshold)
```

### Налаштування через `.env`

```env
FACE_DETECTOR_MODEL=hog        # hog (швидко, CPU) або cnn (точніше, GPU)
FACE_TOLERANCE=0.55            # поріг відстані (0.40–0.60)
MIN_CONFIDENCE=45.0            # мінімальна впевненість (%)
LIVENESS_ENABLED=True          # увімкнути перевірку живості
LIVENESS_THRESHOLD=0.20        # EAR threshold для blink
```

### Метрики при tolerance=0.55

| Метрика | Значення |
|---------|----------|
| FAR | 4.3% |
| FRR | 3.8% |
| Accuracy | 96.0% |

---

## 📚 API

Базовий URL: `http://localhost:8000/api/v1/`

Авторизація: `Authorization: Bearer <access_token>`

### Endpoints

| Метод | URL | Опис |
|-------|-----|------|
| `POST` | `/auth/token/` | Логін (JWT) |
| `POST` | `/auth/token/refresh/` | Оновлення токена |
| `POST` | `/auth/logout/` | Вихід (blacklist) |
| `GET` | `/health/` | Статус DB / Redis / Celery |
| `GET` | `/settings/` | Системні налаштування |
| `CRUD` | `/users/` | Користувачі |
| `CRUD` | `/persons/` | Особи (біометрія) |
| `CRUD` | `/departments/` | Відділи |
| `CRUD` | `/cameras/` | Камери |
| `CRUD` | `/events/` | Події розпізнавання |
| `CRUD` | `/reports/` | Звіти |
| `CRUD` | `/security/spoofing/` | Спроби спуфінгу |
| `CRUD` | `/security/audit-log/` | Аудит |

### Пагінація, фільтрація, пошук

- `?page=2&page_size=50`
- `?department=1&is_active=true`
- `?search=Іваненко`

### Rate limits

- `anon`: 20/min
- `user`: 300/min
- `auth`: 10/min (логін/рефреш)

---

## 🔌 WebSocket

Django Channels + Redis Channel Layer.

```
ws://localhost:8000/ws/camera/{camera_id}/
```

Повідомлення надходять у форматі JSON з base64 JPEG кадром та масивом `faces`:

```json
{
  "type": "frame",
  "camera_id": 1,
  "frame": "data:image/jpeg;base64,/9j/4AAQ...",
  "faces": [
    {
      "bbox": {"top": 120, "right": 340, "bottom": 380, "left": 100},
      "person_id": 5,
      "person_name": "Іваненко Петро",
      "confidence": 92.5,
      "is_known": true,
      "is_spoofing": false,
      "liveness_score": 1.0,
      "is_warming_up": false,
      "texture_score": 0.85,
      "track_id": 0
    }
  ],
  "fps": 24.5,
  "processing_ms": 42.3
}
```

---

## 🧪 Тести

```bash
# Pytest (локально)
pytest

# Django test (всередині Docker)
make test
```

---

## 🧫 Експерименти для дипломної роботи

4 експерименти в папці `experiments/` підтверджують наукові принципи системи.

### Запуск

```bash
# Локально (всі 4)
cd experiments
./run.sh

# З кореня проєкту
make exp-run-all

# Через Docker
make exp-run-docker
```

### Результати

| Експеримент | Файл | Опис |
|-------------|------|------|
| 1 | `01_distance_histogram.png` | Гістограма відстаней same vs different |
| 2 | `02_metrics_by_tolerance.png` | FAR/FRR/Accuracy для tolerance [0.40–0.60] |
| 3 | `03_encryption_results.png` | Тести шифрування Fernet |
| 4 | `04_face_pipeline_vertical.png` | Схема pipeline (PNG + PDF) |

Детальніше — див. [`experiments/README.md`](experiments/README.md).

---

## ⚙️ Змінні середовища (.env)

Копіюй `.env.example` → `.env` (автоматично при `make setup`).

```env
# ── Django ──
SECRET_KEY=your-secret-key-change-this-in-production-min-50-chars
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# ── База даних ──
DB_NAME=faceguard
DB_USER=faceguard
DB_PASSWORD=faceguard_secret
DB_HOST=postgres          # Docker: postgres | Локально: localhost
DB_PORT=5432

# ── Redis ──
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ── ML ──
FACE_DETECTOR_MODEL=hog
FACE_TOLERANCE=0.55
MIN_CONFIDENCE=45.0
LIVENESS_ENABLED=True
LIVENESS_THRESHOLD=0.5

# ── GDPR (Fernet ключ) ──
BIOMETRIC_ENCRYPTION_KEY=your-32-byte-base64-encoded-key-here

# ── Медіа / CORS ──
MEDIA_ROOT=./media
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

> ⚠️ **Важливо**: `BIOMETRIC_ENCRYPTION_KEY` генерується автоматично при `make setup`. Не втрачайте його — без ключа неможливо дешифрувати біометричні дані!

---

## 📋 Makefile команди

| Команда | Опис |
|---------|------|
| `make setup` | 🚀 Перше розгортання (генерує .env, будує, міграції) |
| `make build` | 🔨 Зібрати Docker образи |
| `make up` | ▶ Запустити всі сервіси |
| `make down` | ■ Зупинити всі сервіси |
| `make restart` | 🔄 Перезапустити |
| `make logs` | 📋 Логи всіх сервісів |
| `make logs-web` | 📋 Логи Django |
| `make logs-celery` | 📋 Логи Celery worker |
| `make migrate` | 🗄 Застосувати міграції |
| `make makemigrations` | 🗄 Створити міграції |
| `make superuser` | 👤 Створити суперадміна |
| `make shell` | 🐚 Django shell |
| `make shell-db` | 🐚 PostgreSQL shell |
| `make dev-back` | 🛠 Django dev-сервер локально |
| `make dev-front` | 🛠 React dev-сервер локально |
| `make dev-celery` | 🛠 Celery worker локально |
| `make test` | 🧪 Запустити тести |
| `make health` | 💚 Перевірити стан сервісів |
| `make status` | 📊 Статус контейнерів + health |
| `make clean` | 🗑 Видалити зупинені контейнери |
| `make fclean` | ⚠ Видалити ВСЕ (включно з БД та медіа) |
| `make exp-run-all` | 🧪 Запустити всі 4 експерименти (локально) |
| `make exp-run-docker` | 🧪 Запустити всі 4 експерименти через Docker |
| `make exp-clean` | 🗑 Очистити результати експериментів |

---

## 🐳 Docker сервіси

| Сервіс | Образ | Порт | Опис |
|--------|-------|------|------|
| `postgres` | postgres:16-alpine | 5432 | База даних |
| `redis` | redis:7-alpine | 6379 | Кеш / Channels / Celery broker |
| `web` | Dockerfile (Django) | 8000 | ASGI сервер (Daphne) |
| `celery` | Dockerfile (Django) | — | Celery worker (4 потоки) |
| `celery-beat` | Dockerfile (Django) | — | Планувальник задач |
| `frontend` | frontend/Dockerfile | 80 | Nginx + React SPA |

---

## 🔒 GDPR та безпека

- **Шифрування біометрії**: 128D вектори зберігаються у БД у зашифрованому вигляді (Fernet).
- **Anonymize**: Команда `anonymize_person()` видаляє всі фото, encodings, очищує ПІБ, деактивує запис.
- **Consent**: Обробка біометрії лише за наявності `consent_given=True`.
- **Audit log**: Всі критичні операції (логін, зміни налаштувань, спуфінг) записуються в `AuditLog`.
- **Rate limiting**: JWT endpoints захищені від brute-force.
- **CORS**: Налаштовується через `.env`.

---

## 📄 Ліцензія

MIT License © 2026 FaceGuard Project

---

> 💡 **Порада**: Перед першим запуском переконайтеся, що порт `5432`, `6379`, `8000`, `80` вільні, або зміните порти в `docker-compose.yml`.
