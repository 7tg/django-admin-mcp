"""
Tests for issue #101: tools/list must be filtered by the requesting token's
permissions, mirroring find_models and resources/list.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import Permission, User
from django.test import AsyncClient

from django_admin_mcp.handlers import create_mock_request
from django_admin_mcp.tools import get_tools
from tests.factories import MCPTokenFactory


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def make_user_with_perms(*codenames):
    user = User.objects.create_user(username=f"toolslist_{unique_id()}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


@sync_to_async
def make_token_with_perms(*codenames):
    user = User.objects.create_user(username=f"toolslist_tok_{unique_id()}", password="pw")
    if codenames:
        perms = Permission.objects.filter(codename__in=codenames)
        user.user_permissions.add(*perms)
    token = MCPTokenFactory(user=user)
    if codenames:
        token.permissions.add(*Permission.objects.filter(codename__in=codenames))
    return token


async def list_tools_rpc(token):
    client = AsyncClient()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    response = await client.post(
        "/api/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )
    return response.status_code, json.loads(response.content)


@pytest.mark.django_db(transaction=True)
class TestGetToolsPermissionFiltering:
    """get_tools(request) must skip models the user cannot view."""

    def test_get_tools_without_request_returns_all(self):
        names = {tool.name for tool in get_tools()}
        assert "find_models" in names
        assert "list_author" in names
        assert "list_article" in names

    def test_get_tools_filters_by_view_permission(self):
        user = User.objects.create_user(username=f"toolslist_{unique_id()}", password="pw")
        user.user_permissions.add(Permission.objects.get(codename="view_author"))
        # Re-fetch so the permission cache is fresh
        user = User.objects.get(pk=user.pk)
        request = create_mock_request(user)

        names = {tool.name for tool in get_tools(request)}

        assert "find_models" in names
        assert "list_author" in names
        assert "list_article" not in names
        assert "list_mcptoken" not in names

    def test_get_tools_with_no_permissions_returns_only_find_models(self):
        user = User.objects.create_user(username=f"toolslist_{unique_id()}", password="pw")
        request = create_mock_request(user)

        names = {tool.name for tool in get_tools(request)}

        assert names == {"find_models"}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestToolsListEndpointFiltering:
    """The JSON-RPC tools/list response must honor the token's permissions."""

    async def test_zero_permission_token_sees_only_find_models(self):
        token = await make_token_with_perms()

        status, data = await list_tools_rpc(token)

        assert status == 200
        names = {tool["name"] for tool in data["result"]["tools"]}
        assert names == {"find_models"}

    async def test_token_with_view_author_sees_author_tools_only(self):
        token = await make_token_with_perms("view_author")

        status, data = await list_tools_rpc(token)

        assert status == 200
        names = {tool["name"] for tool in data["result"]["tools"]}
        assert "list_author" in names
        assert "get_author" in names
        assert "list_article" not in names
        assert "list_mcptoken" not in names
