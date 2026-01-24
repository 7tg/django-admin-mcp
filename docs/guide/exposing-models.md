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

Use `readonly_fields` for computed or sensitive fields:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    readonly_fields = ['password', 'last_login', 'date_joined']
```

## Next Steps

- [Token Management](tokens.md) - Configure access tokens
- [Permissions](permissions.md) - Understand the permission system
- [Tools Reference](../tools/overview.md) - Explore all available tools
