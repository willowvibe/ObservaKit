.PHONY: help up down build test lint format migrate logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Rebuild backend image
	docker compose build backend

test: ## Run test suite
	PYTHONPATH=. pytest tests/ -v

test-cov: ## Run tests with coverage
	PYTHONPATH=. pytest tests/ -v --cov=backend --cov-report=html

lint: ## Run linter
	ruff check .

format: ## Auto-format code
	ruff format .

migrate: ## Run database migrations
	alembic upgrade head

migrate-new: ## Create a new migration (usage: make migrate-new msg="add column")
	alembic revision --autogenerate -m "$(msg)"

logs: ## Follow backend logs
	docker compose logs -f backend

clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml

dev: ## Run backend in dev mode
	PYTHONPATH=. uvicorn backend.main:app --reload --port 8000

demo: ## Seed the database with mock data and run a demo
	PYTHONPATH=. python3 scripts/generate_mock_data.py
	@echo "✅ Mock data loaded. Run 'make dev' to start the server."
