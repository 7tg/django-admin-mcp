# django-admin-mcp

A Django package that exposes Django admin models to MCP (Model Context Protocol) clients, allowing programmatic access to your Django admin interface.

## Features

- **Easy Integration**: Add a simple mixin to your ModelAdmin classes
- **Automatic Tool Registration**: Automatically creates MCP tools for CRUD operations
- **Full Admin Access**: Leverage Django's admin interface through code
- **Type-Safe**: Built with proper type hints and schema definitions

## Installation

```bash
pip install django-admin-mcp
```

## Quick Start

### 1. Add the Mixin to Your Admin Classes

```python
# myapp/admin.py
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article, Author

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    list_display = ['title', 'author', 'published_date']
    search_fields = ['title', 'content']

@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'email']
```

### 2. Run the MCP Server

Create a management command or standalone script:

```python
# myapp/management/commands/run_mcp_server.py
from django.core.management.base import BaseCommand
from django_admin_mcp import run_mcp_server
import asyncio

class Command(BaseCommand):
    help = 'Run the MCP server for Django admin'

    def handle(self, *args, **options):
        asyncio.run(run_mcp_server())
```

Then run:

```bash
python manage.py run_mcp_server
```

## Available Tools

For each model with `MCPAdminMixin`, the following tools are automatically created:

- `list_<model_name>`: List all instances with pagination
- `get_<model_name>`: Get a specific instance by ID
- `create_<model_name>`: Create a new instance
- `update_<model_name>`: Update an existing instance
- `delete_<model_name>`: Delete an instance

### Example Usage

```python
# List articles
{
    "tool": "list_article",
    "arguments": {
        "limit": 10,
        "offset": 0
    }
}

# Get a specific article
{
    "tool": "get_article",
    "arguments": {
        "id": 1
    }
}

# Create a new article
{
    "tool": "create_article",
    "arguments": {
        "data": {
            "title": "My New Article",
            "content": "Article content here",
            "author_id": 1
        }
    }
}

# Update an article
{
    "tool": "update_article",
    "arguments": {
        "id": 1,
        "data": {
            "title": "Updated Title"
        }
    }
}

# Delete an article
{
    "tool": "delete_article",
    "arguments": {
        "id": 1
    }
}
```

## Advanced Usage

### Customizing MCP Behavior

You can customize the behavior by overriding methods in your admin class:

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    def get_queryset(self, request):
        # This queryset will be used by MCP tools
        qs = super().get_queryset(request)
        return qs.filter(published=True)
```

### Getting Registered Models

```python
from django_admin_mcp import get_registered_models

models = get_registered_models()
for model_name, model_info in models.items():
    print(f"Model: {model_name}")
    print(f"  Model class: {model_info['model']}")
    print(f"  Admin class: {model_info['admin']}")
```

## How It Works

1. **Mixin Integration**: When you add `MCPAdminMixin` to a `ModelAdmin` class, it automatically registers MCP tools for that model
2. **Tool Registration**: Each model gets 5 CRUD operation tools registered with the MCP server
3. **Schema Generation**: Tool schemas are automatically generated from model field definitions
4. **Request Handling**: When an MCP client calls a tool, the request is routed to the appropriate handler which performs the database operation

## Requirements

- Python >= 3.10
- Django >= 3.2
- mcp >= 0.9.0

## Development

### Running Tests

Install development dependencies:
```bash
pip install -e ".[dev]"
```

Run the test suite:
```bash
pytest
```

Run tests with coverage:
```bash
pytest --cov=django_admin_mcp --cov-report=html
```

The package includes comprehensive tests covering:
- Model registration and tool generation
- CRUD operations
- Error handling and field validation
- Async database operations

See `tests/README.md` for more details.

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
