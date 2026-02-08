"""
Tests for actions and bulk operations via MCP tools
"""

import asyncio
import json

import pytest
from django.contrib.auth.models import User

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestActionsAndBulk:
    """Test suite for actions and bulk operations."""

    async def test_list_actions(self):
        """Test listing available actions for a model with authenticated user."""
        user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser("action_admin", "admin@test.com", "pass"),
        )
        result = await MCPAdminMixin.handle_tool_call("actions_author", {}, user=user)
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert "actions" in response
        # delete_selected should be available for authenticated users
        action_names = [a["name"] for a in response["actions"]]
        assert "delete_selected" in action_names

    async def test_action_delete_selected(self):
        """Test executing delete_selected action."""
        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Me 1", email="delete1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Me 2", email="delete2@example.com"),
        )

        # Execute delete_selected action
        result = await MCPAdminMixin.handle_tool_call(
            "action_author",
            {"action": "delete_selected", "ids": [author1.id, author2.id]},
        )
        response = json.loads(result[0].text)

        assert response["success"] is True
        assert response["action"] == "delete_selected"
        assert response["affected_count"] == 2

        # Verify deletion
        count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(pk__in=[author1.id, author2.id]).count()
        )
        assert count == 0

    async def test_action_missing_params(self):
        """Test action with missing parameters."""
        # Missing action name
        result = await MCPAdminMixin.handle_tool_call("action_author", {"ids": [1, 2]})
        response = json.loads(result[0].text)
        assert "error" in response

        # Missing ids
        result = await MCPAdminMixin.handle_tool_call("action_author", {"action": "delete_selected"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_bulk_create(self):
        """Test bulk create operation."""
        items = [
            {"name": "Bulk Author 1", "email": "bulk1@example.com"},
            {"name": "Bulk Author 2", "email": "bulk2@example.com"},
            {"name": "Bulk Author 3", "email": "bulk3@example.com"},
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "create", "items": items})
        response = json.loads(result[0].text)

        assert response["operation"] == "create"
        assert response["success_count"] == 3
        assert response["error_count"] == 0

    async def test_bulk_update(self):
        """Test bulk update operation."""
        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Me 1", email="update1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Me 2", email="update2@example.com"),
        )

        items = [
            {"id": author1.id, "data": {"name": "Updated 1"}},
            {"id": author2.id, "data": {"name": "Updated 2"}},
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "update", "items": items})
        response = json.loads(result[0].text)

        assert response["operation"] == "update"
        assert response["success_count"] == 2

        # Verify updates
        updated1 = await asyncio.get_event_loop().run_in_executor(None, lambda: Author.objects.get(pk=author1.id))
        assert updated1.name == "Updated 1"

    async def test_bulk_delete(self):
        """Test bulk delete operation."""
        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bulk Delete 1", email="bulkdel1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bulk Delete 2", email="bulkdel2@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author", {"operation": "delete", "items": [author1.id, author2.id]}
        )
        response = json.loads(result[0].text)

        assert response["operation"] == "delete"
        assert response["success_count"] == 2

        # Verify deletion
        count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(pk__in=[author1.id, author2.id]).count()
        )
        assert count == 0

    async def test_bulk_with_errors(self):
        """Test bulk operation with some errors."""
        # First create an author with a specific email
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Existing", email="duplicate@example.com"),
        )

        items = [
            {"name": "Valid Author", "email": "bulkerror@example.com"},
            {
                "name": "Duplicate Email",
                "email": "duplicate@example.com",
            },  # Will fail - duplicate email
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "create", "items": items})
        response = json.loads(result[0].text)

        assert response["success_count"] == 1
        assert response["error_count"] == 1
        assert len(response["results"]["errors"]) == 1
