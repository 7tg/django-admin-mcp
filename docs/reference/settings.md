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

### Standard Django Options

These Django admin options affect MCP behavior:

#### list_display

Fields included in list responses:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ['title', 'author', 'published', 'created_at']
```

#### search_fields

Enables search in `list_*` and powers `autocomplete_*`:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['title', 'content', 'author__name']
```

#### ordering

Default ordering for list results:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    ordering = ['-created_at']  # Newest first
```

#### readonly_fields

Fields excluded from create/update:

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

Inline models included in `get_*` responses:

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
| `token` | CharField | Auto-generated | 64-character token string |
| `user` | ForeignKey | Optional | Associated user for audit |
| `is_active` | Boolean | `True` | Enable/disable token |
| `expires_at` | DateTime | 90 days | Expiration date |
| `groups` | M2M | Empty | Groups for permissions |
| `permissions` | M2M | Empty | Direct permissions |

### Token Expiration

Default expiration is 90 days from creation. Options:

- **Set date**: Token expires at specified datetime
- **Leave blank**: Token never expires

### Permission Sources

Tokens derive permissions from:

1. Direct `permissions` M2M field
2. Permissions from assigned `groups`

!!! note
    User permissions are NOT inherited by tokens.

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

The MCP endpoint is CSRF-exempt (uses token auth instead):

```python
# Automatically applied in views.py
@csrf_exempt
class MCPHTTPView(View):
    ...
```

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
