"""
Tests for inline and related object operations via MCP tools
"""

import asyncio
import json

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Article, Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestInlineAndRelated:
    """Test suite for inline and related object operations."""

    async def test_get_with_include_related(self):
        """Test getting an object with related data."""
        # Create author with articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Related Author", email="related@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Related Article 1", content="Content 1", author=author),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Related Article 2", content="Content 2", author=author),
        )

        # Get author with related data
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id, "include_related": True})
        response = json.loads(result[0].text)

        assert response["name"] == "Related Author"
        assert "_related" in response
        assert "articles" in response["_related"]
        assert len(response["_related"]["articles"]) == 2

    async def test_get_with_include_inlines(self):
        """Test getting an object with inline data."""
        # Create author with articles (which are configured as inlines)
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Inline Author", email="inline@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Inline Article", content="Content", author=author),
        )

        # Get author with inline data
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id, "include_inlines": True})
        response = json.loads(result[0].text)

        assert response["name"] == "Inline Author"
        assert "_inlines" in response
        assert "article" in response["_inlines"]
        assert len(response["_inlines"]["article"]) >= 1

    async def test_related_navigation(self):
        """Test fetching related objects via related_ tool."""
        # Create author with articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Nav Author", email="nav@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Nav Article 1", content="Content 1", author=author),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Nav Article 2", content="Content 2", author=author),
        )

        # Navigate to related articles
        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id, "relation": "articles"})
        response = json.loads(result[0].text)

        assert response["relation"] == "articles"
        assert response["type"] == "many"
        assert response["total_count"] == 2
        assert len(response["results"]) == 2

    async def test_related_with_pagination(self):
        """Test related navigation with pagination."""
        # Create author with many articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Paginate Author", email="paginate@example.com"),
        )
        for i in range(5):
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda i=i: Article.objects.create(
                    title=f"Paginate Article {i}", content=f"Content {i}", author=author
                ),
            )

        # Get first page
        result = await MCPAdminMixin.handle_tool_call(
            "related_author",
            {"id": author.id, "relation": "articles", "limit": 2, "offset": 0},
        )
        response = json.loads(result[0].text)

        assert response["total_count"] == 5
        assert response["count"] == 2

    async def test_related_invalid_relation(self):
        """Test related navigation with invalid relation name."""
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Invalid Author", email="invalid@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id, "relation": "nonexistent"})
        response = json.loads(result[0].text)

        assert "error" in response
