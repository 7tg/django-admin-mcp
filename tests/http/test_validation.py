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
            "/api/",
            data=json.dumps({"id": 1, "method": "invalid/method"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        # JSON-RPC method-not-found envelope (issue #97); id-less requests
        # are notifications and get an empty 202 instead (issue #108)
        assert data["error"]["code"] == -32601
        assert "invalid/method" in data["error"]["message"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_missing_name_field(self):
        """Test that tools/call request without name field is rejected with validation error."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/",
            data=json.dumps({"method": "tools/call"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        # JSON-RPC invalid-params envelope with sanitized details (issue #97)
        assert data["error"]["code"] == -32602
        assert isinstance(data["error"]["data"], list)
        assert len(data["error"]["data"]) > 0

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_with_valid_arguments(self):
        """Test that tools/call with valid arguments works correctly."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/",
            data=json.dumps(
                {"method": "tools/call", "params": {"name": "find_models", "arguments": {"query": "article"}}}
            ),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        # Response is now JSON-RPC wrapped
        assert "result" in data
        assert "content" in data["result"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_call_with_empty_arguments(self):
        """Test that tools/call without arguments field defaults to empty dict."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/",
            data=json.dumps({"method": "tools/call", "params": {"name": "find_models"}}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        # Response is now JSON-RPC wrapped
        assert "result" in data
        assert "content" in data["result"]

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_list_with_extra_fields(self):
        """Test that tools/list request with extra fields is accepted (Pydantic ignores extra fields by default)."""
        token = await sync_to_async(MCPTokenFactory)()

        client = AsyncClient()
        response = await client.post(
            "/api/",
            data=json.dumps({"method": "tools/list", "extra_field": "should be ignored"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "result" in data
        assert "tools" in data["result"]
