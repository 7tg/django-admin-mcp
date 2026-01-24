"""
Tests for HTTP interface edge cases
"""

import json
from unittest.mock import AsyncMock, patch

import django
import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

from tests.factories import MCPTokenFactory

# AsyncClient headers= parameter requires Django 4.2+
DJANGO_42_PLUS = django.VERSION >= (4, 2)
skip_if_django_lt_42 = pytest.mark.skipif(
    not DJANGO_42_PLUS, reason="AsyncClient headers= parameter requires Django 4.2+"
)


@pytest.mark.django_db(transaction=True)
class TestEmptyToolResult:
    """Test suite for empty tool result edge cases."""

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_empty_tool_result(self):
        """Test mcp_endpoint when call_tool returns empty result."""

        # Create a valid token
        token = await sync_to_async(MCPTokenFactory)()

        with patch("django_admin_mcp.views.call_tool", new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = []  # Empty result

            client = AsyncClient()
            response = await client.post(
                "/api/mcp/",
                data=json.dumps({"method": "tools/call", "name": "test_tool", "arguments": {}}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {token.token}"},
            )

            assert response.status_code == 500
            data = json.loads(response.content)
            assert "error" in data
            assert "No result" in data["error"]


@pytest.mark.django_db(transaction=True)
class TestFunctionBasedViewEdgeCases:
    """Test suite for function-based view edge cases."""

    @pytest.mark.asyncio
    async def test_mcp_endpoint_method_not_allowed(self):
        """Test mcp_endpoint rejects non-POST requests."""
        client = AsyncClient()

        # Try GET request
        response = await client.get("/api/mcp/")
        assert response.status_code == 405
        data = json.loads(response.content)
        assert "error" in data
        assert "Method not allowed" in data["error"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_mcp_endpoint_invalid_json(self):
        """Test mcp_endpoint handles invalid JSON."""
        # Create a valid token
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data="invalid json {",
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        assert "JSON" in data["error"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_mcp_endpoint_unknown_method(self):
        """Test mcp_endpoint handles unknown methods."""
        # Create a valid token
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "unknown/method"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        assert "Unknown method" in data["error"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_handle_call_tool_request_missing_tool_name(self):
        """Test handle_call_tool_request with missing tool name."""
        # Create a valid token
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/call", "arguments": {}}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        # Pydantic validation returns "Invalid request" with details
        assert "Invalid request" in data["error"]
        assert "details" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_handle_call_tool_request_success(self):
        """Test handle_call_tool_request with valid tool call."""
        # Create a valid token
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/call", "name": "find_models", "arguments": {}}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        # Should return model data
        assert "models" in data
