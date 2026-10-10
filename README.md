[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/7tg-django-admin-mcp-badge.png)](https://mseep.ai/app/7tg-django-admin-mcp)

# django-admin-mcp

[![PyPI version](https://img.shields.io/pypi/v/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![PyPI downloads](https://img.shields.io/pypi/dm/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-admin-mcp.svg)](https://pypi.org/project/django-admin-mcp/)
[![Django](https://img.shields.io/badge/django-3.2%20%7C%204.x%20%7C%205.x%20%7C%206.0-092E20.svg?logo=django)](https://www.djangoproject.com/)
[![Tests](https://github.com/7tg/django-admin-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/7tg/django-admin-mcp/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/7tg/django-admin-mcp/graph/badge.svg)](https://codecov.io/gh/7tg/django-admin-mcp)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://7tg.github.io/django-admin-mcp/)
[![License](https://img.shields.io/pypi/l/django-admin-mcp.svg)](https://github.com/7tg/django-admin-mcp/blob/main/LICENSE)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-io.github.7tg%2Fdjango--admin--mcp-6E56CF.svg)](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.7tg/django-admin-mcp&version=latest)

Add a mixin to your `ModelAdmin` and MCP clients get CRUD, admin actions and relationship traversal, inside Django's existing permissions. Only Django and Pydantic as dependencies.

<!-- mcp-name: io.github.7tg/django-admin-mcp -->

[![Meet django-admin-mcp: one mixin turns a ModelAdmin into MCP tools, every call goes through the admin's permissions, validation and audit log, one token per user, a conversation with the agent, and how to get started](https://raw.githubusercontent.com/7tg/django-admin-mcp/main/docs/media/demo.gif)](https://github.com/7tg/django-admin-mcp/blob/main/docs/media/demo.mp4)

<sub>One mixin, the request's path through the admin, a token, a conversation with the agent, then getting started. 50 seconds · 1080p · 60 fps · original soundtrack. [Watch the film](https://github.com/7tg/django-admin-mcp/blob/main/docs/media/demo.mp4).</sub>

## Why not just give the agent database access?

A database connection hands the agent raw tables. The Django admin is where your project already encodes who may touch what, how records are validated, and what the sanctioned bulk operations are. This package puts the agent behind that layer instead of around it:

- **Permissions** — every call goes through `ModelAdmin.has_*_permission()`. A token can only do what its linked user can do, and starts with no access until you grant it.
- **Validation** — writes run `full_clean()` and your `save_model()` / `save_related()` hooks, so the agent cannot save a record the admin form would reject.
- **Audit history** — every create, update, delete and action is written to Django's `LogEntry` under the token's user. You can see what the agent changed, and the agent can read the history too.
- **Admin actions** — "publish", "refund", "export CSV" and your other registered actions become tools, including two-step confirmation flows. The agent uses the operations you designed rather than inventing SQL.
- **Scoped exposure** — `mcp_fields` / `mcp_exclude_fields` keep password hashes and secrets out of the agent's view; `get_queryset()` still limits which rows it can see.

## How it compares

A generic Django MCP server or a hand-rolled FastMCP wrapper asks you to define tools, schemas and permission checks yourself, one function at a time. This package reads the `ModelAdmin` classes you already maintain and generates the tools from them, so field choices, querysets, validation, actions and permissions stay in one place and the agent inherits every change you make to the admin. It also ships as a plain Django app with no MCP SDK or extra HTTP stack.

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
    path('mcp/', include('django_admin_mcp.urls')),
    # ...
]
```

```bash
python manage.py migrate django_admin_mcp
```

## Quick start

**1. Expose a model.** Set `mcp_expose = True` to generate tools for it. Models with the mixin but without the flag are discoverable through `find_models` only.

```python
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article, Author

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True                    # list_article, get_article, create_article, ...
    mcp_exclude_fields = ['internal_notes']
    list_display = ['title', 'author', 'published']

@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass                                 # discoverable, no direct tools
```

**2. Create a token** in the admin at `/admin/django_admin_mcp/mcptoken/`. Grant it exactly the permissions and groups the agent needs. The linked user caps what the token can do and is the identity its changes are logged under.

**3. Point your MCP client at it**, for example in a `.mcp.json` for Claude Code:

```json
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

**4. Ask the agent.**

```
User: Show me the latest 10 articles
Agent: [calls list_article with limit=10]

User: Mark articles 1, 2 and 3 as published
Agent: [calls action_article with action="mark_as_published", ids=[1, 2, 3]]

User: What changed on article 42?
Agent: [calls history_article with id=42]
```

## Tools

For each exposed model (here `Article`) the server generates:

| Tool | Does |
|------|------|
| `list_article`, `get_article` | Read with pagination and filtering (needs **view**) |
| `create_article`, `update_article`, `delete_article` | Write single records (needs **add** / **change** / **delete**) |
| `bulk_article` | Create, update or delete many records at once |
| `actions_article`, `action_article` | List and run registered admin actions, including file-returning exports |
| `describe_article` | Field definitions, types and constraints |
| `related_article` | Follow foreign keys and reverse relations |
| `history_article` | Django admin change history |
| `autocomplete_article` | Search suggestions for foreign-key fields |

Plus `find_models` to discover everything exposed, MCP prompts for common workflows, and read-only resources at `models://` and `data://` URIs. The endpoint speaks JSON-RPC 2.0 over HTTP with `GET /mcp/health/` for health checks. Full reference in the [docs](https://7tg.github.io/django-admin-mcp/).

## Security in brief

- Tokens look like `mcp_<key>.<secret>`; only a salted hash of the secret is stored.
- Each token carries its own permissions and groups, intersected with its user's permissions. Deactivating the user disables its tokens.
- Expiry is configurable; revoke a token by deactivating or deleting it in the admin.
- Sensitive values are redacted from log messages, and large action downloads are capped by `MCP_ACTION_MAX_FILE_BYTES` (default 5 MiB).

See [Permissions](https://7tg.github.io/django-admin-mcp/guide/permissions/) and [Token Management](https://7tg.github.io/django-admin-mcp/guide/tokens/) for details.

## Requirements

Python 3.10 to 3.14, Django 3.2 to 6.0, Pydantic 2. Tested against every Django release in that range.

## Support the project

If this saved you time, a star on GitHub helps others find it. Issues and PRs are welcome; see the [contributing guide](https://7tg.github.io/django-admin-mcp/contributing/).

[![Star History Chart](https://api.star-history.com/svg?repos=7tg/django-admin-mcp&type=Date)](https://star-history.com/#7tg/django-admin-mcp&Date)

## License

MIT
