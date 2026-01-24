# Installation

This guide covers installing Django Admin MCP and configuring it in your Django project.

## Requirements

Before installing, ensure you have:

- Python >= 3.10
- Django >= 3.2
- Pydantic >= 2.0

## Install the Package

Install using pip:

```bash
pip install django-admin-mcp
```

Or with your preferred package manager:

=== "pip"

    ```bash
    pip install django-admin-mcp
    ```

=== "uv"

    ```bash
    uv add django-admin-mcp
    ```

=== "poetry"

    ```bash
    poetry add django-admin-mcp
    ```

=== "pipenv"

    ```bash
    pipenv install django-admin-mcp
    ```

## Configure Django Settings

Add `django_admin_mcp` to your `INSTALLED_APPS`:

```python title="settings.py"
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Add django_admin_mcp
    'django_admin_mcp',

    # Your apps...
]
```

## Add URL Routes

Include the MCP URLs in your project's URL configuration:

```python title="urls.py"
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('mcp/', include('django_admin_mcp.urls')),
]
```

This exposes two endpoints:

- `POST /mcp/` - Main MCP protocol endpoint
- `GET /mcp/health/` - Health check endpoint

## Run Migrations

Create the database tables for token management:

```bash
python manage.py migrate django_admin_mcp
```

This creates the `MCPToken` model table for API authentication.

## Verify Installation

Start your Django development server:

```bash
python manage.py runserver
```

Test the health endpoint:

```bash
curl http://localhost:8000/mcp/health/
```

Expected response:

```json
{"status": "ok", "service": "django-admin-mcp"}
```

## Next Steps

Now that Django Admin MCP is installed, proceed to:

1. [Quick Start](quick-start.md) - Set up your first exposed model
2. [Configuration](configuration.md) - Learn about configuration options
