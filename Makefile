# ══════════════════════════════════════════════════════
#  FaceGuard — Makefile
#  Швидке розгортання всього проєкту через Docker
# ══════════════════════════════════════════════════════

.PHONY: help setup build up down restart logs migrate superuser dev-back dev-front clean fclean import-dataset exp-run-all exp-run-docker exp-clean

# Кольори для виводу
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RESET  := \033[0m

EXP_DIR := experiments
DATASET_DIR ?= /app/dataset

help: ## Показати всі доступні команди
	@echo ""
	@echo "$(CYAN)  🛡  FaceGuard — Команди$(RESET)"
	@echo "$(CYAN)════════════════════════════════$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-18s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Перша ініціалізація ──────────────────────────────
setup: ## 🚀 Перше розгортання (генерує ключі, будує образи, мігрує)
	@echo "$(CYAN)► Генеруємо .env...$(RESET)"
	@$(MAKE) _generate_env
	@echo "$(CYAN)► Збираємо Docker образи (no-cache, включно з React SPA)...$(RESET)"
	docker compose build --no-cache
	@echo "$(CYAN)► Запускаємо сервіси...$(RESET)"
	@$(MAKE) up
	@echo "$(CYAN)► Чекаємо на PostgreSQL...$(RESET)"
	@sleep 8
	@echo "$(CYAN)► Генеруємо міграції...$(RESET)"
	docker compose exec web python manage.py makemigrations --settings=faceguard.settings.production
	@echo "$(CYAN)► Застосовуємо міграції...$(RESET)"
	@$(MAKE) migrate
	@echo "$(CYAN)► Збираємо статичні файли...$(RESET)"
	@docker compose exec web python manage.py collectstatic --noinput --settings=faceguard.settings.production
	@echo ""
	@echo "$(GREEN)✅ FaceGuard готовий!$(RESET)"
	@echo "$(GREEN)   Backend API:   http://localhost:8000/api/v1/$(RESET)"
	@echo "$(GREEN)   Admin panel:   http://localhost:8000/admin/$(RESET)"
	@echo "$(GREEN)   Frontend:      http://localhost$(RESET)"
	@echo "$(YELLOW)   Запусти: make superuser — щоб створити адміна$(RESET)"

_generate_env: ## (внутрішня) Генерує .env якщо ще немає
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		SECRET=$$(python3 -c "import secrets; print(secrets.token_urlsafe(60))"); \
		BKEY=$$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "CHANGE_ME_RUN_make_setup_again"); \
		sed -i.bak "s|your-secret-key-change-this-in-production-min-50-chars|$$SECRET|g" .env; \
		sed -i.bak "s|your-32-byte-base64-encoded-key-here|$$BKEY|g" .env; \
		sed -i.bak "s|DB_USER=postgres|DB_USER=faceguard|g" .env; \
		sed -i.bak "s|DB_PASSWORD=your-db-password|DB_PASSWORD=faceguard_secret|g" .env; \
		sed -i.bak "s|DEBUG=True|DEBUG=False|g" .env; \
		rm -f .env.bak; \
		echo "$(GREEN)✓ .env створено$(RESET)"; \
	else \
		echo "$(YELLOW)⚠ .env вже існує, пропускаємо$(RESET)"; \
	fi

# ── Docker ───────────────────────────────────────────
build-frontend: ## ⚛ Зібрати React SPA локально (npm run build)
	cd frontend && npm run build
	@echo "$(GREEN)✓ React SPA зібрано в frontend/dist/$(RESET)"

build: ## 🔨 Зібрати всі Docker образи
	docker compose build

up: ## ▶ Запустити всі сервіси (фон)
	docker compose up -d
	@echo "$(GREEN)✓ Сервіси запущено$(RESET)"

down: ## ■ Зупинити всі сервіси
	docker compose down
	@echo "$(GREEN)✓ Сервіси зупинено$(RESET)"

restart: ## 🔄 Перезапустити всі сервіси
	docker compose restart

logs: ## 📋 Показати логи (всі сервіси)
	docker compose logs -f

logs-web: ## 📋 Логи Django
	docker compose logs -f web

logs-celery: ## 📋 Логи Celery worker
	docker compose logs -f celery

logs-beat: ## 📋 Логи Celery beat
	docker compose logs -f celery-beat

ps: ## 📊 Статус сервісів
	docker compose ps

# ── Django ───────────────────────────────────────────
migrate: ## 🗄 Застосувати міграції Django
	docker compose run --rm web python manage.py migrate --settings=faceguard.settings.production

makemigrations: ## 🗄 Створити нові міграції
	docker compose run --rm web python manage.py makemigrations --settings=faceguard.settings.production

superuser: ## 👤 Створити суперадміна
	docker compose run --rm web python manage.py createsuperuser --settings=faceguard.settings.production

shell: ## 🐚 Django shell
	docker compose run --rm web python manage.py shell --settings=faceguard.settings.production

shell-db: ## 🐚 PostgreSQL shell
	docker compose exec postgres psql -U faceguard -d faceguard

# ── Розробка (локально без Docker) ──────────────────
dev-back: ## 🛠 Запустити Django dev-сервер локально
	@echo "$(YELLOW)Встановіть спочатку: pip install -r requirements.txt$(RESET)"
	DJANGO_SETTINGS_MODULE=faceguard.settings.development \
		python3 manage.py runserver 0.0.0.0:8000

dev-front: ## 🛠 Запустити React dev-сервер локально
	cd frontend && npm run dev

dev-celery: ## 🛠 Запустити Celery worker локально
	celery -A faceguard worker -l info

# ── Імпорт датасету ─────────────────────────────────
import-dataset: ## 📥 Імпортувати фото з dataset/ у persons/encodings
	docker compose exec web python manage.py import_dataset_photos \
		--dataset $(DATASET_DIR) \
		--settings=faceguard.settings.production

# ── Здоров'я системи ──────────────────────────────────
health: ## 💚 Перевірити стан сервісів (DB, Redis, Celery)
	@curl -s http://localhost:8000/api/v1/health/ | python3 -m json.tool || echo "Сервіс недоступний"

status: ## 📊 Статус контейнерів + health-check
	@$(MAKE) ps
	@echo ""
	@$(MAKE) health

# ── Тести ────────────────────────────────────────────
test: ## 🧪 Запустити тести Django
	docker compose exec web python manage.py test --settings=faceguard.settings.development

# ── Очищення ─────────────────────────────────────────
clean: ## 🗑 Видалити зупинені контейнери і dangling image
	docker compose down --remove-orphans
	docker image prune -f

fclean: ## ⚠ Видалити ВСЕ включно з базою даних та медіафайлами
	@echo "$(YELLOW)⚠ Попередження: видаляє PostgreSQL volume і media!$(RESET)"
	@read -p "Продовжити? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose down -v --remove-orphans
	docker image prune -af
	@echo "$(GREEN)✓ Очищено$(RESET)"

# ── Експерименти для дипломної ────────────────────────
exp-run-all: ## 🧪 Запустити ВСІ 4 експерименти (локально)
	@bash $(EXP_DIR)/run.sh

exp-run-docker: ## 🧪 Запустити ВСІ 4 експерименти через Docker
	cd $(EXP_DIR) && docker compose up --build

exp-clean: ## 🗑 Очистити результати експериментів
	rm -rf $(EXP_DIR)/output
	@echo "$(GREEN)✓ Результати експериментів очищено$(RESET)"
