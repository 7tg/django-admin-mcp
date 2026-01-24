# Configuration

Django Admin MCP is designed to work with minimal configuration. This page covers all available configuration options.

## URL Configuration

The MCP endpoint URL is configurable when including the URLs:

```python title="urls.py"
from django.urls import path, include

urlpatterns = [
    # Default path
    path('mcp/', include('django_admin_mcp.urls')),

    # Or customize the path
    path('api/admin-mcp/', include('django_admin_mcp.urls')),
]
```

## Model Admin Configuration

Each ModelAdmin class with `MCPAdminMixin` can be configured independently:

### mcp_expose

Controls whether direct CRUD tools are exposed:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Expose list_article, get_article, etc.
```

| Value | Behavior |
|-------|----------|
| `True` | Full tool set exposed (12 tools) |
| `False` (default) | Only discoverable via `find_models` |

### Standard Django Admin Options

Django Admin MCP respects standard ModelAdmin options:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True

    # Used by list_* tool for default ordering
    ordering = ['-created_at']

    # Used by list_* tool for search
    search_fields = ['title', 'content']

    # Fields shown in list responses
    list_display = ['title', 'author', 'published', 'created_at']

    # Affects create/update validation
    readonly_fields = ['created_at', 'updated_at']

    # Used by autocomplete_* tool
    search_fields = ['title']  # Required for autocomplete to work
```

### Admin Actions

Custom admin actions are automatically exposed via the `actions_*` and `action_*` tools:

```python
@admin.action(description='Mark selected articles as published')
def mark_as_published(modeladmin, request, queryset):
    queryset.update(published=True)

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [mark_as_published]
```

## Token Configuration

Tokens are configured in Django admin. Each token has:

| Field | Description | Default |
|-------|-------------|---------|
| `name` | Descriptive name for the token | Required |
| `token` | Auto-generated unique token | Auto-generated |
| `user` | Associated Django user (for audit) | Optional |
| `is_active` | Enable/disable the token | `True` |
| `expires_at` | Token expiration date | 90 days from creation |
| `groups` | Django groups for permissions | Empty |
| `permissions` | Direct permission assignments | Empty |

### Token Expiry

By default, tokens expire 90 days after creation. You can:

- Set a custom expiration date
- Leave `expires_at` blank for tokens that never expire

### Permission Assignment

Tokens derive permissions from:

1. **Direct permissions** - Assigned directly to the token
2. **Group permissions** - From groups assigned to the token

!!! note "User Permissions Not Inherited"
    Token permissions are independent of the associated user's permissions. This allows creating limited-access tokens even for superusers.

## Environment-Specific Configuration

For different environments, use Django settings:

```python title="settings.py"
# Production: require HTTPS
SECURE_SSL_REDIRECT = True

# Development: allow HTTP
DEBUG = True
```

The MCP endpoint works over both HTTP and HTTPS. In production, always use HTTPS to protect tokens in transit.

## CORS Configuration

If calling the MCP endpoint from a browser (uncommon), configure CORS:

```python title="settings.py"
INSTALLED_APPS = [
    # ...
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    # ...
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
```

## Next Steps

- [Exposing Models](../guide/exposing-models.md) - Detailed model exposure guide
- [Token Management](../guide/tokens.md) - Token lifecycle management
- [Permissions](../guide/permissions.md) - Permission system details
