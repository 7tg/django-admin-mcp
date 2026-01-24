"""
Tests for filtering, searching, and ordering operations via MCP tools
"""

import asyncio
import json

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Article, Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestFilteringSearchingOrdering:
    """Test suite for filtering, searching, and ordering operations."""

    async def test_list_with_filters(self):
        """Test listing with filter criteria."""
        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Alice Smith", email="alice@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Jones", email="bob@example.com"),
        )

        # Filter by exact name
        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"name": "Alice Smith"}})
        response = json.loads(result[0].text)
        assert response["count"] == 1
        assert response["results"][0]["name"] == "Alice Smith"

    async def test_list_with_icontains_filter(self):
        """Test listing with icontains filter lookup."""
        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Charlie Brown", email="charlie@example.com"),
        )

        # Filter by name containing 'brown' (case-insensitive)
        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"name__icontains": "brown"}})
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        assert any("Brown" in r["name"] for r in response["results"])

    async def test_list_with_search(self):
        """Test listing with search term."""
        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Searchable Author", email="search@example.com"),
        )

        # Search for 'searchable'
        result = await MCPAdminMixin.handle_tool_call("list_author", {"search": "Searchable"})
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        assert any("Searchable" in r["name"] for r in response["results"])

    async def test_list_with_ordering(self):
        """Test listing with custom ordering."""
        # Clear existing and create test data with predictable names
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(name__startswith="Order").delete()
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Order Zebra", email="zebra@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Order Alpha", email="alpha@example.com"),
        )

        # Order by name ascending
        result = await MCPAdminMixin.handle_tool_call(
            "list_author",
            {"filters": {"name__icontains": "Order"}, "order_by": ["name"]},
        )
        response = json.loads(result[0].text)
        names = [r["name"] for r in response["results"]]
        assert names.index("Order Alpha") < names.index("Order Zebra")

        # Order by name descending
        result = await MCPAdminMixin.handle_tool_call(
            "list_author",
            {"filters": {"name__icontains": "Order"}, "order_by": ["-name"]},
        )
        response = json.loads(result[0].text)
        names = [r["name"] for r in response["results"]]
        assert names.index("Order Zebra") < names.index("Order Alpha")

    async def test_list_total_count(self):
        """Test that list returns total_count for pagination."""
        # Create multiple test authors
        for i in range(5):
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda i=i: Author.objects.create(name=f"Count Author {i}", email=f"count{i}@example.com"),
            )

        # Request with limit smaller than total
        result = await MCPAdminMixin.handle_tool_call(
            "list_author", {"filters": {"name__icontains": "Count Author"}, "limit": 2}
        )
        response = json.loads(result[0].text)
        assert response["count"] == 2  # Items returned
        assert response["total_count"] >= 5  # Total matching items

    async def test_list_with_invalid_filter_field(self):
        """Test that invalid filter fields are ignored."""
        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"invalid_field": "value"}})
        response = json.loads(result[0].text)
        # Should not error, just ignore the invalid filter
        assert "results" in response

    async def test_list_combined_filters_search_ordering(self):
        """Test combining filters, search, and ordering."""
        # Create test author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Combined Author", email="combined@example.com"),
        )

        # Create test articles
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(
                title="Published Python Guide",
                content="Python programming",
                author=author,
                is_published=True,
            ),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(
                title="Draft Python Tutorial",
                content="More Python",
                author=author,
                is_published=False,
            ),
        )

        # Filter by is_published, search for 'Python', order by title
        result = await MCPAdminMixin.handle_tool_call(
            "list_article",
            {
                "filters": {"is_published": True},
                "search": "Python",
                "order_by": ["title"],
            },
        )
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        # All results should be published
        assert all(r.get("is_published", True) for r in response["results"])
