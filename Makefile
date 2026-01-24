.PHONY: help install lint format typecheck test check clean

help:
	@echo "Available commands:"
	@echo "  make install    - Install dev dependencies"
	@echo "  make lint       - Run ruff linter"
	@echo "  make fix        - Auto-fix lint issues"
	@echo "  make format     - Format code with ruff"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make test       - Run pytest"
	@echo "  make check      - Run all checks (lint, format, typecheck, test)"
	@echo "  make pre-commit - Run pre-commit hooks"
	@echo "  make clean      - Remove build artifacts"

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run djlint django_admin_mcp/ --check

fix:
	uv run ruff check . --fix

format:
	uv run ruff format .
	uv run djlint django_admin_mcp/ --reformat

typecheck:
	uv run mypy django_admin_mcp/

test:
	PYTHONPATH=. uv run pytest

test-cov:
	PYTHONPATH=. uv run pytest --cov=django_admin_mcp --cov-report=term-missing

pre-commit:
	uv run pre-commit run --all-files

check: lint typecheck test

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
