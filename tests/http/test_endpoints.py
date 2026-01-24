"""
Tests for HTTP interface endpoints
"""

import json

import django
import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient, Client

from tests.factories import MCPTokenFactory

# AsyncClient headers= parameter requires Django 4.2+
DJANGO_42_PLUS = django.VERSION >= (4, 2)
skip_if_django_lt_42 = pytest.mark.skipif(
    not DJANGO_42_PLUS, reason="AsyncClient headers= parameter requires Django 4.2+"
)


@pytest.mark.django_db(transaction=True)
class TestHTTPInterface:
    """Test suite for HTTP interface."""

    def test_health_endpoint(self):
        """Test health check endpoint."""
        client = Client()
        response = client.get("/api/health/")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "ok"
        assert data["service"] == "django-admin-mcp"

    @pytest.mark.asyncio
    async def test_mcp_endpoint_without_token(self):
        """Test MCP endpoint rejects requests without token."""
        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_mcp_endpoint_with_invalid_token(self):
        """Test MCP endpoint rejects requests with invalid token."""
        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_mcp_endpoint_with_valid_token_list_tools(self):
        """Test MCP endpoint with valid token lists tools."""
        # Create a token
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "result" in data
        assert "tools" in data["result"]

        # Check that tools are exposed
        tool_names = [tool["name"] for tool in data["result"]["tools"]]
        # Should always have find_models tool
        assert "find_models" in tool_names
        # Should have model-specific tools since mcp_expose=True
        assert "list_author" in tool_names
        assert "list_article" in tool_names

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_mcp_endpoint_with_inactive_token(self):
        """Test MCP endpoint rejects inactive tokens."""
        # Create an inactive token
        token = await sync_to_async(MCPTokenFactory)(is_active=False)

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_token_last_used_updated(self):
        """Test that token last_used_at is updated on use."""
        # Create a token
        token = await sync_to_async(MCPTokenFactory)()
        assert token.last_used_at is None

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200

        # Reload token and check last_used_at is set
        await sync_to_async(token.refresh_from_db)()
        assert token.last_used_at is not None
