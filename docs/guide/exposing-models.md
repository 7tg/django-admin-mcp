# Exposing Models

This guide explains how to expose Django models via the MCP protocol using `MCPAdminMixin`.

## Basic Usage

Add `MCPAdminMixin` to any ModelAdmin class:

```python title="admin.py"
from django.contrib import admin
from django_admin_mcp import MCPAdminMixin
from .models import Article

@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
```

## Two-Level Exposure System

Django Admin MCP uses a two-level exposure system:

### Level 1: Discoverable Models

Models with `MCPAdminMixin` (but without `mcp_expose = True`) are **discoverable**:

```python
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass  # Discoverable via find_models, no direct tools
```

These models:

- Appear in `find_models` results
- Show their field structure
- Do NOT expose direct CRUD tools

### Level 2: Fully Exposed Models

Models with `mcp_expose = True` are **fully exposed**:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Full tool set exposed
```

These models expose 12 tools:

| Tool | Permission | Description |
|------|------------|-------------|
| `list_<model>` | view | List instances with pagination/filtering |
| `get_<model>` | view | Get single instance by ID |
| `create_<model>` | add | Create new instance |
| `update_<model>` | change | Update existing instance |
| `delete_<model>` | delete | Delete instance |
| `describe_<model>` | view | Get field definitions |
| `actions_<model>` | view | List available admin actions |
| `action_<model>` | varies | Execute admin action |
| `bulk_<model>` | varies | Bulk create/update/delete |
| `related_<model>` | view | Get related objects |
| `history_<model>` | view | View change history |
| `autocomplete_<model>` | view | Search suggestions |

## Mixin Placement

!!! important "Mixin Order Matters"
    `MCPAdminMixin` should come **before** `admin.ModelAdmin` in the inheritance chain:

```python
# Correct
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass

# Also correct with other mixins
class ArticleAdmin(MCPAdminMixin, SomeOtherMixin, admin.ModelAdmin):
    pass
```

## Configuring Exposed Behavior

### List Display and Serialization

Fields in `list_display` are included in list responses:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ['title', 'author', 'published', 'created_at']
```

### Search Configuration

`search_fields` enables the search parameter in `list_*` and powers `autocomplete_*`:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['title', 'content', 'author__name']
```

### Ordering

`ordering` sets the default order for list results:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    ordering = ['-created_at']  # Newest first
```

### Readonly Fields

`readonly_fields` are excluded from create/update operations:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    readonly_fields = ['created_at', 'updated_at', 'view_count']
```

### Field Filtering

Control which fields are exposed in MCP responses using field filtering. This is critical for preventing sensitive data exposure.

#### MCP-Specific Field Control

Use `mcp_fields` and `mcp_exclude_fields` for MCP-specific field visibility:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Only expose these fields via MCP
    mcp_fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active']
    # Never expose password, even though it exists in the model
```

Alternatively, exclude specific fields:

```python
class APIKeyAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Exclude sensitive fields from MCP responses
    mcp_exclude_fields = ['secret_key', 'api_token', 'private_data']
```

#### Django Admin Field Fallback

If `mcp_fields` or `mcp_exclude_fields` are not set, django-admin-mcp falls back to Django admin's `fields` and `exclude` attributes:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    fields = ['title', 'content', 'author', 'published']  # Used if mcp_fields not set
```

#### Field Filtering Rules

1. **MCP-specific takes precedence**: If `mcp_fields` is set, it overrides `fields`
2. **MCP-specific exclusion takes precedence**: If `mcp_exclude_fields` is set, it overrides `exclude`
3. **Exclusion wins over inclusion**: If a field is in both `mcp_fields` and `mcp_exclude_fields`, it's excluded
4. **No configuration = all fields**: If no field configuration is provided, all model fields are exposed

#### Example: Protecting Sensitive Data

```python
from django_admin_mcp import MCPAdminMixin

@admin.register(MCPToken)
class MCPTokenAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Never expose token credentials via MCP
    mcp_exclude_fields = ['token_key', 'token_hash', 'salt']
    
    list_display = ['name', 'user', 'is_active', 'created_at']
    readonly_fields = ['token_key', 'token_hash', 'salt']  # Also readonly in admin
```

When listing or getting tokens via MCP, sensitive fields are automatically filtered out:

```json
{
  "id": 1,
  "name": "Production API Token",
  "user": 1,
  "is_active": true,
  "expires_at": "2026-04-24T16:48:36Z"
  // token_key, token_hash, and salt are NOT included
}
```

### Custom Actions

Admin actions are automatically exposed:

```python
@admin.action(description='Mark as published')
def publish(modeladmin, request, queryset):
    queryset.update(published=True)

@admin.action(description='Mark as draft')
def unpublish(modeladmin, request, queryset):
    queryset.update(published=False)

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [publish, unpublish]
```

## Inline Models

Inline models are included in `get_*` responses:

```python
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    inlines = [CommentInline]
```

When fetching an article, its comments are included:

```json
{
  "id": 1,
  "title": "My Article",
  "comments": [
    {"id": 1, "text": "Great article!"},
    {"id": 2, "text": "Thanks for sharing"}
  ]
}
```

## Best Practices

### Start Conservative

Begin with discoverable models, then expose as needed:

```python
# Start with discovery only
class SensitiveDataAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass  # Can see structure, but no direct access

# Later, if needed:
class SensitiveDataAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
```

### Use Meaningful Search Fields

Configure search fields for useful autocomplete:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['username', 'email', 'first_name', 'last_name']
```

### Protect Sensitive Fields

Use `mcp_exclude_fields` to prevent sensitive data exposure:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Never expose password or sensitive authentication data
    mcp_exclude_fields = ['password', 'security_token', 'api_secret']
    readonly_fields = ['password', 'last_login', 'date_joined']
```

For models with many fields, use `mcp_fields` to explicitly allowlist safe fields:

```python
class CustomerAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Only expose non-sensitive customer data
    mcp_fields = ['id', 'name', 'email', 'company', 'created_at']
    # This excludes: credit_card, ssn, internal_notes, etc.
```

## Next Steps

- [Token Management](tokens.md) - Configure access tokens
- [Permissions](permissions.md) - Understand the permission system
- [Tools Reference](../tools/overview.md) - Explore all available tools
