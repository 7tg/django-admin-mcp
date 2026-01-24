"""
Tests for HTTP interface and token authentication
"""

import json
from datetime import timedelta

import django
import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient, Client
from django.utils import timezone

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
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "tools" in data

        # Check that tools are exposed
        tool_names = [tool["name"] for tool in data["tools"]]
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
            headers={"Authorization": f"Bearer {token.token}"},
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
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200

        # Reload token and check last_used_at is set
        await sync_to_async(token.refresh_from_db)()
        assert token.last_used_at is not None


@pytest.mark.django_db(transaction=True)
class TestMCPToken:
    """Test suite for MCPToken model."""

    def test_token_auto_generated(self):
        """Test that token is auto-generated on save."""
        token = MCPTokenFactory()
        assert token.token is not None
        assert len(token.token) > 0

    def test_token_unique(self):
        """Test that tokens are unique."""
        token1 = MCPTokenFactory()
        token2 = MCPTokenFactory()
        assert token1.token != token2.token

    def test_token_string_representation(self):
        """Test string representation of token."""
        token = MCPTokenFactory(name="My Token")
        str_repr = str(token)
        assert "My Token" in str_repr
        assert token.token[:8] in str_repr

    def test_token_default_expiry(self):
        """Test that tokens have default 90-day expiry."""
        token = MCPTokenFactory()
        assert token.expires_at is not None

        # Check that expiry is approximately 90 days from now
        expected_expiry = timezone.now() + timedelta(days=90)
        time_diff = abs((token.expires_at - expected_expiry).total_seconds())
        assert time_diff < 60  # Allow 1 minute tolerance

    def test_token_indefinite_expiry(self):
        """Test creating token with no expiry."""
        token = MCPTokenFactory(expires_at=None)
        assert token.expires_at is None
        assert not token.is_expired()
        assert token.is_valid()

    def test_token_custom_expiry(self):
        """Test creating token with custom expiry."""
        custom_expiry = timezone.now() + timedelta(days=30)
        token = MCPTokenFactory(expires_at=custom_expiry)
        assert token.expires_at == custom_expiry
        assert not token.is_expired()

    def test_token_expired(self):
        """Test that expired tokens are detected."""
        past_date = timezone.now() - timedelta(days=1)
        token = MCPTokenFactory(expires_at=past_date)
        assert token.is_expired()
        assert not token.is_valid()

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_expired_token_rejected(self):
        """Test that expired tokens are rejected in authentication."""
        past_date = timezone.now() - timedelta(days=1)
        token = await sync_to_async(MCPTokenFactory)(expires_at=past_date)

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data


@pytest.mark.django_db(transaction=True)
class TestMCPExpose:
    """Test suite for mcp_expose opt-in behavior."""

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_not_exposed_without_mcp_expose(self):
        """Test that tools are not exposed when mcp_expose is False."""
        from django.contrib import admin

        from tests.models import Author

        # Get the registered admin
        admin_class = admin.site._registry.get(Author).__class__

        # Temporarily set mcp_expose to False
        original_mcp_expose = getattr(admin_class, "mcp_expose", None)

        # Get the actual admin instance from registry
        admin_instance = admin.site._registry[Author]
        admin_instance.mcp_expose = False

        try:
            # Create a token
            token = await sync_to_async(MCPTokenFactory)()

            client = AsyncClient()
            response = await client.post(
                "/api/mcp/",
                data=json.dumps({"method": "tools/list"}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {token.token}"},
            )

            assert response.status_code == 200
            data = json.loads(response.content)

            # Tools for Author should NOT be in the list (but find_models should be)
            tool_names = [tool["name"] for tool in data["tools"]]
            assert "find_models" in tool_names  # This tool is always available
            assert "list_author" not in tool_names
        finally:
            # Restore original value
            if original_mcp_expose is not None:
                admin_instance.mcp_expose = original_mcp_expose
            elif hasattr(admin_instance, "mcp_expose"):
                delattr(admin_instance, "mcp_expose")


@pytest.mark.django_db(transaction=True)
class TestEmptyToolResult:
    """Test suite for empty tool result edge cases."""

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_empty_tool_result(self):
        """Test mcp_endpoint when call_tool returns empty result."""
        from unittest.mock import AsyncMock, patch

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


@pytest.mark.django_db(transaction=True)
class TestPydanticValidation:
    """Test suite for Pydantic input validation."""

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_list_invalid_method(self):
        """Test that invalid method in tools/list request is rejected."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "invalid/method"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        assert "Unknown method" in data["error"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_missing_name_field(self):
        """Test that tools/call request without name field is rejected with validation error."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/call"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data
        assert "Invalid request" in data["error"]
        assert "details" in data
        # Check that Pydantic validation error details are present
        assert isinstance(data["details"], list)
        assert len(data["details"]) > 0

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_with_valid_arguments(self):
        """Test that tools/call with valid arguments works correctly."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/call", "name": "find_models", "arguments": {"query": "article"}}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "models" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_with_empty_arguments(self):
        """Test that tools/call without arguments field defaults to empty dict."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/call", "name": "find_models"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "models" in data

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_list_with_extra_fields(self):
        """Test that tools/list request with extra fields is accepted (Pydantic ignores extra fields by default)."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list", "extra_field": "should be ignored"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "tools" in data
