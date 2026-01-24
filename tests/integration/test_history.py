"""
Tests for LogEntry integration and history_<model_name> tool
"""

import asyncio
import json

import pytest
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth import get_user_model

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestLogEntryIntegration:
    """Test suite for LogEntry integration."""

    async def test_create_logs_entry(self):
        """Test that creating an object logs an entry."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logadmin", email="logadmin@example.com", password="logpass123"
            ),
        )

        # Create an author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Logged Author", "email": "logged@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert "error" not in response, f"Got error: {response}"
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=ADDITION,
            ).first(),
        )
        assert log_entry is not None
        assert "Created via MCP" in log_entry.change_message
        assert log_entry.object_repr == "Logged Author"

    async def test_update_logs_entry(self):
        """Test that updating an object logs an entry."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logupdater",
                email="logupdater@example.com",
                password="logpass123",
            ),
        )

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Log Author", email="updatelog@example.com"),
        )

        # Update the author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author.id, "data": {"name": "Updated Log Author"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=CHANGE,
                object_id=str(author.id),
            ).first(),
        )
        assert log_entry is not None
        assert "Changed via MCP" in log_entry.change_message

    async def test_delete_logs_entry(self):
        """Test that deleting an object logs an entry."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logdeleter",
                email="logdeleter@example.com",
                password="logpass123",
            ),
        )

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Log Author", email="deletelog@example.com"),
        )
        author_id = author.id

        # Delete the author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "delete_author",
            {"id": author_id},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=DELETION,
                object_id=str(author_id),
            ).first(),
        )
        assert log_entry is not None
        assert "Deleted via MCP" in log_entry.change_message

    async def test_no_log_without_user(self):
        """Test that no LogEntry is created without a user."""
        # Get initial count
        initial_count = await asyncio.get_event_loop().run_in_executor(None, LogEntry.objects.count)

        # Create an author without user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "No Log Author", "email": "nolog@example.com"}},
            user=None,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that no new LogEntry was created
        final_count = await asyncio.get_event_loop().run_in_executor(None, LogEntry.objects.count)
        assert final_count == initial_count


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHistoryTool:
    """Test suite for history_<model_name> tool."""

    async def test_history_returns_log_entries(self):
        """Test that history tool returns LogEntry records."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="histadmin",
                email="histadmin@example.com",
                password="histpass123",
            ),
        )

        # Create an author with the user (will log creation)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "History Author", "email": "history@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        author_id = response["id"]

        # Update the author (will log change)
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author_id, "data": {"name": "Updated History Author"}},
            user=superuser,
        )

        # Get history
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": author_id},
        )
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert response["object_id"] == author_id
        assert response["count"] >= 2  # At least create and update
        assert len(response["history"]) >= 2

        # Check that history entries have expected fields
        for entry in response["history"]:
            assert "action" in entry
            assert "action_time" in entry
            assert "user" in entry
            assert "change_message" in entry
            assert entry["user"] == "histadmin"

        # The most recent should be the change, then creation
        assert response["history"][0]["action"] == "changed"
        assert response["history"][1]["action"] == "created"

    async def test_history_not_found(self):
        """Test that history tool returns error for non-existent object."""
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": 99999},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_history_requires_id(self):
        """Test that history tool requires id parameter."""
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {},
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_history_with_limit(self):
        """Test that history tool respects limit parameter."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="limitadmin",
                email="limitadmin@example.com",
                password="limitpass123",
            ),
        )

        # Create an author
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Limit Author", "email": "limit@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        author_id = response["id"]

        # Do multiple updates
        for i in range(5):
            await MCPAdminMixin.handle_tool_call(
                "update_author",
                {"id": author_id, "data": {"name": f"Limit Author {i}"}},
                user=superuser,
            )

        # Get history with limit
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": author_id, "limit": 3},
        )
        response = json.loads(result[0].text)

        # Should have at most 3 entries
        assert response["count"] <= 3
