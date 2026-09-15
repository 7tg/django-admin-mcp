"""
JSON-RPC error compliance for the mcp_endpoint (issue #97).

Error conditions must come back as JSON-RPC error envelopes with HTTP 200
(standard codes -32700/-32601/-32602), and notifications get no response body.
"""

import json

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

from tests.factories import MCPTokenFactory


@sync_to_async
def make_token():
    return MCPTokenFactory()


async def post_mcp(payload, token, raw=None):
    client = AsyncClient()
    return await client.post(
        "/api/",
        data=raw if raw is not None else json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestJsonRpcErrorEnvelopes:
    async def test_parse_error_returns_32700_envelope(self):
        token = await make_token()

        response = await post_mcp(None, token, raw="{not valid json")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["jsonrpc"] == "2.0"
        assert data["error"]["code"] == -32700

    async def test_unknown_method_returns_32601_envelope_with_id(self):
        token = await make_token()

        response = await post_mcp({"jsonrpc": "2.0", "id": 7, "method": "no/such"}, token)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 7
        assert data["error"]["code"] == -32601

    async def test_invalid_tools_call_params_returns_32602_envelope(self):
        token = await make_token()

        response = await post_mcp({"jsonrpc": "2.0", "id": "abc", "method": "tools/call", "params": {}}, token)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["id"] == "abc"
        assert data["error"]["code"] == -32602

    async def test_notification_gets_no_response_body(self):
        token = await make_token()

        response = await post_mcp({"jsonrpc": "2.0", "method": "notifications/initialized"}, token)

        assert response.status_code == 202
        assert response.content == b""
