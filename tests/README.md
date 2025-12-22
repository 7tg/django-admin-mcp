# Tests for django-admin-mcp

This directory contains the test suite for the django-admin-mcp package.

## Running Tests

Install dev dependencies:
```bash
pip install -e ".[dev]"
```

Run all tests:
```bash
pytest
```

Run specific tests:
```bash
pytest tests/test_mixin.py
pytest tests/test_crud.py
```

Run tests with coverage:
```bash
pytest --cov=django_admin_mcp --cov-report=html
```

## Test Structure

- `test_mixin.py`: Tests for MCPAdminMixin functionality, tool generation, and schemas
- `test_crud.py`: Tests for CRUD operations via MCP tools
- `models.py`: Test models (Author and Article) used in tests
- `settings.py`: Django settings for test environment
- `conftest.py`: Pytest configuration and fixtures

## Test Coverage

The test suite covers:
- Model registration with MCP
- MCP server creation
- Tool generation for each model
- Tool schema validation
- CRUD operations (Create, Read, Update, Delete)
- Error handling
- Field validation
- Foreign key relationships
