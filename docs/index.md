# 🤖 Django Admin MCP

Expose Django admin models to MCP (Model Context Protocol) clients via HTTP. Add a mixin to your `ModelAdmin` classes and get instant access to CRUD operations, admin actions, model history, and more.

---

## ✨ Features

- 📦 **Zero Dependencies** — beyond Django and Pydantic, no additional dependencies required
- 🔐 **Token Authentication** — secure Bearer token auth with configurable expiry (default 90 days)
- 🛡️ **Django Admin Permissions** — respects existing view/add/change/delete permissions
- 📝 **Full CRUD** — list, get, create, update, delete operations for all exposed models
- ⚡ **Admin Actions** — execute registered Django admin actions on selected records
- 📦 **Bulk Operations** — create, update, or delete multiple records at once
- 🔍 **Model Introspection** — describe model fields and relationships programmatically
- 🔗 **Related Objects** — traverse foreign keys and reverse relations
- 📜 **Change History** — access Django admin's history log for audit trails
- 🔎 **Autocomplete** — search suggestions for foreign key fields

---

## 🚀 Quick Example

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Exposes list_article, get_article, etc.
    list_display = ['title', 'author', 'published']
```

Once configured, the agent can use the tools directly:

```
User: Show me the latest 10 articles
Agent: [calls list_article with limit=10]

User: Update article 42 to set published=True
Agent: [calls update_article with id=42, data={"published": true}]
```

---

## 📋 Requirements

| Dependency | Version |
|-----------|---------|
| 🐍 Python | >= 3.10 |
| 🌐 Django | >= 3.2 |
| 📐 Pydantic | >= 2.0 |

### ✅ Supported Django Versions

| Django Version | Status |
|----------------|--------|
| Django 3.2 LTS | ✅ Supported |
| Django 4.0 | ✅ Supported |
| Django 4.1 | ✅ Supported |
| Django 4.2 LTS | ✅ Supported |
| Django 5.0 | ✅ Supported |

---

## 📄 License

GPL-3.0-or-later

---

Ready to get started? Check out the [Installation Guide](getting-started/installation.md) or jump straight to the [Quick Start](getting-started/quick-start.md).
