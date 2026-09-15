"""
Tests for MCPAdminMixin functionality
"""

import logging
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import models as dj_models

from django_admin_mcp import MCPAdminMixin
from tests.models import Article, Author


@pytest.mark.django_db
class TestMCPAdminMixin:
    """Test suite for MCPAdminMixin."""

    def test_models_registered(self):
        """Test that models are registered with MCP."""
        registered = MCPAdminMixin._registered_models
        assert "article" in registered, "Article model should be registered"
        assert "author" in registered, "Author model should be registered"

    def test_tools_generated_for_model(self):
        """Test that correct tools are generated for Article model."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        tool_names = [t.name for t in article_tools]

        expected_tools = [
            "list_article",
            "get_article",
            "create_article",
            "update_article",
            "delete_article",
            "describe_article",
            "actions_article",
            "action_article",
            "bulk_article",
            "related_article",
            "history_article",
            "autocomplete_article",
        ]
        assert tool_names == expected_tools, f"Expected {expected_tools}, got {tool_names}"

    def test_tool_schemas_valid(self):
        """Test that tool schemas are valid."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)

        for tool in article_tools:
            assert tool.inputSchema is not None, f"Tool {tool.name} should have an input schema"
            assert "type" in tool.inputSchema, f"Tool {tool.name} schema should have a type"
            assert tool.inputSchema["type"] == "object", f"Tool {tool.name} schema type should be object"

    def test_tool_schemas_have_expected_structure(self):
        """Test that tool schemas have expected structure for key operations."""
        article_tools = MCPAdminMixin.get_mcp_tools(Article)
        tools_by_name = {t.name: t for t in article_tools}

        # List tool has pagination
        list_tool = tools_by_name["list_article"]
        assert "limit" in list_tool.inputSchema["properties"]
        assert "offset" in list_tool.inputSchema["properties"]

        # Update tool has id required, with optional data and inlines
        update_tool = tools_by_name["update_article"]
        assert "id" in update_tool.inputSchema["required"]
        assert "data" in update_tool.inputSchema["properties"]
        assert "inlines" in update_tool.inputSchema["properties"]

    def test_find_models_tool_generated(self):
        """Test that find_models tool is generated."""
        find_models_tool = MCPAdminMixin.get_find_models_tool()
        assert find_models_tool.name == "find_models"
        assert "properties" in find_models_tool.inputSchema
        assert "query" in find_models_tool.inputSchema["properties"]


class TestModelNameCollision:
    """Cross-app model_name collisions must not be silently dropped (issue #99)."""

    def _make_colliding_author(self):
        meta = type("Meta", (), {"app_label": "collision_test"})
        clone = type(
            "Author",
            (dj_models.Model,),
            {"__module__": "tests.collision_models", "Meta": meta},
        )

        def cleanup():
            apps.all_models["collision_test"].pop("author", None)
            apps.clear_cache()

        return clone, cleanup

    def test_collision_with_different_model_warns_and_keeps_first(self, caplog):
        assert MCPAdminMixin._registered_models["author"]["model"] is Author

        clone, cleanup = self._make_colliding_author()
        try:
            with caplog.at_level(logging.WARNING, logger="django_admin_mcp"):
                MCPAdminMixin.register_model_tools(SimpleNamespace(model=clone))

            # First registration wins...
            assert MCPAdminMixin._registered_models["author"]["model"] is Author
            # ...and the dropped registration is reported
            assert any(
                "collision" in record.message.lower() and "author" in record.message.lower()
                for record in caplog.records
            )
        finally:
            cleanup()

    def test_reregistering_same_model_does_not_warn(self, caplog):
        with caplog.at_level(logging.WARNING, logger="django_admin_mcp"):
            MCPAdminMixin.register_model_tools(SimpleNamespace(model=Author))

        assert not caplog.records
        assert MCPAdminMixin._registered_models["author"]["model"] is Author
