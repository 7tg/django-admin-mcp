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
request.user = permission proxy answering from the token's permissions/groups
       ↓
ModelAdmin.has_module_permission() / has_<action>_permission()
       ↓
    Success → Execute Tool
       ↓
    Failure → Return Error
```

Because checks go through the `ModelAdmin` methods, custom `has_*_permission()` overrides and `get_queryset()` scoping in your admin classes apply to MCP calls exactly as they do in the Django admin — `request.user.has_perm(...)` inside them answers from the token's permissions.

## Permission Sources

!!! important "Authorization uses the token's own permissions"
    Every check runs against the token's `permissions` and `groups` fields. The linked user's Django permissions are **not** inherited — the user exists for audit logging only, and even a superuser-bound token has no access until permissions are granted on the token. Tokens start with no permissions (principle of least privilege).

### Direct Permissions

Grant permissions to the token:

```python
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Article

article_ct = ContentType.objects.get_for_model(Article)
token.permissions.add(
    Permission.objects.get(codename='view_article', content_type=article_ct),
    Permission.objects.get(codename='add_article', content_type=article_ct),
)
```

### Group Permissions

Or via groups assigned to the token:

```python
token.groups.add(Group.objects.get(name='Editors'))
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

Create one token per integration and grant it only the permissions it needs. The linked user is the audit identity — actions appear under it in the Django admin history.

### Read-Only Tokens

For monitoring or exploration:

```python
audit_user = User.objects.get(username='mcp-agent')
readonly_token = MCPToken.objects.create(name='Read Only', user=audit_user)
readonly_token.permissions.add(
    *Permission.objects.filter(codename__startswith='view_')
)
```

### Model-Specific Tokens

For single-purpose integrations:

```python
article_token = MCPToken.objects.create(name='Article Manager', user=audit_user)
article_token.permissions.add(
    *Permission.objects.filter(
        content_type=ContentType.objects.get_for_model(Article)
    )
)
```

### Audit Permissions

Review each token's effective permissions regularly:

```python
for token in MCPToken.objects.filter(is_active=True).select_related('user'):
    perms = token.get_all_permissions()
    print(f"{token.name} (logs as {token.user.username}): {len(perms)} permissions")
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

Grant `blog.publish_article` to the token (directly or via one of its groups) to allow the action — `request.user.has_perm(...)` in MCP requests answers from the token's permissions.

Without `permissions=[...]` on the action, executing it via `action_<model>` only requires `change_<model>`.

## Next Steps

- [Client Setup](client-setup.md) — Configure MCP clients
- [Tools Reference](../tools/overview.md) — Explore tool capabilities
