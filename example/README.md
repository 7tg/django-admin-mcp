# Example Django Application with django-admin-mcp

This directory contains a simple example Django application demonstrating how to use django-admin-mcp.

## Setup

1. Install dependencies:
```bash
pip install django django-admin-mcp
```

2. Set up the database:
```bash
cd example
python manage.py migrate
python manage.py createsuperuser
```

3. Create an MCP token in the admin (`/admin/django_admin_mcp/mcptoken/`), or seed one with a value you choose:
```bash
python manage.py seed_mcp_token --token mcp_mykey.mysecret
```

4. Serve it. The MCP endpoint is `http://localhost:8000/api/mcp/` (see `.mcp.json.example`):
```bash
python manage.py runserver
```

## Docker

The repository's `Dockerfile` packages this example project so the server can be
started without a host Django project, for instance by MCP registries that boot the
server to introspect its tools:

```bash
docker build -t django-admin-mcp .
docker run --rm -p 8000:8000 django-admin-mcp
```

On start the container migrates, seeds a token and sample data (`seed_mcp_token`),
and serves on port 8000. Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_ADMIN_MCP_TOKEN` | `mcp_glama-inspect.glama-inspect-secret` | Token value seeded at start (`mcp_<key>.<secret>`, key up to 16 characters) |
| `MCP_ALLOW_URL_TOKEN` | `1` | Also accept the token in the path: `POST /api/mcp/<token>/` |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated `ALLOWED_HOSTS` |
| `DJANGO_DEBUG` | `0` | Set to `1` for Django debug mode |
| `DJANGO_DB_PATH` | `/data/db.sqlite3` | SQLite database location |
| `PORT` | `8000` | Port the server listens on |

```bash
curl http://localhost:8000/api/mcp/health/
curl -X POST http://localhost:8000/api/mcp/ \
  -H "Authorization: Bearer mcp_glama-inspect.glama-inspect-secret" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The seeded token is public by design: use the image for demos and introspection only.

## Project Structure

- `blog/` - A simple blog app with Article and Author models
- `manage.py` - Django management script
- `example_project/` - Django project settings

## Models

### Author
- name (CharField)
- email (EmailField)
- bio (TextField)

### Article
- title (CharField)
- content (TextField)
- author (ForeignKey to Author)
- published_date (DateTimeField)
- is_published (BooleanField)

## MCP Tools Available

Once the server is running, you'll have access to:

- `list_article`, `get_article`, `create_article`, `update_article`, `delete_article`
- `list_author`, `get_author`, `create_author`, `update_author`, `delete_author`
