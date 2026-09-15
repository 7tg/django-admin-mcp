# Quick Start

Get Django Admin MCP working in 5 minutes. This guide assumes you've already [installed](installation.md) the package.

## Expose Your Models

Add the `MCPAdminMixin` to any ModelAdmin class. Set `mcp_expose = True` to expose CRUD tools:

```python title="admin.py"
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article, Author

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Exposes list_article, get_article, create_article, etc.
    list_display = ['title', 'author', 'published']
    search_fields = ['title', 'content']

@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    # No mcp_expose = discoverable via find_models but no direct tools
    list_display = ['name', 'email']
```

!!! tip "Two-Level Exposure"
    Models with just `MCPAdminMixin` are discoverable via `find_models` but don't expose direct CRUD tools. Set `mcp_expose = True` to expose the full tool set.

## Create an API Token

1. Go to Django admin: `http://localhost:8000/admin/`
2. Navigate to **Django Admin MCP > MCP Tokens**
3. Click **Add MCP Token**
4. Fill in:
    - **Name**: A descriptive name (e.g., "MCP Token")
    - **User**: The user actions are audit-logged under (its own permissions are not inherited)
    - **Permissions** / **Groups**: What the token is allowed to do — tokens start with no access
5. Click **Save**
6. Copy the generated token (displayed only once after creation)

!!! warning "Token Security"
    The token is only displayed once after creation — store it securely. Access is governed by the permissions and groups assigned to the token itself; grant only what the agent needs (even a superuser-bound token has no access until granted).

## Configure Your MCP Client

Add the MCP server configuration to your MCP client. Create or edit the configuration file:

```json title=".mcp.json"
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

Replace `YOUR_TOKEN_HERE` with the token you created in Step 2. See [Client Setup](../guide/client-setup.md) for other MCP clients.

## Start Using It

Restart your MCP client to load the new configuration. Then start interacting:

```
User: What models are available in Django admin?
Agent: [calls find_models tool]
I found the following models:
- article (tools_exposed: true — list_article, get_article, create_article, ...)
- author (tools_exposed: false — discoverable only)

User: Show me the latest 10 articles
Agent: [calls list_article with limit=10]
Here are the 10 most recent articles...

User: Create a new article titled "Getting Started with Django"
Agent: [calls create_article with title="Getting Started with Django"]
Created article #15: "Getting Started with Django"
```

## What's Next?

- [Exposing Models](../guide/exposing-models.md) — Learn about model exposure options
- [Token Management](../guide/tokens.md) — Understand token configuration
- [Tools Reference](../tools/overview.md) — Explore all available tools
