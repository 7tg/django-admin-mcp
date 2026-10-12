# django-admin-mcp is a Django app, not a standalone server, so this image
# runs the bundled example project (example/) with the app mounted at
# /api/mcp/ and a token seeded at start. It exists so registries such as
# Glama can boot the server and introspect its tools; it is not a
# production deployment.
#
#   docker build -t django-admin-mcp .
#   docker run --rm -p 8000:8000 django-admin-mcp
#
#   curl http://localhost:8000/api/mcp/health/
#   curl -X POST http://localhost:8000/api/mcp/ \
#     -H "Authorization: Bearer mcp_glama-inspect.glama-inspect-secret" \
#     -H "Content-Type: application/json" \
#     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
#
# Override DJANGO_ADMIN_MCP_TOKEN (mcp_<key>.<secret>, key up to 16 chars)
# to use your own token value.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package from this checkout (runtime deps only: Django, Pydantic).
COPY pyproject.toml setup.py MANIFEST.in README.md LICENSE ./
COPY django_admin_mcp ./django_admin_mcp
RUN pip install .

# The example project that hosts the app.
COPY example ./example
WORKDIR /app/example

ENV DJANGO_SETTINGS_MODULE=example_project.settings \
    DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=* \
    DJANGO_DB_PATH=/data/db.sqlite3 \
    MCP_ALLOW_URL_TOKEN=1 \
    DJANGO_ADMIN_MCP_TOKEN=mcp_glama-inspect.glama-inspect-secret \
    PORT=8000

# Example-app migrations are not committed; generate them at build time.
RUN python manage.py makemigrations blog --noinput \
    && useradd --system --no-create-home app \
    && mkdir -p /data \
    && chown app /data

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/mcp/health/')"

ENTRYPOINT ["./docker-entrypoint.sh"]
