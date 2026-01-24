# Django Admin MCP

Expose Django admin models to MCP (Model Context Protocol) clients via HTTP. Add a mixin to your ModelAdmin classes and get instant access to CRUD operations, admin actions, model history, and more.

## Features

<div class="grid cards" markdown>

- :package: **Zero Dependencies**

    ---

    Beyond Django and Pydantic, no additional dependencies required.

- :ticket: **Token Authentication**

    ---

    Secure Bearer token auth with configurable expiry (default 90 days).

- :shield: **Django Admin Permissions**

    ---

    Respects existing view/add/change/delete permissions.

- :pencil: **Full CRUD**

    ---

    List, get, create, update, delete operations for all exposed models.

- :zap: **Admin Actions**

    ---

    Execute registered Django admin actions on selected records.

- :package: **Bulk Operations**

    ---

    Update or delete multiple records at once.

- :mag: **Model Introspection**

    ---

    Describe model fields and relationships programmatically.

- :link: **Related Objects**

    ---

    Traverse foreign keys and reverse relations.

- :scroll: **Change History**

    ---

    Access Django admin's history log for audit trails.

- :mag_right: **Autocomplete**

    ---

    Search suggestions for foreign key fields.

</div>

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
| Django 3.2 LTS | :white_check_mark: Supported |
| Django 4.0 | :white_check_mark: Supported |
| Django 4.1 | :white_check_mark: Supported |
| Django 4.2 LTS | :white_check_mark: Supported |
| Django 5.0 | :white_check_mark: Supported |

## License

GPL-3.0-or-later

---

Ready to get started? Check out the [Installation Guide](getting-started/installation.md) or jump straight to the [Quick Start](getting-started/quick-start.md).
