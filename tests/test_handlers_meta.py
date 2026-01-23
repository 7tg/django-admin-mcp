"""
Tests for django_admin_mcp.handlers.meta module.

Tests metadata operation handlers:
- handle_describe: Get model schema and admin configuration
- handle_find_models: Discover MCP-exposed models
"""

import json

import pytest

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_describe,
    handle_find_models,
)
from django_admin_mcp.handlers.meta import (
    _get_field_metadata,
    _model_matches_query,
)
from tests.models import Article, Author


class TestModelMatchesQuery:
    """Tests for _model_matches_query helper function."""

    def test_empty_query_matches_everything(self):
        """Test that empty query matches any model."""
        assert _model_matches_query("", "author", "Author") is True
        assert _model_matches_query("", "article", "Article") is True

    def test_matches_model_name(self):
        """Test matching against model name."""
        assert _model_matches_query("auth", "author", "Author") is True
        assert _model_matches_query("AUTHOR", "author", "Author") is True

    def test_matches_verbose_name(self):
        """Test matching against verbose name."""
        assert _model_matches_query("Auth", "author", "Author") is True

    def test_no_match(self):
        """Test query that doesn't match."""
        assert _model_matches_query("xyz", "author", "Author") is False


class TestGetFieldMetadata:
    """Tests for _get_field_metadata helper function."""

    def test_extracts_basic_field_info(self):
        """Test extracting basic field information."""
        field = Author._meta.get_field("name")
        meta = _get_field_metadata(field)
        assert meta["name"] == "name"
        assert meta["type"] == "CharField"
        assert "verbose_name" in meta

    def test_extracts_required_status(self):
        """Test extracting required status for CharField."""
        field = Author._meta.get_field("name")
        meta = _get_field_metadata(field)
        # name is CharField without blank=True, null=True, so should be required
        assert meta["required"] is True

    def test_extracts_optional_status(self):
        """Test extracting optional status for TextField with blank=True."""
        field = Author._meta.get_field("bio")
        meta = _get_field_metadata(field)
        # bio is TextField with blank=True
        assert meta["required"] is False

    def test_extracts_max_length(self):
        """Test extracting max_length for CharField."""
        field = Author._meta.get_field("name")
        meta = _get_field_metadata(field)
        assert meta["max_length"] == 200

    def test_extracts_foreign_key_info(self):
        """Test extracting ForeignKey relationship info."""
        field = Article._meta.get_field("author")
        meta = _get_field_metadata(field)
        assert meta["related_model"] == "author"
        assert meta["related_app"] == "tests"
        assert meta["on_delete"] == "CASCADE"

    def test_extracts_primary_key(self):
        """Test extracting primary key info."""
        field = Author._meta.get_field("id")
        meta = _get_field_metadata(field)
        assert meta.get("primary_key") is True

    def test_extracts_unique(self):
        """Test extracting unique constraint."""
        field = Author._meta.get_field("email")
        meta = _get_field_metadata(field)
        assert meta.get("unique") is True

    def test_extracts_boolean_default(self):
        """Test extracting default value for BooleanField."""
        field = Article._meta.get_field("is_published")
        meta = _get_field_metadata(field)
        assert meta.get("default") is False


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHandleDescribe:
    """Tests for handle_describe async handler."""

    async def test_returns_model_metadata(self):
        """Test that handle_describe returns model metadata."""
        request = create_mock_request()
        result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        assert data["model_name"] == "author"
        assert "verbose_name" in data
        assert "verbose_name_plural" in data
        assert "app_label" in data
        assert "fields" in data
        assert "relationships" in data
        assert "admin_config" in data

    async def test_includes_fields_metadata(self):
        """Test that field metadata is included."""
        request = create_mock_request()
        result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        field_names = [f["name"] for f in data["fields"]]
        assert "name" in field_names
        assert "email" in field_names
        assert "bio" in field_names

    async def test_includes_admin_config(self):
        """Test that admin configuration is included."""
        request = create_mock_request()
        result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        admin_config = data["admin_config"]
        assert "list_display" in admin_config
        assert "search_fields" in admin_config
        assert "ordering" in admin_config

    async def test_includes_inlines_config(self):
        """Test that inlines configuration is included for Author."""
        request = create_mock_request()
        result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        admin_config = data["admin_config"]
        assert "inlines" in admin_config
        assert len(admin_config["inlines"]) > 0
        assert admin_config["inlines"][0]["model"] == "article"

    async def test_returns_relationships(self):
        """Test that relationships are included for Article."""
        request = create_mock_request()
        result = await handle_describe("article", {}, request)
        data = json.loads(result[0].text)

        # Article has FK to Author
        assert len(data["relationships"]) > 0
        rel_names = [r["name"] for r in data["relationships"]]
        assert "author" in rel_names

    async def test_handles_nonexistent_model(self):
        """Test error handling for nonexistent model."""
        request = create_mock_request()
        result = await handle_describe("nonexistent", {}, request)
        data = json.loads(result[0].text)

        assert "error" in data
        assert "nonexistent" in data["error"]


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHandleFindModels:
    """Tests for handle_find_models async handler."""

    async def test_returns_count_and_models(self):
        """Test that result contains count and models list."""
        request = create_mock_request()
        result = await handle_find_models("", {}, request)
        data = json.loads(result[0].text)

        assert "count" in data
        assert "models" in data
        assert isinstance(data["models"], list)

    async def test_includes_exposed_models(self):
        """Test that MCP-exposed models are included."""
        request = create_mock_request()
        result = await handle_find_models("", {}, request)
        data = json.loads(result[0].text)

        model_names = [m["model_name"] for m in data["models"]]
        assert "author" in model_names
        assert "article" in model_names

    async def test_model_info_structure(self):
        """Test that model info contains expected fields."""
        request = create_mock_request()
        result = await handle_find_models("", {}, request)
        data = json.loads(result[0].text)

        # Find the author model
        author_info = next((m for m in data["models"] if m["model_name"] == "author"), None)
        assert author_info is not None
        assert "verbose_name" in author_info
        assert "verbose_name_plural" in author_info
        assert "app_label" in author_info
        assert "tools_exposed" in author_info
        assert author_info["tools_exposed"] is True

    async def test_filters_by_query(self):
        """Test filtering models by query string."""
        request = create_mock_request()
        result = await handle_find_models("", {"query": "auth"}, request)
        data = json.loads(result[0].text)

        model_names = [m["model_name"] for m in data["models"]]
        assert "author" in model_names
        # Article should not match "auth"
        assert "article" not in model_names
