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

### mcp_fields / mcp_exclude_fields

Control which fields are serialized in responses:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    mcp_fields = ['username', 'email', 'is_active']   # allowlist (optional)
    mcp_exclude_fields = ['password', 'security_token']  # denylist, applied last
```

### mcp_use_admin_queryset

When `True` (the default), list/get, actions, and bulk operations start from `ModelAdmin.get_queryset(request)`, matching the admin changelist (proxy filters, soft-delete, multi-tenant scoping). Set to `False` to use `model.objects.all()` instead.

### Standard Django Admin Options

Django Admin MCP respects standard ModelAdmin options:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True

    # Used by list_* tool for default ordering
    ordering = ['-created_at']

    # Used by autocomplete_* tool; without it, all CharField/TextField
    # fields are searched
    search_fields = ['title', 'content']

    # Reported by describe_* as admin metadata (does not change which
    # fields list_* returns — use mcp_fields/mcp_exclude_fields for that)
    list_display = ['title', 'author', 'published', 'created_at']

    # Attempts to update these fields return an error
    readonly_fields = ['created_at', 'updated_at']
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
| `token_key` | Public key for O(1) lookup (auto-generated) | Auto-generated |
| `token_hash` | SHA-256 hash of the secret (auto-generated) | Auto-generated |
| `salt` | Per-token salt for hashing (auto-generated) | Auto-generated |
| `user` | Django user capping the token's access and used for audit logging | Required |
| `is_active` | Enable/disable the token | `True` |
| `expires_at` | Token expiration date | Blank in admin = never; 90 days when omitted in code |
| `groups` | Groups granting permissions to the token | Empty |
| `permissions` | Direct permissions granted to the token | Empty |

Token format: `mcp_<key>.<secret>` — the key is stored in plaintext for lookup, the secret is hashed with a per-token salt.

### Token Expiry

- Leaving **Expires At** blank in the admin form creates a token that never expires
- Programmatic creation without an `expires_at` kwarg defaults to 90 days; pass an explicit `MCPToken(expires_at=None, ...)` for an indefinite token
- Set any datetime for a custom expiration

### Permission Assignment

!!! important "Effective permissions = token grants ∩ user permissions"
    At request time, all checks run through `ModelAdmin.has_*_permission()`, answered from the token's own `permissions` and `groups` capped by the linked user's permissions. A token can narrow its user's access but never exceed it; tokens start with no access, and even a superuser-bound token has none until permissions are granted on the token.

## Optional Django Settings

```python title="settings.py"
# Cap on the page size of list_* tools (default: 1000)
MCP_MAX_LIST_LIMIT = 1000

# Max size of file downloads returned by admin actions (default: 5 MiB)
MCP_ACTION_MAX_FILE_BYTES = 5 * 1024 * 1024
```

See the [Settings Reference](../reference/settings.md) for details.

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

- [Exposing Models](../guide/exposing-models.md) — Detailed model exposure guide
- [Token Management](../guide/tokens.md) — Token lifecycle management
- [Permissions](../guide/permissions.md) — Permission system details
