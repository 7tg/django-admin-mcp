# Django Admin MCP

Expose Django admin models to MCP (Model Context Protocol) clients via HTTP. Add a mixin to your ModelAdmin classes and get instant access to CRUD operations, admin actions, model history, and more.

## Features

- 📦 **Zero Dependencies** - Beyond Django and Pydantic, no additional dependencies required.
- 🎫 **Token Authentication** - Secure Bearer token auth with configurable expiry (default 90 days).
- 🛡️ **Django Admin Permissions** - Respects existing view/add/change/delete permissions.
- ✏️ **Full CRUD** - List, get, create, update, delete operations for all exposed models.
- ⚡ **Admin Actions** - Execute registered Django admin actions on selected records.
- 📦 **Bulk Operations** - Update or delete multiple records at once.
- 🔍 **Model Introspection** - Describe model fields and relationships programmatically.
- 🔗 **Related Objects** - Traverse foreign keys and reverse relations.
- 📜 **Change History** - Access Django admin's history log for audit trails.
- 🔎 **Autocomplete** - Search suggestions for foreign key fields.

## Quick Example

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Exposes list_article, get_article, etc.
    list_display = ['title', 'author', 'published']
```

Once configured, Claude can use the tools directly:

```
User: Show me the latest 10 articles
Claude: [calls list_article with limit=10]

User: Update article 42 to set published=True
Claude: [calls update_article with id=42, data={"published": true}]
```

## Requirements

- Python >= 3.10
- Django >= 3.2
- Pydantic >= 2.0

## Supported Django Versions

| Django Version | Status |
|----------------|--------|
| Django 3.2 LTS | ✅ Supported |
| Django 4.0 | ✅ Supported |
| Django 4.1 | ✅ Supported |
| Django 4.2 LTS | ✅ Supported |
| Django 5.0 | ✅ Supported |

## License

GPL-3.0-or-later

---

Ready to get started? Check out the [Installation Guide](getting-started/installation.md) or jump straight to the [Quick Start](getting-started/quick-start.md).
