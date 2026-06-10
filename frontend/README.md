# FaceGuard — Frontend (React 19 + TypeScript + Vite)

> SPA (Single Page Application) для системи розпізнавання облич FaceGuard.

---

## 🛠️ Стек технологій

| Технологія | Версія | Призначення |
|------------|--------|-------------|
| React | 19.2.0 | UI фреймворк |
| TypeScript | 5.9.3 | Типізація |
| Vite | 7.3.1 | Збірка / dev-сервер |
| Tailwind CSS | 4.2.4 | Стилізація |
| Radix UI | 1.4.3 | Компоненти (Alert, Dialog, Dropdown, Tabs, Toast тощо) |
| Zustand | 5.0.11 | State management |
| Axios | 1.13.6 | HTTP-клієнт |
| React Router | 7.13.1 | Маршрутизація |
| Recharts | 3.7.0 | Графіки / діаграми |

---

## 📁 Структура

```
frontend/
├── src/
│   ├── api/          # API client (axios instance, interceptors, endpoints)
│   ├── components/   # React компоненти (UI + бізнес-логіка)
│   ├── pages/        # Сторінки (Dashboard, Persons, Cameras, Events, Reports, Settings)
│   ├── store/        # Zustand stores (auth, cameras, persons, events)
│   ├── types/        # TypeScript типи / інтерфейси
│   ├── lib/          # Утиліти (cn, dateFormat, validators)
│   ├── assets/       # Статичні ресурси (логотип, іконки)
│   ├── App.tsx       # Кореневий компонент з роутами
│   ├── main.tsx      # Точка входу (ReactDOM.createRoot)
│   └── index.css     # Глобальні Tailwind стилі
├── public/           # Публічні файли (favicon, index.html)
├── dist/             # Production build (генерується `npm run build`)
├── Dockerfile        # Multi-stage: Node → nginx
├── nginx.conf        # SPA fallback: try_files $uri /index.html
├── vite.config.ts    # Vite + proxy (/api, /ws, /media)
├── package.json
└── tsconfig.json
```

---

## 🚀 Запуск

```bash
# 1. Встановити залежності
npm install

# 2. Dev-сервер (з проксі на Django backend)
npm run dev     # http://localhost:5173

# 3. Production build
npm run build   # результат → dist/

# 4. Лінт
npm run lint
```

---

## 🔌 Proxy (dev-режим)

Vite автоматично проксіює запити на Django:

- `GET /api/v1/...` → `http://localhost:8000`
- `WS /ws/...` → `ws://localhost:8000`
- `GET /media/...` → `http://localhost:8000`

> Для production nginx сам маршрутизує `/api/` та `/ws/` на Django контейнер.

---

## 🎨 Дизайн-система

- **Tailwind CSS** — utility-first стилі.
- **Radix UI** — accessible, unstyled компоненти (Alert Dialog, Dropdown Menu, Tabs, Toast, Tooltip тощо).
- **Lucide React** — іконки.
- **Next Themes** — світла / темна тема.
- **Sonner** — toast-сповіщення.
- **shadcn/ui patterns** — компоненти з `class-variance-authority` та `tailwind-merge`.

---

## 📦 Docker

```bash
# Зібрати локально (для ручного тестування)
cd frontend && npm run build

# Docker образ (multi-stage)
# Stage 1: Node 22 Alpine → build
# Stage 2: nginx Alpine → serve dist/ + nginx.conf
```

Образ використовується в `docker-compose.yml` (сервіс `frontend`, порт `80`).

---

## 🔑 Авторизація

- JWT (access + refresh tokens) зберігаються в Zustand store.
- Axios interceptor автоматично додає `Authorization: Bearer <token>`.
- При 401 — спроба рефрешу токена; при невдачі — перенаправлення на `/login`.

---

## 📋 Головні сторінки

| Шлях | Опис |
|------|------|
| `/` | Dashboard (загальна статистика, графіки) |
| `/persons` | Управління особами (CRUD, фото, encodings) |
| `/cameras` | Камери (додавання, налаштування, перегляд стріму) |
| `/events` | Події розпізнавання (фільтрація, пошук) |
| `/reports` | Звіти (PDF/Excel, генерація) |
| `/security` | Спроби спуфінгу, Audit Log |
| `/settings` | Системні налаштування (для адмінів) |
| `/login` | Сторінка входу |

---

## ⚙️ Конфігурація

Конфігурація через vite.config.ts:
- `VITE_API_URL` (за замовчуванням `/api/v1` через nginx proxy)
- `VITE_WS_URL` (за замовчуванням `ws://<same-host>`)

Для Docker не потрібно build args — nginx сам маршрутизує.

---

## 📝 Примітки

- `dist/` генерується автоматично, не комітьте його в git.
- При додаванні нової сторінки — додайте роут в `App.tsx`.
- Для нового API endpoint — додайте функцію в `src/api/`.
