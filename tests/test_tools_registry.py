"""
Tests for django_admin_mcp.tools.registry module.

Tests tool registration, routing, and schema generation.
"""

import json

import pytest
from django.test import RequestFactory

from django_admin_mcp.protocol.types import TextContent, Tool
from django_admin_mcp.tools import (
    HANDLERS,
    call_tool,
    get_find_models_tool,
    get_model_tools,
    get_tools,
)
from django_admin_mcp.tools.registry import (
    _format_fields_doc,
    _get_field_info,
)


class TestHandlersRegistry:
    """Test HANDLERS mapping."""

    def test_handlers_contains_all_operations(self):
        """HANDLERS should contain all expected operation handlers."""
        expected_operations = [
            "list",
            "get",
            "create",
            "update",
            "delete",
            "describe",
            "actions",
            "action",
            "bulk",
            "related",
            "history",
            "autocomplete",
        ]
        for op in expected_operations:
            assert op in HANDLERS, f"Missing handler for {op}"


class TestCallTool:
    """Test call_tool function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_call_tool_find_models(self, django_setup_with_admin):
        """call_tool should route find_models correctly."""
        request = RequestFactory().get("/")
        request.user = None

        result = await call_tool("find_models", {}, request)

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        data = json.loads(result[0].text)
        assert "count" in data
        assert "models" in data

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_call_tool_list_operation(self, django_setup_with_admin):
        """call_tool should route list operations correctly."""
        from asgiref.sync import sync_to_async
        from django.contrib.auth.models import User

        @sync_to_async
        def create_user():
            return User.objects.create_superuser("admin", "admin@test.com", "password")

        user = await create_user()
        request = RequestFactory().get("/")
        request.user = user

        result = await call_tool("list_author", {}, request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "count" in data
        assert "results" in data

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_call_tool_invalid_format(self, django_setup_with_admin):
        """call_tool should return error for invalid tool name format."""
        request = RequestFactory().get("/")
        request.user = None

        result = await call_tool("invalidformat", {}, request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Invalid tool name format" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_call_tool_unknown_operation(self, django_setup_with_admin):
        """call_tool should return error for unknown operations."""
        request = RequestFactory().get("/")
        request.user = None

        result = await call_tool("unknown_author", {}, request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Unknown operation" in data["error"]


class TestGetFieldInfo:
    """Test _get_field_info function."""

    @pytest.mark.django_db
    def test_get_field_info_returns_fields(self, django_setup_with_admin):
        """_get_field_info should return field information."""
        from tests.models import Author

        fields = _get_field_info(Author)

        assert len(fields) > 0
        field_names = [f["name"] for f in fields]
        assert "name" in field_names
        assert "email" in field_names

    @pytest.mark.django_db
    def test_get_field_info_includes_required_status(self, django_setup_with_admin):
        """_get_field_info should include required status."""
        from tests.models import Author

        fields = _get_field_info(Author)

        name_field = next(f for f in fields if f["name"] == "name")
        assert "required" in name_field
        assert "type" in name_field


class TestFormatFieldsDoc:
    """Test _format_fields_doc function."""

    def test_format_fields_doc_basic(self):
        """_format_fields_doc should format fields correctly."""
        fields = [
            {"name": "title", "type": "CharField", "required": True},
            {"name": "body", "type": "TextField", "required": False},
        ]

        doc = _format_fields_doc(fields)

        assert "title" in doc
        assert "CharField" in doc
        assert "[required]" in doc
        assert "body" in doc
        assert "TextField" in doc

    def test_format_fields_doc_empty(self):
        """_format_fields_doc should handle empty list."""
        doc = _format_fields_doc([])
        assert doc == ""


class TestGetModelTools:
    """Test get_model_tools function."""

    @pytest.mark.django_db
    def test_get_model_tools_returns_all_operations(self, django_setup_with_admin):
        """get_model_tools should return tools for all operations."""
        from tests.models import Author

        tools = get_model_tools(Author)

        tool_names = [t.name for t in tools]
        expected_tools = [
            "list_author",
            "get_author",
            "create_author",
            "update_author",
            "delete_author",
            "describe_author",
            "actions_author",
            "action_author",
            "bulk_author",
            "related_author",
            "history_author",
            "autocomplete_author",
        ]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool {expected}"

    @pytest.mark.django_db
    def test_get_model_tools_includes_field_documentation(self, django_setup_with_admin):
        """get_model_tools should include field documentation in descriptions."""
        from tests.models import Author

        tools = get_model_tools(Author)

        list_tool = next(t for t in tools if t.name == "list_author")
        assert "name" in list_tool.description
        assert "email" in list_tool.description

    @pytest.mark.django_db
    def test_get_model_tools_schema_structure(self, django_setup_with_admin):
        """get_model_tools should generate valid schema structure."""
        from tests.models import Author

        tools = get_model_tools(Author)

        list_tool = next(t for t in tools if t.name == "list_author")
        assert list_tool.inputSchema["type"] == "object"
        assert "properties" in list_tool.inputSchema

        get_tool = next(t for t in tools if t.name == "get_author")
        assert "required" in get_tool.inputSchema
        assert "id" in get_tool.inputSchema["required"]


class TestGetFindModelsTool:
    """Test get_find_models_tool function."""

    def test_get_find_models_tool_returns_tool(self):
        """get_find_models_tool should return a Tool instance."""
        tool = get_find_models_tool()

        assert isinstance(tool, Tool)
        assert tool.name == "find_models"
        assert "Discover" in tool.description
        assert tool.inputSchema["type"] == "object"
        assert "query" in tool.inputSchema["properties"]


class TestGetTools:
    """Test get_tools function."""

    @pytest.mark.django_db
    def test_get_tools_includes_find_models(self, django_setup_with_admin):
        """get_tools should include find_models tool."""
        tools = get_tools()

        tool_names = [t.name for t in tools]
        assert "find_models" in tool_names

    @pytest.mark.django_db
    def test_get_tools_includes_model_tools(self, django_setup_with_admin):
        """get_tools should include tools for exposed models."""
        tools = get_tools()

        tool_names = [t.name for t in tools]
        # Author and Article should be exposed via mcp_expose=True
        assert "list_author" in tool_names
        assert "list_article" in tool_names
