"""
End-to-end tests: HTTP authorization is enforced from the token's effective
permissions — the token's own permissions/groups capped by the linked user's
permissions. A token can narrow its user's access, never extend it, and even
a superuser-bound token has no access unless permissions are granted on it.
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
def make_superuser_token():
    superuser = User.objects.create_superuser(
        username=f"enforce_super_{User.objects.count()}",
        email="enforce_super@example.com",
        password="test",
    )
    return MCPTokenFactory(user=superuser)


@sync_to_async
def make_token_with_perms(*codenames, user_codenames=None):
    """Token granted `codenames`; its user holds `user_codenames` (defaults to the same)."""
    user = User.objects.create_user(
        username=f"enforce_user_{User.objects.count()}",
        password="test",
    )
    user_perms = codenames if user_codenames is None else user_codenames
    if user_perms:
        user.user_permissions.add(*Permission.objects.filter(codename__in=user_perms))
    token = MCPTokenFactory(user=user)
    if codenames:
        token.permissions.add(*Permission.objects.filter(codename__in=codenames))
    return token


async def call_tool_rpc(token, name, arguments=None):
    client = AsyncClient()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    response = await client.post(
        "/api/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )
    data = json.loads(response.content)
    return response.status_code, data


def tool_payload(data):
    return json.loads(data["result"]["content"][0]["text"])


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestTokenPermissionEnforcement:
    """Token permissions — not the linked user's — authorize HTTP tool calls."""

    @pytest.mark.asyncio
    async def test_superuser_bound_token_without_permissions_is_denied(self):
        """A token with no permissions is denied even when bound to a superuser."""
        token = await make_superuser_token()

        status, data = await call_tool_rpc(token, "list_author")

        assert status == 200
        payload = tool_payload(data)
        assert payload.get("code") == "permission_denied"

    @pytest.mark.asyncio
    async def test_token_grant_exceeding_user_permissions_is_denied(self):
        """A token granted view_author whose user lacks it gets no access — the user caps the token."""
        token = await make_token_with_perms("view_author", user_codenames=())

        status, data = await call_tool_rpc(token, "list_author")

        assert status == 200
        payload = tool_payload(data)
        assert payload.get("code") == "permission_denied"

    @pytest.mark.asyncio
    async def test_token_level_view_permission_grants_access(self):
        """A token holding view_author (also held by its user) can list authors."""
        token = await make_token_with_perms("view_author")

        status, data = await call_tool_rpc(token, "list_author")

        assert status == 200
        payload = tool_payload(data)
        assert "results" in payload, payload

    @pytest.mark.asyncio
    async def test_token_view_permission_does_not_grant_create(self):
        """Holding only view_author must not allow create_author."""
        token = await make_token_with_perms("view_author")

        status, data = await call_tool_rpc(
            token, "create_author", {"data": {"name": "Denied", "email": "denied@example.com"}}
        )

        assert status == 200
        payload = tool_payload(data)
        assert payload.get("code") == "permission_denied"
