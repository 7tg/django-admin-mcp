#!/bin/sh
# Boot the example project for a container: migrate, seed a known MCP token
# and sample data, then serve HTTP. Configuration comes from the environment
# (see the Dockerfile for the variables and their defaults).
set -eu

cd "$(dirname "$0")"

python manage.py migrate --noinput
python manage.py seed_mcp_token --token "$DJANGO_ADMIN_MCP_TOKEN"

echo "MCP endpoint:    http://0.0.0.0:${PORT}/api/mcp/  (Authorization: Bearer ${DJANGO_ADMIN_MCP_TOKEN})"
if [ "${MCP_ALLOW_URL_TOKEN:-0}" = "1" ]; then
  echo "URL-token route: http://0.0.0.0:${PORT}/api/mcp/${DJANGO_ADMIN_MCP_TOKEN}/"
fi
echo "Health:          http://0.0.0.0:${PORT}/api/mcp/health/"

exec python manage.py runserver "0.0.0.0:${PORT}" --noreload
