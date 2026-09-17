"""
Tests for the opt-in URL-path token endpoint.

Web MCP clients (claude.ai, ChatGPT) can only register a plain URL for a
custom connector: their dialogs offer OAuth but no field for a static
``Authorization`` header. ``MCP_ALLOW_URL_TOKEN`` opens a route that carries
the bearer token as a path segment instead.
"""

import json

import django
import pytest
from asgiref.sync import sync_to_async
from django.core.handlers.base import BaseHandler
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import AsyncClient, override_settings

from django_admin_mcp import views
from tests.factories import MCPTokenFactory

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
}


@sync_to_async
def make_token():
    return MCPTokenFactory()


def touch_headers_middleware(get_response):
    """Middleware that reads ``request.headers``, as CORS and Common do."""

    async def middleware(request):
        _ = request.headers  # populates the cached_property before the view runs
        return await get_response(request)

    return middleware


touch_headers_middleware.async_capable = True
touch_headers_middleware.sync_capable = False


async def post_initialize(path):
    return await AsyncClient().post(path, data=json.dumps(INITIALIZE), content_type="application/json")


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestURLTokenEndpoint:
    """The path token stands in for the Authorization header."""

    async def test_valid_url_token_initializes(self):
        """A token in the path authenticates exactly as a bearer header would."""
        token = await make_token()

        with override_settings(MCP_ALLOW_URL_TOKEN=True):
            response = await post_initialize(f"/api/{token.plaintext_token}/")

        assert response.status_code == 200
        body = json.loads(response.content)
        assert body["result"]["serverInfo"]["name"] == "django-admin-mcp"

    async def test_invalid_url_token_is_unauthorized(self):
        """An unknown token is rejected the same way a bad header is."""
        with override_settings(MCP_ALLOW_URL_TOKEN=True):
            response = await post_initialize("/api/mcp_notakey.notasecret/")

        assert response.status_code == 401

    async def test_inactive_url_token_is_unauthorized(self):
        """Deactivating a token closes the URL route with it."""
        token = await make_token()
        token.is_active = False
        await sync_to_async(token.save)()

        with override_settings(MCP_ALLOW_URL_TOKEN=True):
            response = await post_initialize(f"/api/{token.plaintext_token}/")

        assert response.status_code == 401

    async def test_route_is_absent_when_setting_is_off(self):
        """The route 404s unless explicitly enabled — off is the default."""
        token = await make_token()

        response = await post_initialize(f"/api/{token.plaintext_token}/")

        assert response.status_code == 404

    async def test_path_token_overrides_authorization_header(self):
        """The path token is authoritative on this route, header or not."""
        token = await make_token()

        with override_settings(MCP_ALLOW_URL_TOKEN=True):
            response = await AsyncClient().post(
                f"/api/{token.plaintext_token}/",
                data=json.dumps(INITIALIZE),
                content_type="application/json",
                headers={"Authorization": "Bearer mcp_garbage.garbage"},
            )

        assert response.status_code == 200

    async def test_path_token_is_seen_after_middleware_reads_headers(self):
        """
        ``request.headers`` is a cached_property, and middleware routinely
        materializes it before the view runs. The promoted token has to
        invalidate that cache or it would never reach authentication.
        """
        token = await make_token()

        with override_settings(
            MCP_ALLOW_URL_TOKEN=True,
            MIDDLEWARE=["tests.http.test_url_token.touch_headers_middleware"],
        ):
            response = await post_initialize(f"/api/{token.plaintext_token}/")

        assert response.status_code == 200

    async def test_route_is_csrf_exempt(self):
        """
        A POST without a CSRF token must not be rejected.

        ``tests/settings.py`` declares no MIDDLEWARE, so CsrfViewMiddleware is
        added here — otherwise nothing would exercise the exemption. The client
        is built inside the override so its handler loads that middleware.
        """
        token = await make_token()

        with override_settings(
            MCP_ALLOW_URL_TOKEN=True,
            MIDDLEWARE=["django.middleware.csrf.CsrfViewMiddleware"],
        ):
            response = await AsyncClient(enforce_csrf_checks=True).post(
                f"/api/{token.plaintext_token}/",
                data=json.dumps(INITIALIZE),
                content_type="application/json",
            )

        assert response.status_code == 200


def test_route_is_usable_under_atomic_requests():
    """
    The view must carry its own ``_non_atomic_requests`` marker.

    Django's handler reads that marker off the *resolved* view, so the one on
    ``mcp_endpoint`` — which this route delegates to — is never consulted. A
    project with ``ATOMIC_REQUESTS = True`` would otherwise get
    ``RuntimeError: You cannot use ATOMIC_REQUESTS with async views`` on every
    request. ``tests/settings.py`` leaves ATOMIC_REQUESTS off, so enable it
    here for the duration of the check.
    """
    settings_dict = connections.settings[DEFAULT_DB_ALIAS]
    original = settings_dict["ATOMIC_REQUESTS"]
    settings_dict["ATOMIC_REQUESTS"] = True
    try:
        BaseHandler().make_view_atomic(views.mcp_endpoint_url_token)
    finally:
        settings_dict["ATOMIC_REQUESTS"] = original
