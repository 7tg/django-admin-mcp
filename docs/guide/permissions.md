# Permissions

Django Admin MCP integrates with Django's permission system. Every operation checks permissions before execution.

## How Permissions Work

### Permission Requirements by Operation

| Operation | Required Permission |
|-----------|---------------------|
| `list_*` | `view_<model>` |
| `get_*` | `view_<model>` |
| `describe_*` | `view_<model>` |
| `create_*` | `add_<model>` |
| `update_*` | `change_<model>` |
| `delete_*` | `delete_<model>` |
| `actions_*` | `view_<model>` |
| `action_*` | `change_<model>` |
| `bulk_*` create | `add_<model>` |
| `bulk_*` update | `change_<model>` |
| `bulk_*` delete | `delete_<model>` |
| `related_*` | `view_<model>` |
| `history_*` | `view_<model>` |
| `autocomplete_*` | `view_<model>` |
| `find_models` | Filters results by `has_module_permission()` and `view_<model>` |

`action_<model>` with `delete_selected` additionally requires `delete_<model>`, checked before any ID lookup.

### Permission Checking Flow

```
Request with Token
       ↓
Token Validation (active, not expired)
       ↓
request.user = token's linked user
       ↓
ModelAdmin.has_module_permission() / has_<action>_permission()
       ↓
    Success → Execute Tool
       ↓
    Failure → Return Error
```

Because checks go through the `ModelAdmin` methods, custom `has_*_permission()` overrides and `get_queryset()` scoping in your admin classes apply to MCP calls exactly as they do in the Django admin.

## Permission Sources

!!! important "Authorization uses the linked user's permissions"
    Every check runs against the Django **user** the token is bound to (`token.user`). The token model also has `permissions` and `groups` fields, but they are **not currently consulted** during authorization — assign permissions to the linked user (directly or via its groups) to control what a token can do. A token bound to a superuser has full access.

### User Permissions

Grant permissions to the token's linked user:

```python
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Article

article_ct = ContentType.objects.get_for_model(Article)
token.user.user_permissions.add(
    Permission.objects.get(codename='view_article', content_type=article_ct),
    Permission.objects.get(codename='add_article', content_type=article_ct),
)
```

### Group Permissions

Or via the user's groups:

```python
token.user.groups.add(Group.objects.get(name='Editors'))
```

## Django Admin Permissions

Django automatically creates four permissions per model:

| Permission | Codename | Description |
|------------|----------|-------------|
| View | `view_<model>` | Read-only access |
| Add | `add_<model>` | Create new records |
| Change | `change_<model>` | Modify existing records |
| Delete | `delete_<model>` | Remove records |

Example for an `Article` model in the `blog` app:

- `blog.view_article`
- `blog.add_article`
- `blog.change_article`
- `blog.delete_article`

## Creating Permission Groups

Organize permissions into reusable groups:

```python
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Article, Author

# Get content types
article_ct = ContentType.objects.get_for_model(Article)
author_ct = ContentType.objects.get_for_model(Author)

# Create a read-only group
readers = Group.objects.create(name='Blog Readers')
readers.permissions.add(
    Permission.objects.get(codename='view_article', content_type=article_ct),
    Permission.objects.get(codename='view_author', content_type=author_ct),
)

# Create an editors group
editors = Group.objects.create(name='Blog Editors')
editors.permissions.add(
    *Permission.objects.filter(content_type__in=[article_ct, author_ct])
)
```

## Permission Error Responses

When a permission check fails, the tool returns an error object (delivered as JSON text inside the JSON-RPC result envelope):

```json
{
  "error": "Permission denied: cannot add article",
  "code": "permission_denied"
}
```

## Best Practices

Create a dedicated Django user per integration and bind the token to it — never bind agent tokens to a superuser.

### Read-Only Tokens

For monitoring or exploration:

```python
reader = User.objects.create_user('mcp-readonly')
reader.user_permissions.add(
    *Permission.objects.filter(codename__startswith='view_')
)
readonly_token = MCPToken.objects.create(name='Read Only', user=reader)
```

### Model-Specific Tokens

For single-purpose integrations:

```python
manager = User.objects.create_user('mcp-articles')
manager.user_permissions.add(
    *Permission.objects.filter(
        content_type=ContentType.objects.get_for_model(Article)
    )
)
article_token = MCPToken.objects.create(name='Article Manager', user=manager)
```

### Audit Permissions

Review each token's effective permissions (its linked user's) regularly:

```python
for token in MCPToken.objects.filter(is_active=True).select_related('user'):
    perms = token.user.get_all_permissions()
    print(f"{token.name} (user {token.user.username}): {len(perms)} permissions")
    for perm in sorted(perms):
        print(f"  - {perm}")
```

## Custom Permissions

You can create custom permissions for admin actions:

```python title="models.py"
class Article(models.Model):
    # ...

    class Meta:
        permissions = [
            ("publish_article", "Can publish articles"),
            ("feature_article", "Can feature articles"),
        ]
```

Then gate admin actions on them with Django's `allowed_permissions`:

```python title="admin.py"
@admin.action(description='Publish selected articles', permissions=['publish'])
def publish(modeladmin, request, queryset):
    queryset.update(published=True)

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [publish]

    def has_publish_permission(self, request):
        return request.user.has_perm('blog.publish_article')
```

Without `permissions=[...]` on the action, executing it via `action_<model>` only requires `change_<model>`.

## Next Steps

- [Client Setup](client-setup.md) — Configure MCP clients
- [Tools Reference](../tools/overview.md) — Explore tool capabilities
