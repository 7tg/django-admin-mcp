"""
Tests for basic CRUD operations via MCP tools
"""

import asyncio

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestCRUDOperations:
    """Test suite for CRUD operations."""

    async def test_create_author(self):
        """Test creating an author via MCP."""
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {
                "data": {
                    "name": "Test Author",
                    "email": "test@example.com",
                    "bio": "Test bio",
                }
            },
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True
        assert "id" in response
        assert response["object"]["name"] == "Test Author"

    async def test_list_authors(self):
        """Test listing authors via MCP."""
        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 1", email="author1@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("list_author", {"limit": 10})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "count" in response
        assert "results" in response
        assert response["count"] >= 1

    async def test_get_author(self):
        """Test getting a specific author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 2", email="author2@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["name"] == "Author 2"
        assert response["email"] == "author2@example.com"

    async def test_update_author(self):
        """Test updating an author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 3", email="author3@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "update_author", {"id": author.id, "data": {"name": "Updated Author"}}
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True
        assert response["object"]["name"] == "Updated Author"

    async def test_delete_author(self):
        """Test deleting an author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 4", email="author4@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("delete_author", {"id": author.id})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_get_nonexistent_author(self):
        """Test getting a nonexistent author returns error."""
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": 99999})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "error" in response

    async def test_update_invalid_field(self):
        """Test updating with invalid field returns error."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 5", email="author5@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "update_author", {"id": author.id, "data": {"invalid_field": "value"}}
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "error" in response
        assert "Invalid field" in response["error"]

    async def test_create_article_with_author(self):
        """Test creating an article with author relationship."""
        # Create author first
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Article Author", email="articleauthor@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "create_article",
            {
                "data": {
                    "title": "Test Article",
                    "content": "Test content",
                    "author_id": author.id,  # Use author_id for foreign key
                    "is_published": True,
                }
            },
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        # Check if error or success
        if "error" in response:
            # If there's an error, the test should explain what went wrong
            pytest.fail(f"Failed to create article: {response['error']}")
        assert response["success"] is True
        assert response["object"]["title"] == "Test Article"

    async def test_find_models(self):
        """Test finding models via find_models tool."""
        # Call find_models without query
        result = await MCPAdminMixin.handle_tool_call("find_models", {})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "count" in response
        assert "models" in response
        assert response["count"] >= 2  # Should find at least author and article

        # Verify that models are in the results
        model_names = [m["model_name"] for m in response["models"]]
        assert "author" in model_names
        assert "article" in model_names

        # Test with query filter
        result = await MCPAdminMixin.handle_tool_call("find_models", {"query": "author"})

        response = json.loads(result[0].text)
        assert "count" in response
        assert response["count"] >= 1
        model_names = [m["model_name"] for m in response["models"]]
        assert "author" in model_names
