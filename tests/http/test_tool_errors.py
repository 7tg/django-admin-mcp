"""
Tool failures are signalled the way the MCP spec describes (issue #126):

- a tool that ran and failed (record not found, invalid field, permission
  denied) returns a ``tools/call`` result with ``isError: true``;
- a tool name that does not resolve is a JSON-RPC ``-32602`` error, not a
  result whose text happens to say ``Unknown operation``.
"""

import json

import django
import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import Permission, User
from django.test import AsyncClient

from tests.factories import MCPTokenFactory

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)


@sync_to_async
def make_token(*codenames):
    user = User.objects.create_user(username=f"iserror_{User.objects.count()}", password="test")
    if codenames:
        perms = Permission.objects.filter(codename__in=codenames)
        user.user_permissions.add(*perms)
    token = MCPTokenFactory(user=user)
    if codenames:
        token.permissions.add(*perms)
    return token


async def call_tool_rpc(token, name, arguments=None):
    client = AsyncClient()
    payload = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    response = await client.post(
        "/api/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )
    assert response.status_code == 200
    return json.loads(response.content)


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestToolResultIsError:
    """Failed tool executions carry ``isError: true`` on the result."""

    @pytest.mark.asyncio
    async def test_not_found_sets_is_error(self):
        token = await make_token("view_author")

        data = await call_tool_rpc(token, "get_author", {"id": 999999})

        assert "error" not in data, "a tool that ran must answer with a result, not a protocol error"
        assert data["result"]["isError"] is True
        assert "error" in json.loads(data["result"]["content"][0]["text"])

    @pytest.mark.asyncio
    async def test_invalid_field_sets_is_error(self):
        token = await make_token("view_author", "change_author")

        data = await call_tool_rpc(token, "update_author", {"id": 1, "data": {"bogus": 1}})

        assert data["result"]["isError"] is True

    @pytest.mark.asyncio
    async def test_permission_denied_is_a_tool_error_not_a_protocol_error(self):
        token = await make_token()

        data = await call_tool_rpc(token, "list_author")

        assert "error" not in data
        assert data["result"]["isError"] is True
        assert json.loads(data["result"]["content"][0]["text"])["code"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_success_is_not_an_error(self):
        token = await make_token("view_author")

        data = await call_tool_rpc(token, "list_author")

        assert data["result"]["isError"] is False
        assert "error" not in json.loads(data["result"]["content"][0]["text"])

    @pytest.mark.asyncio
    async def test_error_payload_text_is_unchanged(self):
        """Clients that parse the JSON text keep working: the payload is the same."""
        token = await make_token("view_author")

        data = await call_tool_rpc(token, "get_author", {"id": 999999})

        assert json.loads(data["result"]["content"][0]["text"]) == {"error": "author not found"}


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestUnknownToolIsInvalidParams:
    """A tool name that does not resolve is JSON-RPC ``-32602`` naming the tool."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "no_such_tool",  # unknown operation (was reported as "Unknown operation: no")
            "frobnicate_author",  # unknown operation on a known model
            "list_nosuchmodel",  # known operation on an unregistered model
            "nounderscore",  # no operation/model split at all
        ],
    )
    async def test_unknown_tool_name(self, name):
        token = await make_token("view_author")

        data = await call_tool_rpc(token, name)

        assert "result" not in data
        assert data["error"]["code"] == -32602
        assert name in data["error"]["message"]
        assert data["id"] == 7
