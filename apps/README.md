# FaceGuard — Django Apps

> Модульна архітектура Django проєкту. Кожен app відповідає за окрему доменну область.

---

## 📁 Структура

```
apps/
├── core/           # Користувачі, системні налаштування, health-check
├── persons/        # Особи, фото, FaceEncoding, GDPR anonymize
├── cameras/        # Камери, RTSP/USB streams, налаштування
├── events/         # RecognitionEvent, DailyStats, snapshots
├── recognition/    # ML pipeline singleton (state.py)
├── reports/        # PDF/Excel/CSV генератори
├── security/       # SpoofingAttempt, AuditLog
└── streaming/      # WebSocket consumers (камери + веб-камера)
```

---

## 🧩 Опис кожного app

### `apps.core`
- **Моделі:** `User` (custom user model), `SystemSettings` (key-value налаштування)
- **Views:** `UserViewSet` (CRUD користувачів), `health_check`, `system_settings`
- **Middleware:** `SecurityAuditMiddleware` — логування критичних операцій
- **Permissions:** `IsAdminOrAbove`, `IsGuardOrAbove`, `IsSuperAdmin`

### `apps.persons`
- **Моделі:** `Person`, `PersonPhoto`, `FaceEncoding`, `Department`
- **Views:** `PersonViewSet` (CRUD + фото + train + anonymize), `DepartmentViewSet`
- **Services:** `register_person`, `train_person_encodings`, `load_all_encodings`, `anonymize_person`
- **GDPR:** `anonymize_person()` — видаляє біометрію, фото, очищує ПІБ, деактивує запис.
- **Management commands:**
  - `import_dataset_photos` — масовий імпорт фото з папки
  - `generate_fernet_key` — генерація ключа для шифрування біометрії

### `apps.cameras`
- **Моделі:** `Camera` (stream_url, status, recognition_enabled, frame_skip, detection_confidence, resolution_scale)
- **Views:** `CameraViewSet` (CRUD + запуск/зупинка стріму)
- **Worker:** `CameraWorker` (див. `workers/camera_worker.py`)

### `apps.events`
- **Моделі:** `RecognitionEvent` (timestamp, camera, person, event_type, confidence, snapshot), `DailyStats`
- **Views:** `RecognitionEventViewSet` (фільтрація, пошук, агрегація)
- **Services:** `EventService` — створення подій з `FrameResult`
- **Event types:** `recognized`, `unknown`, `spoofing`

### `apps.recognition`
- **Призначення:** Ініціалізація ML pipeline singleton при старті Django.
- **Файли:** `apps.py` (`RecognitionConfig.ready()`), `state.py` (`get_pipeline()`)
- **ML Pipeline:** див. `ml/README.md`

### `apps.reports`
- **Моделі:** `Report` (report_type, format, status, file, params_json)
- **Views:** `ReportViewSet` (CRUD, запуск генерації)
- **Generators:** `ReportGeneratorFactory` — PDF (ReportLab), Excel (openpyxl), CSV

### `apps.security`
- **Моделі:** `SpoofingAttempt` (timestamp, camera, confidence, method), `AuditLog` (action, user, resource, timestamp)
- **Views:** `SpoofingAttemptViewSet`, `AuditLogViewSet`
- **Middleware:** `SecurityAuditMiddleware` автоматично записує логи в `AuditLog`

### `apps.streaming`
- **Призначення:** WebSocket consumers для real-time відео.
- **Файли:** `consumers.py` (camera stream), `webcam_consumer.py` (веб-камера з браузера), `routing.py` (URL patterns)
- **Протокол:** Django Channels + Redis Channel Layer

---

## 🔐 Permissions (ролі)

| Роль | Доступ |
|------|--------|
| **SuperAdmin** | Все + anonymize, видалення користувачів |
| **Admin** | CRUD осіб, камер, користувачів, налаштування |
| **Guard** | Перегляд осіб, камер, подій, звітів |
| **User** | Лише власні дані (якщо передбачено) |

---

## 📚 REST API Endpoints

Всі endpoints префіксовані `/api/v1/` (див. `faceguard/api_urls.py`).

| Endpoint | App | Методи | Опис |
|----------|-----|--------|------|
| `/users/` | core | CRUD | Користувачі |
| `/persons/` | persons | CRUD | Особи |
| `/persons/{id}/photos/` | persons | GET, POST | Фото особи |
| `/persons/{id}/train/` | persons | POST | Запуск тренування encodings |
| `/persons/{id}/anonymize/` | persons | POST | GDPR anonymize (superadmin) |
| `/departments/` | persons | CRUD | Відділи |
| `/cameras/` | cameras | CRUD | Камери |
| `/events/` | events | CRUD | Події розпізнавання |
| `/reports/` | reports | CRUD | Звіти |
| `/security/spoofing/` | security | CRUD | Спроби спуфінгу |
| `/security/audit-log/` | security | CRUD | Audit log |
| `/health/` | core | GET | Health-check |
| `/settings/` | core | GET, PUT | Системні налаштування |
| `/auth/token/` | core | POST | JWT login |
| `/auth/token/refresh/` | core | POST | JWT refresh |
| `/auth/logout/` | core | POST | JWT logout (blacklist) |

---

## 🗄️ Моделі — зв'язки

```
Department 1 ──────── N Person
Person 1 ──────────── N PersonPhoto
Person 1 ──────────── N FaceEncoding
Person 1 ──────────── N RecognitionEvent
Camera 1 ──────────── N RecognitionEvent
Camera 1 ──────────── N SpoofingAttempt
User 1 ────────────── N AuditLog
```

---

## 📝 Примітки

- Всі моделі використовують `BigAutoField` як primary key.
- Мова застосунку: українська (`LANGUAGE_CODE = 'uk'`).
- Часовий пояс: `Europe/Kyiv`.
- Custom User model: `AUTH_USER_MODEL = 'core.User'` (з полем `role`).
- FaceEncoding використовує Fernet шифрування (GDPR) — див. `apps.persons.models.FaceEncoding.set_encoding()` / `get_encoding()`.
