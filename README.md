# django-admin-mcp

[![Stable](https://img.shields.io/badge/status-stable-brightgreen.svg)](https://github.com/7tg/django-admin-mcp)
[![PyPI version](https://img.shields.io/pypi/v/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![Django](https://img.shields.io/badge/django-3.2%20%7C%204.x%20%7C%205.x-092E20.svg?logo=django)](https://www.djangoproject.com/)
[![Tests](https://github.com/7tg/django-admin-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/7tg/django-admin-mcp/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/7tg/django-admin-mcp/graph/badge.svg)](https://codecov.io/gh/7tg/django-admin-mcp)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://docs.pydantic.dev)
[![Typed: mypy](https://img.shields.io/badge/typed-mypy-blue.svg)](https://mypy-lang.org/)
[![Django Packages](https://img.shields.io/badge/Django%20Packages-django--admin--mcp-8c3c26.svg)](https://djangopackages.org/packages/p/django-admin-mcp/)
[![License](https://img.shields.io/pypi/l/django-admin-mcp.svg)](https://github.com/7tg/django-admin-mcp/blob/main/LICENSE)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://7tg.github.io/django-admin-mcp/)

Expose Django admin models to MCP (Model Context Protocol) clients via HTTP. Add a mixin to your `ModelAdmin` classes and get instant access to CRUD operations, admin actions, model history, and more.

---

## Features

- **Only two dependencies** — Django and Pydantic, nothing else. No MCP SDK, no extra HTTP stack, no supply-chain sprawl
- **Token authentication** — secure Bearer token auth with configurable expiry
- **Django admin permissions** — respects existing view/add/change/delete permissions
- **Field filtering** — control which fields are exposed via `mcp_fields` and `mcp_exclude_fields`
- **Full CRUD** — list, get, create, update, delete operations
- **Admin actions** — execute registered Django admin actions, including two-step confirmation flows
- **Bulk operations** — create, update, or delete multiple records at once
- **Model introspection** — describe model fields and relationships
- **Related objects** — traverse foreign keys and reverse relations
- **Change history** — access Django admin's history log
- **Autocomplete** — search suggestions for foreign key fields
- **MCP Prompts & Resources** — workflow guides plus read-only data access via `models://` and `data://` URIs

---

<!-- mcp-name: io.github.7tg/django-admin-mcp -->

## Installation

```bash
pip install django-admin-mcp
```

Add to your Django project:

```python
# settings.py
INSTALLED_APPS = [
    'django_admin_mcp',
    # ...
]

# urls.py
from django.urls import path, include

urlpatterns = [
    path('mcp/', include('django_admin_mcp.urls')),
    # ...
]
```

Run migrations to create the token model:

```bash
python manage.py migrate django_admin_mcp
```

---

## Quick Start

### 1. Expose Your Models

Add the mixin to any `ModelAdmin`. Set `mcp_expose = True` to expose direct tools:

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article, Author

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Exposes list_article, get_article, etc.
    list_display = ['title', 'author', 'published']

@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass  # Discoverable via find_models, no direct tools
```

#### Protecting Sensitive Fields

Use `mcp_exclude_fields` to prevent sensitive data exposure:

```python
@admin.register(User)
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Never expose sensitive fields via MCP
    mcp_exclude_fields = ['password', 'security_token']
```

### 2. Create an API Token

Go to Django admin at `/admin/django_admin_mcp/mcptoken/` and create a token. Grant the token exactly the permissions the agent needs via its **Permissions** and **Groups** fields — tokens start with no access. The linked user caps the token (it can never exceed that user's permissions) and is the audit identity actions are logged under.

### 3. Configure Your MCP Client

Add to your MCP client settings (e.g. a project `.mcp.json` for Claude Code):

```json
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

### 4. Use with Your Agent

Once configured, the agent can use the tools directly:

```
User: What models are available in Django admin?
Agent: [calls find_models tool]

User: Show me the latest 10 articles
Agent: [calls list_article with limit=10]

User: Get article #42 and update its title to "New Title"
Agent: [calls get_article with id=42, then update_article]
```

---

## Available Tools

For each exposed model (e.g., `Article`), the following tools are generated:

### CRUD Operations

| Tool | Description |
|------|-------------|
| `list_article` | List all articles with pagination (`limit`, `offset`) and filtering |
| `get_article` | Get a single article by `id` |
| `create_article` | Create a new article with field values |
| `update_article` | Update an existing article by `id` |
| `delete_article` | Delete an article by `id` |

### Model Introspection

| Tool | Description |
|------|-------------|
| `find_models` | Discover all exposed models and their available tools |
| `describe_article` | Get field definitions, types, and constraints |

### Admin Actions

| Tool | Description |
|------|-------------|
| `actions_article` | List available admin actions for the model |
| `action_article` | Execute an admin action on selected records |
| `bulk_article` | Bulk create, update, or delete multiple records |

### Relationships

| Tool | Description |
|------|-------------|
| `related_article` | Get related objects via foreign keys |
| `history_article` | View Django admin change history |
| `autocomplete_article` | Search suggestions for autocomplete fields |

---

## HTTP Protocol Reference

For custom integrations, the MCP endpoint accepts JSON-RPC 2.0 POST requests:

```bash
# List available tools
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'

# Call a tool
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_article", "arguments": {"limit": 10}}}'
```

Supported methods: `initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, `resources/list`, `resources/templates/list`, and `resources/read`. A `GET /mcp/health/` endpoint is available for health checks.

---

## Example Conversations

### CRUD Operations

```
User: Create a new article titled "Getting Started with Django"

Agent: I'll create that article for you.
[calls create_article with title="Getting Started with Django"]
Created article #15: "Getting Started with Django"

User: Update article 15 to add content

Agent: [calls update_article with id=15, content="..."]
Updated article #15 successfully.

User: Delete article 15

Agent: [calls delete_article with id=15]
Deleted article #15.
```

### Admin Actions

```
User: Mark articles 1, 2, and 3 as published

Agent: [calls action_article with action="mark_as_published", ids=[1,2,3]]
Marked 3 articles as published.
```

When an admin action returns a Django `HttpResponse` / `StreamingHttpResponse` (typical for CSV/TSV/PDF downloads), `action_<model>` serializes the body instead of `str(response)`:

```json
{
  "success": true,
  "action": "export_csv",
  "affected_count": 2,
  "result": {
    "type": "file",
    "encoding": "utf-8",
    "content_type": "text/csv; charset=utf-8",
    "filename": "export.csv",
    "content_disposition": "attachment; filename=\"export.csv\"",
    "size": 10,
    "status_code": 200,
    "content": "a,b\r\n1,2\r\n"
  }
}
```

Text-ish content types (`text/*`, `application/json`, …) decode using the `Content-Type` charset (or `response.charset`, default UTF-8) and return `"encoding": "utf-8"` with Unicode text in `content`. If that decode fails (unknown charset or invalid bytes), the payload falls back to `"encoding": "base64"` like binary downloads. Binary payloads use `"encoding": "base64"` with ASCII base64 in `content`.

Large downloads are rejected once the body exceeds `MCP_ACTION_MAX_FILE_BYTES` (default 5 MiB) to protect MCP transports.

### Bulk Operations

```
User: Set status to "archived" for articles 10-15

Agent: [calls bulk_article with operation="update", ids=[10,11,12,13,14,15], data={"status": "archived"}]
Updated 6 articles.

User: Delete all draft articles from last month

Agent: [calls list_article to find drafts, then bulk_article with operation="delete"]
Deleted 12 draft articles.
```

### Exploring Relationships

```
User: Show me all comments on article 42

Agent: [calls related_article with id=42, relation="comments"]
Found 8 comments on article #42...

User: What changes were made to article 42?

Agent: [calls history_article with id=42]
Change history for article #42:
- 2024-01-15: Changed title (admin)
- 2024-01-10: Created (admin)
```

### Model Discovery

```
User: What can I manage through MCP?

Agent: [calls find_models]
Available models:
- article (5 tools: list, get, create, update, delete)
- author (5 tools: list, get, create, update, delete)
- category (5 tools: list, get, create, update, delete)

User: What fields does article have?

Agent: [calls describe_article]
Article fields:
- id (AutoField, read-only)
- title (CharField, max_length=200, required)
- content (TextField, optional)
- author (ForeignKey to Author, required)
- published (BooleanField, default=False)
- created_at (DateTimeField, auto)
```

---

## Security

### Two-Level Exposure

Models with `MCPAdminMixin` are automatically discoverable via the `find_models` tool, allowing the agent to see what's available. To expose full CRUD tools directly, set `mcp_expose = True`:

```python
# Discoverable via find_models only
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass

# Full tools exposed (list_article, get_article, etc.)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
```

### Token Authentication

- Tokens are created in Django admin (format: `mcp_<key>.<secret>`; only a salted hash of the secret is stored)
- Each token carries its own permissions and groups, capped by the linked Django user's permissions: a token can narrow its user's access but never exceed it
- Tokens start with no permissions (principle of least privilege); even a superuser-bound token has no access until granted
- The linked user is also the audit identity actions are logged under; deactivating the user disables all its tokens' access
- Token expiry is configurable (blank in the admin form = never expires; programmatic creation defaults to 90 days)
- Revoke tokens by deactivating or deleting them in admin

### Permission Checking

All operations go through `ModelAdmin.has_*_permission()`, answered from the token's effective permissions (its grants intersected with the linked user's permissions):

| Operation | Required Permission |
|-----------|-------------------|
| `list_*` / `get_*` | **view** |
| `create_*` | **add** |
| `update_*` | **change** |
| `delete_*` | **delete** |

If the token lacks the permission, the operation returns an error.

---

## Requirements

| Dependency | Version |
|-----------|---------|
| Python | >= 3.10 |
| Django | >= 3.2 |
| Pydantic | >= 2.0 |

### Supported Django Versions

Django 3.2 · 4.0 · 4.1 · 4.2 · 5.0

---

## License

MIT
