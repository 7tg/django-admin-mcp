"""
Tests for issue #102: fields hidden by mcp_fields/mcp_exclude_fields must not
appear in tool descriptions, describe_* output, or the schema resource.
"""

import json
import uuid
from contextlib import contextmanager

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, get_model_admin, handle_describe
from django_admin_mcp.models import MCPToken
from django_admin_mcp.tools import get_model_tools
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@contextmanager
def admin_attrs(model_name, **attrs):
    """Temporarily set attributes on a registered model admin."""
    _, model_admin = get_model_admin(model_name)
    originals = {name: getattr(model_admin, name, None) for name in attrs}
    for name, value in attrs.items():
        setattr(model_admin, name, value)
    try:
        yield model_admin
    finally:
        for name, value in originals.items():
            setattr(model_admin, name, value)


@sync_to_async
def create_superuser(uid):
    return User.objects.create_superuser(
        username=f"schema_vis_{uid}",
        email=f"schema_vis_{uid}@example.com",
        password="pw",
    )


class TestToolDescriptionVisibility:
    """Tool descriptions must not embed metadata of hidden fields."""

    def test_mcptoken_tool_descriptions_hide_excluded_fields(self):
        tools = {tool.name: tool for tool in get_model_tools(MCPToken)}
        for tool_name in ("list_mcptoken", "create_mcptoken", "update_mcptoken"):
            description = tools[tool_name].description
            assert "token_key" not in description, tool_name
            assert "token_hash" not in description, tool_name
            assert "salt" not in description, tool_name
        # Non-sensitive fields stay documented
        assert "name" in tools["create_mcptoken"].description

    def test_mcp_fields_include_list_limits_tool_descriptions(self):
        with admin_attrs("author", mcp_fields=["name"]):
            tools = {tool.name: tool for tool in get_model_tools(Author)}
            description = tools["create_author"].description
            assert "name" in description
            assert "email" not in description
            assert "bio" not in description


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDescribeVisibility:
    """describe_* must not return metadata for hidden fields."""

    async def test_describe_mcptoken_hides_excluded_fields(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))

        result = await handle_describe("mcptoken", {}, request)
        data = json.loads(result[0].text)

        field_names = {f["name"] for f in data["fields"]}
        assert "token_key" not in field_names
        assert "token_hash" not in field_names
        assert "salt" not in field_names
        assert "name" in field_names
        # Relationships unaffected by the exclude list
        relation_names = {r["name"] for r in data["relationships"]}
        assert "user" in relation_names

    async def test_describe_honors_mcp_fields_include_list(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))

        with admin_attrs("author", mcp_fields=["name"]):
            result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        field_names = {f["name"] for f in data["fields"]}
        assert field_names == {"name"}
        # Reverse relations stay discoverable for related_* even under an
        # include list (they are never serialized fields)
        relation_names = {r["name"] for r in data["relationships"]}
        assert "articles" in relation_names
