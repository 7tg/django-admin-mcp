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
    - **Expires At** — Expiration date (leaving it blank applies the 90-day default)
    - **User** — The Django user the token acts as: requests are authorized with this user's permissions and audit-logged under it (required)

5. Click **Save**
6. Copy the generated token — it is only displayed once after creation

An existing token's change page also offers a **Regenerate Token** button that invalidates the current secret and shows a new plaintext token once.

### Via Django Shell

```python
from django_admin_mcp.models import MCPToken
from django.contrib.auth.models import User

# Create a dedicated user carrying exactly the permissions the agent needs
user = User.objects.get(username='mcp-agent')

token = MCPToken.objects.create(
    name='API Token',
    user=user,
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
| `expires_at` passed explicitly at creation | Used as-is; an explicit `None` means the token never expires |
| `expires_at` not passed (including left blank in the admin form) | Defaults to 90 days from creation |

To create an indefinite token, pass the value explicitly in code: `MCPToken.objects.create(name='...', user=user, expires_at=None)`.

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

!!! important "Permissions come from the linked user"
    At request time, every check runs against the Django permissions of the token's linked **user**. The token's own `permissions` and `groups` fields are not currently consulted during authorization. Control a token's access by managing its user's permissions — and never bind an agent token to a superuser.

### User Permissions

```python
from django.contrib.auth.models import Permission

token = MCPToken.objects.select_related('user').get(name='My Token')

# Add view permission for Article to the linked user
view_article = Permission.objects.get(
    codename='view_article',
    content_type__app_label='blog'
)
token.user.user_permissions.add(view_article)
```

### Group Permissions

```python
from django.contrib.auth.models import Group

editors = Group.objects.get(name='Editors')
token.user.groups.add(editors)
```

### Check Permissions

```python
# Effective permissions are the linked user's
perms = token.user.get_all_permissions()
print(f"Permissions: {perms}")
```

!!! tip "Permission caching"
    Django caches a user's permissions on the user instance — re-fetch the user (or the token) after changing permissions to see the update.

## Security Best Practices

### Principle of Least Privilege

Bind each token to a dedicated user carrying only the permissions needed:

```python
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from blog.models import Article, Author

reader = User.objects.create_user('mcp-readonly')
reader.user_permissions.add(
    Permission.objects.get(
        codename='view_article',
        content_type=ContentType.objects.get_for_model(Article),
    ),
    Permission.objects.get(
        codename='view_author',
        content_type=ContentType.objects.get_for_model(Author),
    ),
)
readonly_token = MCPToken.objects.create(name='Read Only', user=reader)
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
