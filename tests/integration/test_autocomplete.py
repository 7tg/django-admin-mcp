"""
Tests for autocomplete tool
"""

import asyncio
import json
import uuid

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestAutocomplete:
    """Test suite for autocomplete tool."""

    async def test_autocomplete_returns_results(self):
        """Test that autocomplete tool returns results."""
        unique_suffix = uuid.uuid4().hex[:8]

        # Create some authors with unique emails
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="John Doe", email=f"john_{unique_suffix}@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Jane Doe", email=f"jane_{unique_suffix}@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Smith", email=f"bob_{unique_suffix}@example.com"),
        )

        # Test autocomplete without term
        result = await MCPAdminMixin.handle_tool_call(
            "autocomplete_author",
            {},
        )
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert response["count"] >= 3
        assert "results" in response
        for item in response["results"]:
            assert "id" in item
            assert "text" in item

    async def test_autocomplete_with_search_term(self):
        """Test that autocomplete tool filters by search term."""
        # Create some authors
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Alice Autocomplete", email="alice@auto.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Autocomplete", email="bob@auto.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Charlie Unique", email="charlie@unique.com"),
        )

        # Search for "Autocomplete"
        result = await MCPAdminMixin.handle_tool_call(
            "autocomplete_author",
            {"term": "Autocomplete"},
        )
        response = json.loads(result[0].text)

        assert response["term"] == "Autocomplete"
        assert response["count"] == 2  # Only Alice and Bob

        # Verify the results contain the expected names
        names = [r["text"] for r in response["results"]]
        assert all("Autocomplete" in name for name in names)
