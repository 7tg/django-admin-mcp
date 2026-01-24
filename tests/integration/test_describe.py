"""
Tests for describe_<model_name> tool
"""

import json

import pytest

from django_admin_mcp import MCPAdminMixin


@pytest.mark.django_db
@pytest.mark.asyncio
class TestDescribeModel:
    """Test suite for describe_<model_name> tool."""

    async def test_describe_author(self):
        """Test describing the Author model."""
        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        # Check basic model info
        assert response["model_name"] == "author"
        assert "verbose_name" in response
        assert "fields" in response
        assert "relationships" in response
        assert "admin_config" in response

    async def test_describe_fields(self):
        """Test that describe returns correct field metadata."""
        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        # Find specific fields
        field_names = [f["name"] for f in response["fields"]]
        assert "name" in field_names
        assert "email" in field_names
        assert "bio" in field_names

        # Check field details
        name_field = next(f for f in response["fields"] if f["name"] == "name")
        assert name_field["type"] == "CharField"
        assert name_field["max_length"] == 200
        assert name_field["required"] is True

    async def test_describe_relationships(self):
        """Test that describe returns relationship info."""
        result = await MCPAdminMixin.handle_tool_call("describe_article", {})
        response = json.loads(result[0].text)

        # Article has FK to Author
        relationships = response["relationships"]
        author_rel = next((r for r in relationships if r["name"] == "author"), None)
        assert author_rel is not None
        assert author_rel["related_model"] == "author"

    async def test_describe_admin_config(self):
        """Test that describe returns admin configuration."""
        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        admin_config = response["admin_config"]
        assert "list_display" in admin_config
        assert "search_fields" in admin_config
        assert "ordering" in admin_config

        # Check configured values from conftest.py
        assert "name" in admin_config["list_display"]
        assert "email" in admin_config["list_display"]
        assert "name" in admin_config["search_fields"]
        assert "name" in admin_config["ordering"]
