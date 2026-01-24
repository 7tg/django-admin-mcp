# Token Management

Django Admin MCP uses token-based authentication for all API requests. This guide covers creating, managing, and securing tokens.

## Creating Tokens

### Via Django Admin

1. Navigate to Django admin: `http://localhost:8000/admin/`
2. Go to **Django Admin MCP > MCP Tokens**
3. Click **Add MCP Token**
4. Configure the token:

    - **Name**: Descriptive identifier (e.g., "MCP - Development")
    - **User**: Associated user for audit logging (required)
    - **Is Active**: Enable/disable the token
    - **Expires At**: Expiration date (default: 90 days from now)
    - **Groups**: Assign groups for permission inheritance
    - **Permissions**: Assign individual permissions

5. Click **Save**
6. Copy the generated token from the list view

### Via Django Shell

```python
from django_admin_mcp.models import MCPToken
from django.contrib.auth.models import User, Permission

# Create a token
user = User.objects.get(username='admin')
token = MCPToken.objects.create(
    name='API Token',
    user=user,
)

# Add permissions
view_article = Permission.objects.get(codename='view_article')
token.permissions.add(view_article)

print(f"Token: {token.token}")
```

## Token Properties

### Token String

Tokens are 64-character random strings, auto-generated on creation:

```
a1b2c3d4e5f6...  (64 characters)
```

!!! warning "Token Security"
    Tokens cannot be viewed again after creation in Django admin. Store them securely.

### Expiration

Tokens have an optional expiration date:

| Configuration | Behavior |
|---------------|----------|
| `expires_at` set | Token expires at that datetime |
| `expires_at` blank | Token never expires |
| Default | 90 days from creation |

Check token validity:

```python
token = MCPToken.objects.get(name='My Token')
if token.is_valid():
    print("Token is active and not expired")
```

### Active Status

The `is_active` field allows quick enable/disable without deletion:

```python
# Disable a token
token.is_active = False
token.save()

# Re-enable later
token.is_active = True
token.save()
```

### Usage Tracking

Each token tracks its last usage:

```python
token = MCPToken.objects.get(name='My Token')
print(f"Last used: {token.last_used_at}")
```

This is automatically updated on each authenticated request.

## Permission Assignment

### Direct Permissions

Assign permissions directly to the token:

```python
from django.contrib.auth.models import Permission

token = MCPToken.objects.get(name='My Token')

# Add view permission for Article
view_article = Permission.objects.get(
    codename='view_article',
    content_type__app_label='blog'
)
token.permissions.add(view_article)

# Add multiple permissions
add_article = Permission.objects.get(codename='add_article')
change_article = Permission.objects.get(codename='change_article')
token.permissions.add(add_article, change_article)
```

### Group Permissions

Assign groups to inherit their permissions:

```python
from django.contrib.auth.models import Group

token = MCPToken.objects.get(name='My Token')

# Create a group with permissions
editors = Group.objects.get(name='Editors')
token.groups.add(editors)
```

### Check Permissions

```python
token = MCPToken.objects.get(name='My Token')

# Check single permission
if token.has_perm('blog.view_article'):
    print("Can view articles")

# Get all permissions
perms = token.get_all_permissions()
print(f"Permissions: {perms}")
```

!!! note "User Permissions Not Inherited"
    Token permissions are independent of the associated user's permissions. A superuser can have a token with limited access.

## Security Best Practices

### Principle of Least Privilege

Create tokens with only the permissions needed:

```python
# Read-only token
readonly_token = MCPToken.objects.create(name='Read Only')
readonly_token.permissions.add(
    Permission.objects.get(codename='view_article'),
    Permission.objects.get(codename='view_author'),
)

# Full access token
full_token = MCPToken.objects.create(name='Full Access')
full_token.permissions.add(
    *Permission.objects.filter(
        content_type__app_label='blog'
    )
)
```

### Use Expiration Dates

Always set expiration for production tokens:

```python
from datetime import timedelta
from django.utils import timezone

token = MCPToken.objects.create(
    name='Production Token',
    expires_at=timezone.now() + timedelta(days=30),
)
```

### Rotate Tokens Regularly

Create new tokens and deactivate old ones:

```python
# Create new token
new_token = MCPToken.objects.create(
    name='Production Token v2',
    user=old_token.user,
)
new_token.permissions.set(old_token.permissions.all())

# Deactivate old token
old_token.is_active = False
old_token.save()
```

### Audit Token Usage

Monitor token usage via `last_used_at`:

```python
from django.utils import timezone
from datetime import timedelta

# Find unused tokens
unused = MCPToken.objects.filter(
    last_used_at__lt=timezone.now() - timedelta(days=30)
)

# Consider deactivating or deleting
for token in unused:
    print(f"Unused token: {token.name}")
```

## Using Tokens

Include the token in the Authorization header:

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'
```

## Next Steps

- [Permissions](permissions.md) - Detailed permission system guide
- [Client Setup](client-setup.md) - Configure MCP clients
