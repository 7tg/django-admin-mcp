"""
Tests for MCPAdminMixin functionality
"""

import pytest

from django_admin_mcp import MCPAdminMixin, get_registered_models, get_server
from tests.models import Article, Author


@pytest.mark.django_db
class TestMCPAdminMixin:
    """Test suite for MCPAdminMixin."""

    def test_models_registered(self):
        """Test that models are registered with MCP."""
        registered = get_registered_models()
        assert "article" in registered, "Article model should be registered"
        assert "author" in registered, "Author model should be registered"

    def test_server_created(self):
        """Test that MCP server is created."""
        server = get_server()
        assert server is not None, "MCP server should be created"
        assert server.name == "django-admin-mcp"

    def test_tools_generated_for_author(self):
        """Test that correct tools are generated for Author model."""
        author_tools = MCPAdminMixin.get_mcp_tools(Author)
        tool_names = [t.name for t in author_tools]

        expected_tools = [
            "list_author",
            "get_author",
            "create_author",
            "update_author",
            "delete_author",
            "find_author",
        ]
        assert (
            tool_names == expected_tools
        ), f"Expected {expected_tools}, got {tool_names}"

    def test_tools_generated_for_article(self):
        """Test that correct tools are generated for Article model."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        tool_names = [t.name for t in article_tools]

        expected_tools = [
            "list_article",
            "get_article",
            "create_article",
            "update_article",
            "delete_article",
            "find_article",
        ]
        assert (
            tool_names == expected_tools
        ), f"Expected {expected_tools}, got {tool_names}"

    def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)

        for tool in article_tools:
            assert (
                tool.inputSchema is not None
            ), f"Tool {tool.name} should have an input schema"
            assert (
                "type" in tool.inputSchema
            ), f"Tool {tool.name} schema should have a type"
            assert (
                tool.inputSchema["type"] == "object"
            ), f"Tool {tool.name} schema type should be object"

    def test_list_tool_has_pagination(self):
        """Test that list tool has pagination parameters."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        list_tool = next(t for t in article_tools if t.name == "list_article")

        assert "properties" in list_tool.inputSchema
        assert "limit" in list_tool.inputSchema["properties"]
        assert "offset" in list_tool.inputSchema["properties"]

    def test_get_tool_requires_id(self):
        """Test that get tool requires id parameter."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        get_tool = next(t for t in article_tools if t.name == "get_article")

        assert "required" in get_tool.inputSchema
        assert "id" in get_tool.inputSchema["required"]

    def test_create_tool_requires_data(self):
        """Test that create tool requires data parameter."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        create_tool = next(t for t in article_tools if t.name == "create_article")

        assert "required" in create_tool.inputSchema
        assert "data" in create_tool.inputSchema["required"]

    def test_update_tool_requires_id_and_data(self):
        """Test that update tool requires id and data parameters."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        update_tool = next(t for t in article_tools if t.name == "update_article")

        assert "required" in update_tool.inputSchema
        assert "id" in update_tool.inputSchema["required"]
        assert "data" in update_tool.inputSchema["required"]

    def test_delete_tool_requires_id(self):
        """Test that delete tool requires id parameter."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        delete_tool = next(t for t in article_tools if t.name == "delete_article")

        assert "required" in delete_tool.inputSchema
        assert "id" in delete_tool.inputSchema["required"]
