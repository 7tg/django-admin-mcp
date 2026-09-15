"""
Tests for issue #108: JSON-RPC notifications (requests without an id) must
never receive a response body — not even an error envelope.
"""

import json

import django
import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

from tests.factories import MCPTokenFactory

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)


async def post_rpc(token, payload):
    client = AsyncClient()
    return await client.post(
        "/api/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )


@skip_if_django_lt_42
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestNotificationHandling:
    """Notifications get an empty 202; unknown *requests* keep METHOD_NOT_FOUND."""

    async def test_notifications_initialized_gets_empty_202(self):
        token = await sync_to_async(MCPTokenFactory)()
        response = await post_rpc(token, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert response.status_code == 202
        assert response.content == b""

    async def test_notifications_cancelled_gets_empty_202(self):
        token = await sync_to_async(MCPTokenFactory)()
        response = await post_rpc(
            token,
            {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7}},
        )
        assert response.status_code == 202
        assert response.content == b""

    async def test_notifications_roots_list_changed_gets_empty_202(self):
        token = await sync_to_async(MCPTokenFactory)()
        response = await post_rpc(token, {"jsonrpc": "2.0", "method": "notifications/roots/list_changed"})
        assert response.status_code == 202
        assert response.content == b""

    async def test_unknown_request_with_id_still_gets_method_not_found(self):
        token = await sync_to_async(MCPTokenFactory)()
        response = await post_rpc(token, {"jsonrpc": "2.0", "id": 5, "method": "no/such/method"})
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["error"]["code"] == -32601
        assert data["id"] == 5

    async def test_unknown_method_without_id_gets_empty_202(self):
        token = await sync_to_async(MCPTokenFactory)()
        response = await post_rpc(token, {"jsonrpc": "2.0", "method": "no/such/method"})
        assert response.status_code == 202
        assert response.content == b""
