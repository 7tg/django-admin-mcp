# django-admin-mcp

A Django package that exposes Django admin models to MCP (Model Context Protocol) clients, allowing programmatic access to your Django admin interface through both stdio and HTTP interfaces.

## Documentation

📚 **[API Documentation](https://7tg.github.io/django-admin-mcp/)** - Interactive API documentation with Redoc

## Features

- **Easy Integration**: Add a simple mixin to your ModelAdmin classes
- **HTTP & Stdio Interfaces**: Use MCP via HTTP API or stdio for maximum flexibility
- **Token Authentication**: Secure HTTP interface with token-based authentication
- **Search Functionality**: Built-in find tool for searching across text fields
- **Opt-in Exposure**: Control which models expose MCP tools with `mcp_expose` attribute
- **Automatic Tool Registration**: Automatically creates MCP tools for CRUD operations
- **Type-Safe**: Built with proper type hints and schema definitions

## Installation

```bash
pip install django-admin-mcp
```

## Configuration

### 1. Add to INSTALLED_APPS

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'django_admin_mcp',
    # your apps
]
```

### 2. Add URL patterns (for HTTP interface)

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    # ...
    path('api/', include('django_admin_mcp.urls')),
]
```

### 3. Run migrations

```bash
python manage.py migrate
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
    mcp_expose = True  # Enable MCP tools for this model

@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'email']
    mcp_expose = True  # Enable MCP tools for this model
```

**Important**: Only models with `mcp_expose = True` will expose MCP tools. This is a security feature to prevent accidental exposure of sensitive models.

## Usage

### HTTP Interface (Recommended)

The HTTP interface allows you to use MCP over standard HTTP requests with token authentication.

#### 1. Create an MCP Token

Create a token via Django admin at `/admin/django_admin_mcp/mcptoken/`:

1. Go to Django admin
2. Navigate to "MCP Tokens"
3. Click "Add MCP Token"
4. Enter a name (e.g., "Production API")
5. **Optional**: Set an expiration date or leave empty for an indefinite token (default: 90 days)
6. Save and copy the generated token

**Token Expiry:**
- By default, new tokens expire after 90 days
- To create an indefinite token, clear the "Expires at" field when creating the token
- Expired tokens are automatically rejected during authentication
- The admin interface shows token status with color coding (Active, Expires in X days, Expired)

#### 2. Make HTTP Requests

**List Available Tools:**

```bash
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'
```

**Call a Tool:**

```bash
# Discover available models
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "find_models",
    "arguments": {}
  }'

# List articles (requires mcp_expose=True)
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "list_article",
    "arguments": {"limit": 10, "offset": 0}
  }'
```

### Stdio Interface

For stdio-based MCP clients, create a management command:

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

### Model Discovery

The `find_models` tool is always available to discover which Django models are registered:

**Discover all models:**
```json
{
    "method": "tools/call",
    "name": "find_models",
    "arguments": {}
}
```

**Search for specific models:**
```json
{
    "method": "tools/call",
    "name": "find_models",
    "arguments": {
        "query": "article"
    }
}
```

This returns information about available models including their names, verbose names, and whether their tools are exposed.

### Model-Specific Tools

For each model with `MCPAdminMixin` and `mcp_expose = True`, the following CRUD tools are available:

- `list_<model_name>`: List all instances with pagination
- `get_<model_name>`: Get a specific instance by ID
- `create_<model_name>`: Create a new instance
- `update_<model_name>`: Update an existing instance
- `delete_<model_name>`: Delete an instance

### Example Usage

**List articles:**
```json
{
    "method": "tools/call",
    "name": "list_article",
    "arguments": {
        "limit": 10,
        "offset": 0
    }
}
```

**Get a specific article:**
```json
{
    "method": "tools/call",
    "name": "get_article",
    "arguments": {
        "id": 1
    }
}
```

**Create a new article:**
```json
{
    "method": "tools/call",
    "name": "create_article",
    "arguments": {
        "data": {
            "title": "My New Article",
            "content": "Article content here",
            "author_id": 1
        }
    }
}
```

**Update an article:**
```json
{
    "method": "tools/call",
    "name": "update_article",
    "arguments": {
        "id": 1,
        "data": {
            "title": "Updated Title"
        }
    }
}
```

**Delete an article:**
```json
{
    "method": "tools/call",
    "name": "delete_article",
    "arguments": {
        "id": 1
    }
}
```

## Security

### Token Management

- Tokens are automatically generated with secure random values
- **Token Expiry**: By default, tokens expire after 90 days for security
- **Indefinite Tokens**: You can create tokens without expiry by clearing the expiration date
- Tokens can be enabled/disabled via the `is_active` field
- Token usage is tracked with `last_used_at` timestamp
- Each token has a descriptive name for easy identification

### Opt-in Tool Exposure

By default, models with `MCPAdminMixin` do **not** expose their CRUD tools. You must explicitly set `mcp_expose = True` in your admin class. This provides several benefits:

- **Security**: Prevents accidental exposure of sensitive models
- **Context Window Efficiency**: Only exposes tools when needed, reducing LLM token usage
- **Progressive Disclosure**: Use `find_models` to discover what's available, then expose only what's needed

```python
@admin.register(SensitiveModel)
class SensitiveModelAdmin(MCPAdminMixin, admin.ModelAdmin):
    # mcp_expose is False by default
    # This model can be discovered via find_models but tools are NOT exposed
    pass

@admin.register(PublicModel)
class PublicModelAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Explicitly enable
    # This model's CRUD tools WILL be exposed
    pass
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
    mcp_expose = True
    
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

1. **Mixin Integration**: When you add `MCPAdminMixin` to a `ModelAdmin` class, it automatically registers that model with MCP
2. **Model Discovery**: The `find_models` tool is always available to discover registered models
3. **Opt-in Tool Exposure**: Only models with `mcp_expose = True` expose their full CRUD tools
4. **Reduced Context**: By default, only the discovery tool is exposed, minimizing LLM context window usage
5. **Tool Registration**: Each exposed model gets 5 CRUD tools: list, get, create, update, and delete
6. **Schema Generation**: Tool schemas are automatically generated from model field definitions
7. **Request Handling**: When an MCP client calls a tool, the request is routed to the appropriate handler which performs the database operation
8. **Authentication**: HTTP requests are authenticated using Bearer tokens stored in the database

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
- Find/search functionality
- HTTP interface and token authentication
- Opt-in tool exposure
- Error handling and field validation
- Async database operations

See `tests/README.md` for more details.

## License

GPL-3.0-or-later - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
