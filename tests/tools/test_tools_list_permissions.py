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


WRITE_TOOLS = {"create_author", "update_author", "delete_author", "bulk_author", "action_author"}
VIEW_TOOLS = {
    "list_author",
    "get_author",
    "describe_author",
    "actions_author",
    "related_author",
    "history_author",
    "autocomplete_author",
}


def author_tool_names(*codenames):
    user = User.objects.create_user(username=f"toolslist_{unique_id()}", password="pw")
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    # Re-fetch so the permission cache is fresh
    request = create_mock_request(User.objects.get(pk=user.pk))
    return {tool.name for tool in get_tools(request) if tool.name.endswith("_author")}


@pytest.mark.django_db(transaction=True)
class TestGetToolsWriteOperationFiltering:
    """Issue #119: write tools are listed only when the user holds their permission."""

    def test_view_only_user_sees_no_write_tools(self):
        assert author_tool_names("view_author") == VIEW_TOOLS

    def test_add_permission_lists_create_and_bulk(self):
        assert author_tool_names("view_author", "add_author") == VIEW_TOOLS | {"create_author", "bulk_author"}

    def test_change_permission_lists_update_action_and_bulk(self):
        assert author_tool_names("view_author", "change_author") == VIEW_TOOLS | {
            "update_author",
            "action_author",
            "bulk_author",
        }

    def test_delete_permission_lists_delete_and_bulk(self):
        assert author_tool_names("view_author", "delete_author") == VIEW_TOOLS | {"delete_author", "bulk_author"}

    def test_all_permissions_list_every_tool(self):
        names = author_tool_names("view_author", "add_author", "change_author", "delete_author")
        assert names == VIEW_TOOLS | WRITE_TOOLS

    def test_without_request_write_tools_are_listed(self):
        names = {tool.name for tool in get_tools()}
        assert WRITE_TOOLS <= names


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestToolsListEndpointWriteFiltering:
    """Issue #119: the JSON-RPC tools/list response hides unusable write tools."""

    async def test_view_only_token_sees_no_write_tools(self):
        token = await make_token_with_perms("view_author")

        status, data = await list_tools_rpc(token)

        assert status == 200
        names = {tool["name"] for tool in data["result"]["tools"]}
        assert names == VIEW_TOOLS | {"find_models"}

    async def test_change_token_sees_update_action_and_bulk(self):
        token = await make_token_with_perms("view_author", "change_author")

        status, data = await list_tools_rpc(token)

        assert status == 200
        names = {tool["name"] for tool in data["result"]["tools"]}
        assert names == VIEW_TOOLS | {"find_models", "update_author", "action_author", "bulk_author"}
