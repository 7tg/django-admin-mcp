"""
Tests for Pydantic input validation
"""

import json

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
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
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
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
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
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
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
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
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
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "tools" in data
