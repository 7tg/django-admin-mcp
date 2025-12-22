# Tests for django-admin-mcp

This directory contains the test suite for the django-admin-mcp package.

## Quick Start

Install dev dependencies:
```bash
pip install -e ".[dev]"
```

Run all tests:
```bash
pytest
```

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Tests with Verbose Output
```bash
pytest -v
```

### Run Specific Test Module
```bash
pytest tests/test_mixin.py
pytest tests/test_crud.py
pytest tests/test_http.py
```

### Run Specific Test Class or Function
```bash
pytest tests/test_mixin.py::TestMCPAdminMixin
pytest tests/test_crud.py::TestCRUDOperations::test_create_author
```

### Run Tests with Coverage
```bash
# Terminal report
pytest --cov=django_admin_mcp --cov-report=term-missing

# HTML report (opens in htmlcov/index.html)
pytest --cov=django_admin_mcp --cov-report=html

# Both terminal and HTML
pytest --cov=django_admin_mcp --cov-report=html --cov-report=term
```

### Run Tests in Parallel (faster)
```bash
pip install pytest-xdist
pytest -n auto
```

## Test Structure

- `test_mixin.py`: Tests for MCPAdminMixin functionality, tool generation, and schemas (11 tests)
- `test_crud.py`: Tests for CRUD operations via MCP tools (9 tests)
- `test_http.py`: Tests for HTTP interface and token authentication (15 tests)
- `models.py`: Test models (Author and Article) used in tests
- `settings.py`: Django settings for test environment
- `conftest.py`: Pytest configuration and fixtures

## Test Coverage

The test suite provides **74% code coverage** across:
- Model registration with MCP
- MCP server creation
- Tool generation for each model
- Tool schema validation
- CRUD operations (Create, Read, Update, Delete)
- HTTP API interface
- Token authentication and management
- Token expiration handling
- Opt-in tool exposure (mcp_expose flag)
- Error handling and field validation
- Foreign key relationships
- Search/find functionality

## Code Quality

The package includes linting checks that run in CI:

```bash
# Check formatting
black --check django_admin_mcp/ tests/

# Check import sorting
isort --check-only django_admin_mcp/ tests/

# Run linter
flake8 django_admin_mcp/ tests/ --max-line-length=120 --extend-ignore=E203,W503
```

## CI/CD

Tests run automatically on GitHub Actions for:
- Python versions: 3.10, 3.11, 3.12
- Django versions: 3.2, 4.0, 4.1, 4.2, 5.0

See `.github/workflows/tests.yml` for configuration.

## Test Results

For detailed test results and coverage analysis, see `../TEST_RESULTS.md`.
