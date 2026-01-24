# AGENTS.md - AI Agent Instructions for django-admin-mcp

This document provides context and guidelines for AI agents (GitHub Copilot, etc.) working on this codebase.

## Project Overview

**django-admin-mcp** is a Django package that exposes Django admin models to MCP (Model Context Protocol) clients via HTTP. It enables AI assistants to interact with Django admin interfaces through standardized tools, providing CRUD operations, admin actions, model history, and more.

### Key Features

- Zero dependencies beyond Django and Pydantic
- Token-based HTTP authentication with configurable expiry
- Respects Django admin permissions (view/add/change/delete)
- Full CRUD, bulk operations, admin actions, model introspection
- Related object traversal and change history access

## Architecture

```
MCP Client (IDE, Agent, etc.)
    ↓ HTTP + Bearer Token
MCPHTTPView (django_admin_mcp/views.py)
    ↓ JSON-RPC
Tools Registry (django_admin_mcp/tools/registry.py)
    ↓
Handlers (django_admin_mcp/handlers/)
    ↓
Django Admin + ModelAdmin
    ↓
Database
```

## Directory Structure

```
django-admin-mcp/
├── django_admin_mcp/           # Main package
│   ├── __init__.py             # Public exports (MCPAdminMixin)
│   ├── mixin.py                # Core MCPAdminMixin class
│   ├── models.py               # MCPToken model (authentication)
│   ├── views.py                # HTTP view (MCPHTTPView)
│   ├── admin.py                # Django admin registration
│   ├── apps.py                 # Django app config
│   ├── urls.py                 # URL routing
│   ├── handlers/               # Operation handlers
│   │   ├── base.py             # Base utilities, permissions
│   │   ├── crud.py             # Create, Read, Update, Delete
│   │   ├── actions.py          # Admin actions
│   │   ├── relations.py        # Foreign key relations
│   │   └── meta.py             # Model introspection
│   ├── protocol/               # MCP protocol implementation
│   │   ├── types.py            # Pydantic type definitions
│   │   ├── jsonrpc.py          # JSON-RPC implementation
│   │   └── errors.py           # Error definitions
│   ├── tools/                  # Tool registry and management
│   │   ├── registry.py         # Tool registration and routing
│   │   └── __init__.py         # Tool exports
│   └── migrations/             # Database migrations
├── example/                    # Example Django application
├── tests/                      # Test suite (pytest)
├── docs/                       # Documentation (OpenAPI specs)
└── plans/                      # Future improvement plans
```

## Key Files

| File | Purpose |
|------|---------|
| `django_admin_mcp/mixin.py` | MCPAdminMixin - main entry point for exposing models |
| `django_admin_mcp/models.py` | MCPToken model with user, groups, permissions fields |
| `django_admin_mcp/views.py` | HTTP endpoint handling JSON-RPC requests |
| `django_admin_mcp/tools/registry.py` | Dynamic tool generation from Django models |
| `django_admin_mcp/handlers/base.py` | Permission checking utilities |
| `django_admin_mcp/handlers/crud.py` | CRUD operation implementations |
| `django_admin_mcp/protocol/types.py` | Pydantic models for MCP protocol |

## Coding Standards

### Python Style

- **Python 3.10+** - Use modern Python features (type hints, walrus operator, etc.)
- **Line length**: 120 characters max
- **Formatter**: ruff format
- **Linter**: ruff (replaces flake8, isort, black)
- **Type checker**: mypy with django-stubs

### Import Order (handled by ruff)

1. Standard library
2. Django
3. Third-party packages
4. Local imports (`django_admin_mcp`)

### Type Hints

- Use type hints for all function parameters and return types
- Use `from __future__ import annotations` for forward references
- Pydantic models for complex data structures

### Django Conventions

- ModelAdmin classes should inherit: `MCPAdminMixin, admin.ModelAdmin` (mixin first)
- Use `get_queryset()` for custom filtering
- Respect Django's permission system

### Error Handling

- Use `django_admin_mcp/protocol/errors.py` for MCP-specific errors
- Return proper JSON-RPC error responses
- Include meaningful error messages

## Testing

### Framework

- **pytest** with pytest-django
- **pytest-asyncio** for async tests
- **pytest-cov** for coverage

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=django_admin_mcp

# Specific test file
pytest tests/test_crud.py

# Specific test
pytest tests/test_crud.py::TestListOperation::test_list_basic
```

### Test Structure

- Tests are in `tests/` directory
- Settings in `tests/settings.py`
- Test models in `tests/test_app/models.py`
- Each handler has a corresponding test file: `test_handlers_*.py`

### Test Categories

| File | Tests |
|------|-------|
| `test_crud.py` | CRUD operations |
| `test_permissions.py` | Permission checking |
| `test_http.py` | HTTP interface |
| `test_tools_registry.py` | Tool registration |
| `test_edge_cases.py` | Edge cases and error handling |
| `test_protocol.py` | Protocol types and validation |

### Writing Tests

```python
import pytest
from django.contrib.auth.models import User

@pytest.mark.django_db
class TestFeature:
    def test_basic_case(self, admin_client):
        # Arrange
        user = User.objects.create_user('test', 'test@test.com', 'password')

        # Act
        result = some_function(user)

        # Assert
        assert result.success is True
```

### Async Tests (Django 4.2+)

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.django_db
async def test_async_operation():
    # Async tests are skipped on Django < 4.2
    result = await async_function()
    assert result is not None
```

## Linting and Formatting

### Commands

```bash
# Check for lint errors
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Check formatting
ruff format --check .

# Apply formatting
ruff format .

# Type checking
mypy django_admin_mcp/
```

### Pre-commit

Pre-commit hooks are configured. Install with:

```bash
pip install pre-commit
pre-commit install
```

## Common Development Tasks

### Adding a New Handler

1. Create handler in `django_admin_mcp/handlers/`
2. Inherit from base utilities in `handlers/base.py`
3. Register tools in `tools/registry.py`
4. Add tests in `tests/test_handlers_*.py`
5. Update type definitions in `protocol/types.py` if needed

### Adding a New Tool

1. Define input schema in `protocol/types.py`
2. Implement handler function in appropriate `handlers/*.py`
3. Register in `tools/registry.py` with proper naming convention
4. Add tests covering success and error cases

### Modifying MCPToken

1. Update model in `models.py`
2. Create migration: `python manage.py makemigrations django_admin_mcp`
3. Update permission checking in `handlers/base.py`
4. Add tests for new permission scenarios

## Security Considerations

### Authentication

- All requests require valid Bearer token
- Tokens are validated against `MCPToken` model
- Expired tokens are rejected
- Token usage is tracked (last_used_at)

### Authorization

- Operations check Django admin permissions
- `list_*`, `get_*` require **view** permission
- `create_*` requires **add** permission
- `update_*` requires **change** permission
- `delete_*` requires **delete** permission

### Data Validation

- All input is validated via Pydantic models
- Django's model validation is applied on save
- Foreign keys are validated before assignment

### Do NOT

- Expose internal Django errors to clients
- Allow unauthenticated access
- Bypass permission checks
- Execute raw SQL queries

## Generated Tools Per Model

For a model with `mcp_expose = True`:

| Tool | Permission | Description |
|------|------------|-------------|
| `list_<model>` | view | List with pagination/filtering |
| `get_<model>` | view | Retrieve single instance |
| `create_<model>` | add | Create new instance |
| `update_<model>` | change | Update existing instance |
| `delete_<model>` | delete | Delete instance |
| `describe_<model>` | view | Field definitions |
| `actions_<model>` | view | List admin actions |
| `action_<model>` | varies | Execute admin action |
| `bulk_<model>` | varies | Bulk update/delete |
| `related_<model>` | view | Traverse relations |
| `history_<model>` | view | View change history |
| `autocomplete_<model>` | view | Search suggestions |

## Dependencies

### Required

- **Django >= 3.2** - Web framework
- **Pydantic >= 2.0** - Data validation

### Development

- pytest, pytest-django, pytest-asyncio, pytest-cov
- ruff (linting/formatting)
- mypy, django-stubs (type checking)
- pre-commit

## CI/CD

GitHub Actions runs on push to `main` and `copilot/**` branches:

1. **Tests**: Matrix of Python 3.10-3.12 x Django 3.2-5.0
2. **Lint**: ruff check and format
3. **Type check**: mypy

## Version Support

| Python | Django |
|--------|--------|
| 3.10 | 3.2, 4.0, 4.1, 4.2, 5.0 |
| 3.11 | 3.2, 4.0, 4.1, 4.2, 5.0 |
| 3.12 | 3.2, 4.0, 4.1, 4.2, 5.0 |

## Useful Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run example project
cd example && python manage.py runserver

# Create test token
cd example && python manage.py shell
>>> from django_admin_mcp.models import MCPToken
>>> MCPToken.objects.create(name="test")

# Run all quality checks
ruff check . && ruff format --check . && mypy django_admin_mcp/ && pytest
```
