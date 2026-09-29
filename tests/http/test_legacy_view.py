"""
Tests for the legacy class-based ``MCPHTTPView`` (bare-JSON responses) and
token authentication edge cases shared with the JSON-RPC endpoint.
"""

import json
from unittest.mock import patch

import django
import pytest
from asgiref.sync import sync_to_async
from django.db import DatabaseError
from django.test import AsyncRequestFactory

from django_admin_mcp.protocol import TextContent
from django_admin_mcp.views import MCPHTTPView, mcp_endpoint
from tests.factories import MCPTokenFactory

# AsyncRequestFactory headers= parameter requires Django 4.2+
skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncRequestFactory headers= parameter requires Django 4.2+"
)


@sync_to_async
def make_token():
    return MCPTokenFactory()


def post_request(body, token=None, path="/mcp/"):
    """Build a POST request with an optional bearer token."""
    extra = {}
    if token is not None:
        extra["headers"] = {"Authorization": f"Bearer {token}"}
    return AsyncRequestFactory().post(path, data=body, content_type="application/json", **extra)


async def call_view(body, token=None):
    view = MCPHTTPView.as_view()
    return await view(post_request(body, token=token))


@skip_if_django_lt_42
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestMCPHTTPView:
    """The legacy view shares the auth pipeline but returns bare JSON."""

    async def test_missing_token_is_unauthorized(self):
        response = await call_view(json.dumps({"method": "tools/list"}))
        assert response.status_code == 401
        assert "error" in json.loads(response.content)

    async def test_invalid_json_body(self):
        token = await make_token()
        response = await call_view("{not json", token=token.plaintext_token)
        assert response.status_code == 400
        assert json.loads(response.content)["error"] == "Invalid JSON in request body"

    async def test_tools_list(self):
        token = await make_token()
        response = await call_view(json.dumps({"method": "tools/list"}), token=token.plaintext_token)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "tools" in data
        assert all({"name", "description", "inputSchema"} <= set(tool) for tool in data["tools"])

    async def test_tools_call(self):
        token = await make_token()
        body = json.dumps({"method": "tools/call", "name": "find_models", "arguments": {}})
        response = await call_view(body, token=token.plaintext_token)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert "models" in data

    async def test_tools_call_missing_name_is_invalid(self):
        token = await make_token()
        body = json.dumps({"method": "tools/call", "arguments": {}})
        response = await call_view(body, token=token.plaintext_token)
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["error"] == "Invalid request"
        assert "details" in data

    async def test_unknown_method(self):
        token = await make_token()
        response = await call_view(json.dumps({"method": "bogus/method"}), token=token.plaintext_token)
        assert response.status_code == 400
        assert "Unknown method" in json.loads(response.content)["error"]

    async def test_tools_call_empty_result_is_server_error(self):
        token = await make_token()
        body = json.dumps({"method": "tools/call", "name": "find_models", "arguments": {}})
        with patch("django_admin_mcp.views.call_tool", return_value=[]):
            response = await call_view(body, token=token.plaintext_token)
        assert response.status_code == 500
        assert json.loads(response.content)["error"] == "No result from tool"


@skip_if_django_lt_42
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestAuthenticationEdgeCases:
    """Token parsing/verification failure paths in authenticate_token."""

    async def test_valid_key_wrong_secret_is_unauthorized(self):
        token = await make_token()
        tampered = f"mcp_{token.token_key}.deadbeefdeadbeef"
        response = await call_view(json.dumps({"method": "tools/list"}), token=tampered)
        assert response.status_code == 401

    async def test_database_error_is_unauthorized(self):
        token = await make_token()
        with patch("django_admin_mcp.views.MCPToken.get_by_key", side_effect=DatabaseError("boom")):
            response = await call_view(json.dumps({"method": "tools/list"}), token=token.plaintext_token)
        assert response.status_code == 401


@skip_if_django_lt_42
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestToolResultValidation:
    """The JSON-RPC endpoint rejects tool results that are not valid JSON."""

    async def test_invalid_json_tool_result_is_jsonrpc_error(self):
        token = await make_token()
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "find_models", "arguments": {}}}
        )
        fake_result = [TextContent(text="this is not json")]
        with patch("django_admin_mcp.views.call_tool", return_value=fake_result):
            response = await mcp_endpoint(post_request(body, token=token.plaintext_token))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["error"]["code"] == -32000
        assert data["error"]["message"] == "Invalid JSON in tool result"
