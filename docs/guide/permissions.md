# 🔒 Permissions

Django Admin MCP integrates with Django's permission system. Every operation checks permissions before execution.

## 🔍 How Permissions Work

### 📋 Permission Requirements by Operation

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
| `find_models` | Filters results by `view_<model>` |

### 🔄 Permission Checking Flow

```
Request with Token
       ↓
Token Validation (active, not expired)
       ↓
Tool Permission Check
       ↓
    Success → Execute Tool
       ↓
    Failure → Return Error
```

## 📦 Permission Sources

Tokens derive permissions from two sources:

### 1️⃣ Direct Permissions

Permissions assigned directly to the token:

```python
token = MCPToken.objects.get(name='My Token')
token.permissions.add(
    Permission.objects.get(codename='view_article'),
    Permission.objects.get(codename='add_article'),
)
```

### 2️⃣ Group Permissions

Permissions inherited from assigned groups:

```python
token = MCPToken.objects.get(name='My Token')
token.groups.add(Group.objects.get(name='Editors'))
```

!!! important "User Permissions Not Inherited"
    The associated user's permissions are NOT inherited by the token. This is by design, allowing limited-access tokens for any user, including superusers.

## 🏗️ Django Admin Permissions

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

## 👥 Creating Permission Groups

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

## ❌ Permission Error Responses

When a permission check fails, the tool returns an error:

```json
{
  "content": [
    {
      "type": "text",
      "text": "Permission denied: blog.add_article"
    }
  ],
  "isError": true
}
```

## 💡 Best Practices

### 👁️ Read-Only Tokens

For monitoring or exploration:

```python
readonly_token = MCPToken.objects.create(name='Read Only')
readonly_token.permissions.add(
    *Permission.objects.filter(codename__startswith='view_')
)
```

### 🎯 Model-Specific Tokens

For single-purpose integrations:

```python
article_token = MCPToken.objects.create(name='Article Manager')
article_token.permissions.add(
    *Permission.objects.filter(
        content_type=ContentType.objects.get_for_model(Article)
    )
)
```

### 🔑 Admin-Level Tokens

For full administrative access:

```python
admin_token = MCPToken.objects.create(name='Admin Token')
admin_token.permissions.add(
    *Permission.objects.filter(
        content_type__app_label__in=['blog', 'auth']
    )
)
```

### 📊 Audit Permissions

Review token permissions regularly:

```python
for token in MCPToken.objects.filter(is_active=True):
    perms = token.get_all_permissions()
    print(f"{token.name}: {len(perms)} permissions")
    for perm in sorted(perms):
        print(f"  - {perm}")
```

## 🔧 Custom Permissions

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

Then use in admin actions:

```python title="admin.py"
@admin.action(description='Publish selected articles')
def publish(modeladmin, request, queryset):
    # This action requires 'publish_article' permission
    queryset.update(published=True)

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [publish]
```

## 🔗 Next Steps

- [Client Setup](client-setup.md) — Configure MCP clients
- [Tools Reference](../tools/overview.md) — Explore tool capabilities
