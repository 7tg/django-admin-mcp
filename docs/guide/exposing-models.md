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

### Level 1 — Discoverable Models

Models with `MCPAdminMixin` (but without `mcp_expose = True`) are **discoverable**:

```python
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    pass  # Discoverable via find_models, no direct tools
```

These models:

- Appear in `find_models` results with `tools_exposed: false` (filtered by module and `view` permission)
- Show their field structure
- Are not advertised in `tools/list`

!!! warning "`mcp_expose` controls advertisement, not reachability"
    Registering a model with the mixin makes its handlers callable: a client that explicitly issues `tools/call` for `list_author` will get a response even without `mcp_expose = True`. Django permissions are the enforcement boundary — do not rely on `mcp_expose` to protect data.

### Level 2 — Fully Exposed Models

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
| `action_<model>` | change | Execute admin action |
| `bulk_<model>` | varies | Bulk create/update/delete |
| `related_<model>` | view | Get related objects |
| `history_<model>` | view | View change history |
| `autocomplete_<model>` | view | Search suggestions |

!!! note
    `tools/list` itself is not permission-filtered — tools for models the caller cannot access are still advertised and fail with a permission error at call time.

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

### List Display

`list_display` is reported by `describe_<model>` as admin metadata. It does **not** change which fields `list_<model>` returns — use `mcp_fields`/`mcp_exclude_fields` for that:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ['title', 'author', 'published', 'created_at']
```

### Search Configuration

`search_fields` controls which fields `autocomplete_*` searches. Without it, all `CharField`/`TextField` fields are searched:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['title', 'content']
```

### Queryset Scoping

By default (`mcp_use_admin_queryset = True`), `list_*`, `get_*`, admin actions, and bulk operations start from `ModelAdmin.get_queryset(request)` — proxy filters, soft-delete, and multi-tenant scoping match the admin changelist. Set it to `False` to use `model.objects.all()` instead:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    mcp_use_admin_queryset = False  # bypass get_queryset() scoping
```

### Ordering

`ordering` sets the default order for list results:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    ordering = ['-created_at']  # Newest first
```

### Readonly Fields

Attempts to update `readonly_fields` return an error:

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
    mcp_fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
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

1. **MCP-specific takes precedence** — If `mcp_fields` is set, it overrides `fields`
2. **MCP-specific exclusion takes precedence** — If `mcp_exclude_fields` is set, it overrides `exclude`
3. **Exclusion wins over inclusion** — If a field is in both `mcp_fields` and `mcp_exclude_fields`, it's excluded
4. **No configuration = all fields** — If no field configuration is provided, all model fields are exposed

!!! note "Non-editable fields are always excluded"
    Serialization uses Django's `model_to_dict()`, which skips every `editable=False` field — including auto primary keys, `auto_now_add`/`auto_now` timestamps, and any field declared `editable=False`. This means `list_*`/`get_*` payloads do **not** contain an `id` key; use `get_*`'s input `id` (or `create_*`'s returned `id`) to track object identity. Regular date fields like `expires_at` are included normally.

#### Example — Protecting Sensitive Data

```python
from django_admin_mcp import MCPAdminMixin

@admin.register(Customer)
class CustomerAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    # Never expose payment credentials via MCP
    mcp_exclude_fields = ['card_number', 'internal_notes']

    list_display = ['name', 'email', 'is_active']
```

When listing or getting customers via MCP, excluded fields are filtered out:

```json
{
  "name": "Acme Corp",
  "email": "billing@acme.example",
  "is_active": true,
  "tags": [1, 3]
}
```

Foreign keys serialize as bare primary keys and many-to-many fields as lists of primary keys. `card_number` and `internal_notes` are not included; neither are non-editable fields such as the auto primary key or `auto_now_add` timestamps.

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

Inline models are included in `get_*` responses when `include_inlines` is set to `true`:

```python
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    inlines = [CommentInline]
```

When fetching an article with `include_inlines: true`, its comments are included under the `_inlines` key, grouped by the inline model's lowercase name:

```json
{
  "title": "My Article",
  "_inlines": {
    "comment": [
      {"text": "Great article!"},
      {"text": "Thanks for sharing"}
    ]
  }
}
```

Inlines can also be created, updated, and deleted through `update_<model>`'s `inlines` parameter — see [CRUD Operations](../tools/crud.md).

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
    mcp_fields = ['name', 'email', 'company']
    # This excludes: credit_card, ssn, internal_notes, etc.
```

## Next Steps

- [Token Management](tokens.md) — Configure access tokens
- [Permissions](permissions.md) — Understand the permission system
- [Tools Reference](../tools/overview.md) — Explore all available tools
