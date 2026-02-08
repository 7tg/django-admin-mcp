# 🤝 Contributing

Thank you for your interest in contributing to Django Admin MCP! This guide will help you get started.

## 🛠️ Development Setup

### 📋 Prerequisites

- Python 3.10 or higher
- Git
- uv, pip, or another Python package manager

### 📥 Clone the Repository

```bash
git clone https://github.com/7tg/django-admin-mcp.git
cd django-admin-mcp
```

### 📦 Install Dependencies

**Using uv (recommended):**

```bash
uv sync --all-extras
```

**Using pip:**

```bash
pip install -e ".[dev]"
```

### 🔧 Set Up Pre-commit Hooks

```bash
pre-commit install
```

This ensures code quality checks run before each commit.

---

## 🧪 Running Tests

### ▶️ Run All Tests

```bash
pytest
```

### 📊 Run with Coverage

```bash
pytest --cov=django_admin_mcp --cov-report=html
open htmlcov/index.html
```

### 🎯 Run Specific Tests

```bash
# Run a specific test file
pytest tests/test_crud.py

# Run a specific test
pytest tests/test_crud.py::test_list_articles

# Run tests matching a pattern
pytest -k "test_create"
```

### 🔄 Test Against Multiple Django Versions

The CI runs tests against Django 3.2, 4.0, 4.1, 4.2, and 5.0. To test locally:

```bash
# Install a specific Django version
pip install "django==4.2.*"
pytest
```

---

## ✅ Code Quality

### 🔍 Linting

We use Ruff for linting:

```bash
ruff check .
```

Auto-fix issues:

```bash
ruff check --fix .
```

### 🎨 Formatting

```bash
ruff format .
```

### 🏷️ Type Checking

```bash
mypy django_admin_mcp
```

### 🔄 All Checks

Run all checks at once:

```bash
pre-commit run --all-files
```

---

## 📂 Project Structure

```
django-admin-mcp/
├── django_admin_mcp/          # Main package
│   ├── __init__.py           # Package exports
│   ├── mixin.py              # MCPAdminMixin
│   ├── models.py             # MCPToken model
│   ├── views.py              # HTTP endpoint
│   ├── admin.py              # Django admin for tokens
│   ├── urls.py               # URL configuration
│   ├── handlers/             # Tool handlers
│   │   ├── base.py          # Shared utilities
│   │   ├── crud.py          # CRUD operations
│   │   ├── actions.py       # Admin actions
│   │   ├── meta.py          # Model introspection
│   │   ├── relations.py     # Relationships
│   │   └── decorators.py    # Permission decorators
│   ├── protocol/             # MCP protocol
│   │   ├── types.py         # Pydantic models
│   │   ├── jsonrpc.py       # JSON-RPC handling
│   │   └── errors.py        # Error definitions
│   └── tools/                # Tool registry
│       └── registry.py      # Tool generation
├── tests/                    # Test suite
├── docs/                     # Documentation
├── example/                  # Example Django project
└── pyproject.toml           # Project configuration
```

---

## 🔄 Making Changes

### 🌿 Branching Strategy

1. Fork the repository
2. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```
3. Make your changes
4. Push and create a pull request

### 💬 Commit Messages

Use clear, descriptive commit messages:

```
Add support for custom field serializers

- Add FieldSerializer protocol
- Implement JSONFieldSerializer for JSONField
- Update tests for new functionality
```

### 📝 Pull Request Guidelines

- Include a clear description of changes
- Add tests for new functionality
- Update documentation if needed
- Ensure all checks pass
- Keep changes focused and atomic

---

## ➕ Adding Features

### 🔧 Adding a New Handler

1. Create or update handler in `handlers/`:

   ```python title="handlers/myhandler.py"
   async def handle_my_operation(
       model_name: str,
       arguments: dict[str, Any],
       request: HttpRequest
   ) -> list[TextContent]:
       # Implementation
       return [TextContent(text=json.dumps(result))]
   ```

2. Register in `tools/registry.py`:

   ```python
   HANDLERS = {
       # ...
       "my_operation": handle_my_operation,
   }
   ```

3. Add tool schema generation if needed

4. Write tests in `tests/`

### 🛠️ Adding a New Tool

1. Define the tool schema in `tools/registry.py`
2. Implement the handler
3. Add comprehensive tests
4. Document in `docs/tools/`

---

## 🧪 Testing Guidelines

### 📐 Test Structure

```python
import pytest
from django_admin_mcp.handlers.crud import handle_list

@pytest.mark.django_db
class TestListHandler:
    def test_list_returns_results(self, article_factory):
        # Arrange
        article_factory.create_batch(5)

        # Act
        result = await handle_list("article", {"limit": 10}, request)

        # Assert
        data = json.loads(result[0].text)
        assert len(data["results"]) == 5
```

### 📂 Test Categories

- **Unit tests** — Test individual functions/methods
- **Integration tests** — Test handler + database
- **Permission tests** — Test authorization logic
- **Edge case tests** — Test error handling

### 🏭 Fixtures

Use factory_boy for test data:

```python
@pytest.fixture
def article_factory():
    return ArticleFactory
```

---

## 📖 Documentation

### 🔧 Building Docs Locally

```bash
pip install mkdocs mkdocs-material
mkdocs serve
```

Visit `http://localhost:8000` to preview.

### 📂 Documentation Structure

- `docs/getting-started/` — Installation and setup
- `docs/guide/` — User guides
- `docs/tools/` — Tool reference
- `docs/examples/` — Examples and use cases
- `docs/reference/` — API and settings reference

---

## 🚀 Release Process

Releases are managed by maintainers:

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create release tag
4. CI publishes to PyPI

---

## 💬 Getting Help

- **Issues** — [GitHub Issues](https://github.com/7tg/django-admin-mcp/issues)
- **Discussions** — [GitHub Discussions](https://github.com/7tg/django-admin-mcp/discussions)

---

## 🤝 Code of Conduct

Be respectful and constructive. We're all here to build something great together.

---

Thank you for contributing!
