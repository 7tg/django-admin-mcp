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
request.user = permission proxy answering from the token's effective permissions
               (token permissions/groups ∩ linked user's permissions)
       ↓
ModelAdmin.has_module_permission() / has_<action>_permission()
       ↓
    Success → Execute Tool
       ↓
    Failure → Return Error
```

Because checks go through the `ModelAdmin` methods, custom `has_*_permission()` overrides and `get_queryset()` scoping in your admin classes apply to MCP calls exactly as they do in the Django admin — `request.user.has_perm(...)` inside them answers from the token's permissions.

## Permission Sources

!!! important "Effective permissions = token grants ∩ user permissions"
    Every check runs against the token's `permissions` and `groups` fields, **capped by the linked user's Django permissions** — a token can narrow its user's access but never exceed it. The user's permissions are not inherited (a permission must be granted on the token to be usable), tokens start with no permissions (principle of least privilege), and a token granted something its user lacks is still denied. Binding to a superuser means the token's grants apply as-is; deactivating the linked user disables all its tokens' access.

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

Create one token per integration and grant it only the permissions it needs. The linked user must hold at least those permissions (it caps the token) and is the audit identity — actions appear under it in the Django admin history.

### Read-Only Tokens

For monitoring or exploration:

```python
# The linked user caps the token, so it must hold the permissions too
agent_user = User.objects.get(username='mcp-agent')
view_perms = Permission.objects.filter(codename__startswith='view_')
agent_user.user_permissions.add(*view_perms)

readonly_token = MCPToken.objects.create(name='Read Only', user=agent_user)
readonly_token.permissions.add(*view_perms)
```

### Model-Specific Tokens

For single-purpose integrations:

```python
article_perms = Permission.objects.filter(
    content_type=ContentType.objects.get_for_model(Article)
)
agent_user.user_permissions.add(*article_perms)

article_token = MCPToken.objects.create(name='Article Manager', user=agent_user)
article_token.permissions.add(*article_perms)
```

### Audit Permissions

Review each token's effective permissions regularly:

```python
for token in MCPToken.objects.filter(is_active=True).select_related('user'):
    perms = token.get_effective_permissions()  # grants ∩ user permissions
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

Grant `blog.publish_article` to the token (directly or via one of its groups) — and make sure its linked user holds it too — to allow the action. `request.user.has_perm(...)` in MCP requests answers from the token's effective permissions.

Without `permissions=[...]` on the action, executing it via `action_<model>` only requires `change_<model>`.

## Next Steps

- [Client Setup](client-setup.md) — Configure MCP clients
- [Tools Reference](../tools/overview.md) — Explore tool capabilities
