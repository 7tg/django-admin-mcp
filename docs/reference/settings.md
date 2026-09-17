# Settings Reference

Django Admin MCP configuration options and Django settings.

## Django Settings

### Required Settings

Add `django_admin_mcp` to installed apps:

```python title="settings.py"
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'django_admin_mcp',  # Add this

    # Your apps
]
```

### URL Configuration

Include the MCP URLs:

```python title="urls.py"
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('mcp/', include('django_admin_mcp.urls')),  # Add this
]
```

You can customize the URL path:

```python
# Alternative paths
path('api/mcp/', include('django_admin_mcp.urls')),
path('admin-api/', include('django_admin_mcp.urls')),
```

### Optional Settings

Four optional Django settings:

```python title="settings.py"
# Maximum page size for list_*, related_*, history_*, and autocomplete_*
# tools. Requested limits above this value are silently capped. Default: 1000
MCP_MAX_LIST_LIMIT = 1000

# Maximum size of file downloads returned by admin actions
# (HttpResponse/StreamingHttpResponse bodies). Larger responses are
# rejected with an error. Default: 5 MiB
MCP_ACTION_MAX_FILE_BYTES = 5 * 1024 * 1024

# Write resolution for MCPToken.last_used_at, in seconds. Within this
# window of the recorded timestamp, further uses are not written to the
# database. Set to 0 to record every use. Default: 60
MCP_LAST_USED_RESOLUTION = 60

# Accept the bearer token as a URL path segment, for clients that cannot
# send an Authorization header. Default: False
MCP_ALLOW_URL_TOKEN = False
```

### MCP_ALLOW_URL_TOKEN

Opens a second route at `<mount_point>/<token>/` that reads the bearer token from the URL instead of the `Authorization` header:

```
POST https://example.com/mcp/mcp_yourkey.yoursecret/
```

It exists for web MCP clients — claude.ai and ChatGPT custom connectors register a plain URL and offer OAuth, with no field for a static header. Everything downstream is unchanged: the same token, the same permission checks, the same responses.

When the setting is false (the default) the route returns `404`. The header route at `<mount_point>/` always works and is unaffected either way.

!!! warning "A token in a URL is a weaker secret"
    URLs are recorded where headers are not: proxy and web-server access logs, `django.request` log lines on errors, and browser history. Treat the URL itself as the credential.

    - Mint a **dedicated** token for the URL route so it can be revoked on its own
    - Give it the narrowest permissions and an `expires_at`
    - Prefer the header route for any client that supports it

!!! note "Token expiry is not a Django setting"
    The 90-day default for programmatic creation is fixed in the `MCPToken` model. Set `expires_at` per token to override it; in the admin form, a blank **Expires At** means the token never expires.

---

## ModelAdmin Options

Configure each ModelAdmin with these options:

### mcp_expose

Enable full tool exposure:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True  # Expose all 12 tools
```

| Value | Effect |
|-------|--------|
| `True` | Expose CRUD tools, actions, relationships |
| `False` | Only discoverable via `find_models` |

Default: `False`

!!! note "`mcp_expose` controls both advertisement and reachability"
    Non-exposed models are hidden from `tools/list`, and a direct `tools/call` for them is rejected with the same "Model not found" error as for unregistered models.

### mcp_fields

Allowlist of fields to include in serialized responses. Takes precedence over the admin's `fields`:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    mcp_fields = ['title', 'author', 'published']
```

Default: `None` (all editable fields)

### mcp_exclude_fields

Denylist of fields to strip from serialized responses. Takes precedence over the admin's `exclude` and is applied after `mcp_fields`:

```python
class UserAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    mcp_exclude_fields = ['password', 'security_token']
```

Default: `None`

### mcp_use_admin_queryset

When `True` (the default), every tool that looks up rows (`list_*`, `get_*`, `update_*`, `delete_*`, `bulk_*`, actions, `related_*`, `history_*`, `autocomplete_*`) starts from `ModelAdmin.get_queryset(request)`, so proxy filters, soft-delete, and multi-tenant scoping match the admin changelist. Set to `False` to use `model.objects.all()` instead:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    mcp_use_admin_queryset = False
```

Default: `True`

### Standard Django Options

These Django admin options affect MCP behavior:

#### list_display

Reported by `describe_*` as admin metadata. It does **not** control which fields appear in `list_*` responses — use `mcp_fields`/`mcp_exclude_fields` for that:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ['title', 'author', 'published', 'created_at']
```

#### search_fields

Controls which fields `autocomplete_*` searches. Without it, all `CharField`/`TextField` fields are searched:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['title', 'content']
```

#### ordering

Default ordering for list results:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    ordering = ['-created_at']  # Newest first
```

#### readonly_fields

Attempts to update these fields return an error:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    readonly_fields = ['created_at', 'updated_at', 'view_count']
```

#### list_filter

Available filter options (informational in `describe_*`):

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_filter = ['published', 'author', 'created_at']
```

#### actions

Admin actions exposed via `actions_*` and `action_*`:

```python
@admin.action(description='Mark as published')
def publish(modeladmin, request, queryset):
    queryset.update(published=True)

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [publish]
```

#### inlines

Inline models included in `get_*` responses (when `include_inlines: true`):

```python
class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    inlines = [CommentInline]
```

---

## Token Settings

Token behavior is configured per-token in Django admin:

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | CharField | Required | Descriptive identifier |
| `token_key` | CharField | Auto-generated | Public key for O(1) lookup |
| `token_hash` | CharField | Auto-generated | SHA-256 hash of the secret |
| `salt` | CharField | Auto-generated | Per-token salt for hashing |
| `user` | ForeignKey | Required | Caps the token's permissions and is the audit identity |
| `is_active` | Boolean | `True` | Enable/disable token |
| `expires_at` | DateTime | See below | Expiration date |
| `groups` | M2M | Empty | Groups granting permissions to the token |
| `permissions` | M2M | Empty | Direct permissions granted to the token |
| `created_at` | DateTime | Auto | Creation timestamp |
| `last_used_at` | DateTime | Auto | Updated on every authenticated request |

Token format: `mcp_<key>.<secret>` — the key is stored in plaintext for lookup, the secret is hashed with a per-token salt.

### Token Expiration

- **Admin form** — leaving **Expires At** blank creates a token that never expires
- **Programmatic creation** — omitting the `expires_at` kwarg defaults to 90 days; an explicit `MCPToken(expires_at=None, ...)` never expires
- **Set date** — the token expires at the specified datetime

### Permission Sources

!!! important "Effective permissions = token grants ∩ user permissions"
    At request time, permission checks run through `ModelAdmin.has_*_permission()`, answered from the token's `permissions` and `groups` fields capped by the linked user's Django permissions. A token can narrow its user's access but never exceed it. The user's permissions are not inherited (grants must be on the token), even a superuser-bound token has no access until granted, and deactivating the linked user disables the token's access entirely.

---

## Environment Configuration

### Development

```python title="settings.py"
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
```

### Production

```python title="settings.py"
DEBUG = False
ALLOWED_HOSTS = ['api.example.com']
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

---

## Database Configuration

Django Admin MCP uses Django's database configuration:

```python title="settings.py"
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'myapp',
        'USER': 'myuser',
        'PASSWORD': 'mypassword',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

The `MCPToken` model is created via migrations:

```bash
python manage.py migrate django_admin_mcp
```

---

## Logging Configuration

Enable logging for debugging:

```python title="settings.py"
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django_admin_mcp': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

---

## Security Settings

### CSRF

The MCP endpoint is CSRF-exempt (it uses Bearer token auth instead); the view is marked exempt automatically — no configuration needed.

### CORS

For browser access, configure CORS:

```python title="settings.py"
INSTALLED_APPS = [
    'corsheaders',
    # ...
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # ...
]

CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
]

# Or allow all (not recommended for production)
CORS_ALLOW_ALL_ORIGINS = True
```

### HTTPS

Always use HTTPS in production:

```python title="settings.py"
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
```

---

## Middleware Order

Ensure proper middleware ordering:

```python title="settings.py"
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',       # First (if using CORS)
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]
```
