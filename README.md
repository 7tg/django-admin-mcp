# django-admin-mcp

Expose Django admin models to MCP (Model Context Protocol) clients. Add a mixin to your ModelAdmin classes and get instant CRUD tools accessible via HTTP or stdio.

📚 **[API Documentation](https://7tg.github.io/django-admin-mcp/)**

## Installation

```bash
pip install django-admin-mcp
```

```python
# settings.py
INSTALLED_APPS = [
    'django_admin_mcp',
    # ...
]

# urls.py
urlpatterns = [
    path('api/', include('django_admin_mcp.urls')),
]
```

```bash
python manage.py migrate
```

## Usage

Add the mixin to any ModelAdmin and set `mcp_expose = True`:

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Required to expose CRUD tools
```

This creates 5 tools: `list_article`, `get_article`, `create_article`, `update_article`, `delete_article`.

## HTTP API

1. Create a token in Django admin at `/admin/django_admin_mcp/mcptoken/`
2. Make requests:

```bash
# List tools
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'

# Call a tool
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "name": "list_article", "arguments": {"limit": 10}}'
```

## Stdio Interface

```python
# myapp/management/commands/run_mcp_server.py
from django.core.management.base import BaseCommand
from django_admin_mcp import run_mcp_server
import asyncio

class Command(BaseCommand):
    def handle(self, *args, **options):
        asyncio.run(run_mcp_server())
```

## Model Discovery

Use `find_models` to discover available models:

```json
{"method": "tools/call", "name": "find_models", "arguments": {}}
```

## Security

- **Opt-in only**: Models require `mcp_expose = True` to expose tools
- **Token auth**: HTTP requests require Bearer tokens (90-day default expiry)
- **Discovery-first**: Use `find_models` to see what's available without exposing tools

## Requirements

- Python >= 3.10
- Django >= 3.2
- mcp >= 0.9.0

## License

GPL-3.0-or-later
