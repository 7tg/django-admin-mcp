# Token Management

Django Admin MCP uses token-based authentication for all API requests. This guide covers creating, managing, and securing tokens.

## Creating Tokens

### Via Django Admin

1. Navigate to Django admin: `http://localhost:8000/admin/`
2. Go to **Django Admin MCP > MCP Tokens**
3. Click **Add MCP Token**
4. Configure the token:

    - **Name** — Descriptive identifier (e.g., "MCP - Development")
    - **Is Active** — Enable/disable the token
    - **Expires At** — Expiration date (leave blank for a token that never expires)
    - **User** — The Django user actions are audit-logged under (required; the user's own permissions are **not** used for authorization)
    - **Groups** / **Permissions** — What the token is allowed to do: these token-level assignments are the sole source of authorization

5. Click **Save**
6. Copy the generated token — it is only displayed once after creation

An existing token's change page also offers a **Regenerate Token** button that invalidates the current secret and shows a new plaintext token once.

### Via Django Shell

```python
from django_admin_mcp.models import MCPToken
from django.contrib.auth.models import Permission, User

# The user is for audit logging; it does not grant any access
user = User.objects.get(username='mcp-agent')

token = MCPToken.objects.create(
    name='API Token',
    user=user,
)

# Grant the token exactly the permissions the agent needs
token.permissions.add(
    Permission.objects.get(codename='view_article', content_type__app_label='blog'),
)

# Get the plaintext token (only available immediately after creation)
print(f"Token: {token.get_plaintext_token()}")
```

## Token Properties

### Token Format

Tokens use a structured `mcp_<key>.<secret>` format:

- The **key** (`token_key`, ~16 characters) is stored in plaintext for O(1) lookup
- The **secret** (~43 characters) is hashed with a per-token salt (`token_hash` + `salt`) using SHA-256
- Constant-time comparison prevents timing attacks

```
mcp_h3jN9x2kQpLmVzRw.4tYuIoPaSdFgHjKlZxCvBnM1234567890abcdefg
```

!!! warning "Token Security"
    The full token is only displayed once after creation. The secret portion is hashed and cannot be recovered. Store tokens securely.

### Expiration

Tokens have an optional expiration date:

| Configuration | Behavior |
|---------------|----------|
| Left blank in the admin form | The token never expires |
| `expires_at` passed explicitly in code | Used as-is; an explicit `None` means the token never expires |
| `expires_at` not passed at all in code | Defaults to 90 days from creation |

To create an indefinite token in code, pass the value explicitly: `MCPToken.objects.create(name='...', user=user, expires_at=None)`.

Check token validity:

```python
token = MCPToken.objects.get(name='My Token')
if token.is_valid():
    print("Token is active and not expired")
```

### Active Status

The `is_active` field allows quick enable/disable without deletion. Deactivation takes effect immediately — inactive tokens are filtered out at the lookup query, before any validity check:

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

!!! important "Permissions live on the token"
    At request time, every check runs against the token's own `permissions` and `groups`. The linked user's Django permissions are **not** inherited — even a token bound to a superuser has no access until permissions are granted on the token. Tokens start with no permissions (principle of least privilege).

### Direct Permissions

```python
from django.contrib.auth.models import Permission

token = MCPToken.objects.get(name='My Token')

# Grant view permission for Article to the token
view_article = Permission.objects.get(
    codename='view_article',
    content_type__app_label='blog'
)
token.permissions.add(view_article)
```

### Group Permissions

```python
from django.contrib.auth.models import Group

editors = Group.objects.get(name='Editors')
token.groups.add(editors)
```

### Check Permissions

```python
# Effective permissions: direct + group permissions on the token
perms = token.get_all_permissions()
print(f"Permissions: {perms}")

# Single checks
token.has_perm('blog.view_article')
token.has_module_perms('blog')
```

## Security Best Practices

### Principle of Least Privilege

Grant each token only the permissions it needs:

```python
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Article, Author

audit_user = User.objects.get(username='mcp-agent')  # audit trail only
readonly_token = MCPToken.objects.create(name='Read Only', user=audit_user)
readonly_token.permissions.add(
    Permission.objects.get(
        codename='view_article',
        content_type=ContentType.objects.get_for_model(Article),
    ),
    Permission.objects.get(
        codename='view_author',
        content_type=ContentType.objects.get_for_model(Author),
    ),
)
```

### Use Expiration Dates

Always set expiration for production tokens:

```python
from datetime import timedelta
from django.utils import timezone

token = MCPToken.objects.create(
    name='Production Token',
    user=user,
    expires_at=timezone.now() + timedelta(days=30),
)
```

### Rotate Tokens Regularly

Regenerate a token in place (also available via the **Regenerate Token** button in admin):

```python
new_plaintext = token.regenerate_token()  # invalidates the old secret immediately
```

Or create a new token and deactivate the old one:

```python
new_token = MCPToken.objects.create(
    name='Production Token v2',
    user=old_token.user,
)
# Carry over the old token's access
new_token.permissions.set(old_token.permissions.all())
new_token.groups.set(old_token.groups.all())

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
  -H "Authorization: Bearer mcp_yourkey.yoursecret" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

## Next Steps

- [Permissions](permissions.md) — Detailed permission system guide
- [Client Setup](client-setup.md) — Configure MCP clients
