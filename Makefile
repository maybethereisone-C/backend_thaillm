.PHONY: install run dev test test-unit test-integration cover clean docker-build help

UV := uv
HOST ?= 127.0.0.1
PORT ?= 18000
IMAGE ?= llm-gateway

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install         Install dependencies"
	@echo "  run             Run production server locally"
	@echo "  dev             Run development server with app-only reload"
	@echo "  test            Run full test suite"
	@echo "  test-unit       Run unit tests only"
	@echo "  test-integration  Run integration tests only"
	@echo "  cover           Run tests with coverage report"
	@echo "  clean           Remove generated local files"
	@echo "  docker-build    Build production Docker image"

install:
	$(UV) sync

run:
	$(UV) run uvicorn app.main:app --host $(HOST) --port $(PORT)

dev:
	$(UV) run uvicorn app.main:app --host $(HOST) --port $(PORT) --reload --reload-dir app

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest tests/unit

test-integration:
	$(UV) run pytest tests/integration

cover:
	$(UV) run pytest --cov=app --cov-report=term-missing

clean:
	find . -path './.venv' -prune -o -type d -name "__pycache__" -exec rm -rf {} +
	find . -path './.venv' -prune -o -type f -name "*.pyc" -delete
	find . -path './.venv' -prune -o -type f -name ".DS_Store" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov

docker-build:
	docker build -t $(IMAGE) .
