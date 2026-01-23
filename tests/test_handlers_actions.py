"""
Tests for django_admin_mcp.handlers.actions module.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User

from django_admin_mcp.handlers import (
    handle_action,
    handle_actions,
    handle_bulk,
)
from django_admin_mcp.handlers.base import create_mock_request
from tests.models import Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid):
    """Create a superuser asynchronously."""
    return User.objects.create_superuser(
        username=f"admin_{uid}",
        email=f"admin_{uid}@example.com",
        password="admin",
    )


@sync_to_async
def create_author(name, email, bio=""):
    """Create an author asynchronously."""
    return Author.objects.create(name=name, email=email, bio=bio)


@sync_to_async
def author_exists(pk):
    """Check if author exists asynchronously."""
    return Author.objects.filter(pk=pk).exists()


@sync_to_async
def author_exists_by_name(name):
    """Check if author exists by name asynchronously."""
    return Author.objects.filter(name=name).exists()


@sync_to_async
def refresh_author(author):
    """Refresh author from database asynchronously."""
    author.refresh_from_db()
    return author


@pytest.mark.django_db(transaction=True)
class TestHandleActions:
    """Tests for handle_actions function."""

    @pytest.mark.asyncio
    async def test_lists_actions_for_registered_model(self):
        """Test that handle_actions lists available actions."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_actions("author", {}, request)
        parsed = json.loads(result[0].text)
        assert "model" in parsed
        assert parsed["model"] == "author"
        assert "count" in parsed
        assert "actions" in parsed
        # delete_selected should be in the actions
        action_names = [a["name"] for a in parsed["actions"]]
        assert "delete_selected" in action_names

    @pytest.mark.asyncio
    async def test_returns_error_for_unregistered_model(self):
        """Test that handle_actions returns error for unknown model."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_actions("nonexistent", {}, request)
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "not registered" in parsed["error"]

    @pytest.mark.asyncio
    async def test_permission_denied_for_anonymous_user(self):
        """Test that handle_actions denies anonymous user."""
        request = create_mock_request(AnonymousUser())  # Explicit anonymous user for permission testing
        result = await handle_actions("author", {}, request)
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Permission denied" in parsed["error"]


@pytest.mark.django_db(transaction=True)
class TestHandleAction:
    """Tests for handle_action function."""

    @pytest.mark.asyncio
    async def test_executes_delete_selected_action(self):
        """Test that handle_action executes delete_selected action."""
        uid = unique_id()
        user = await create_superuser(uid)
        author1 = await create_author(
            name=f"Delete Author 1 {uid}",
            email=f"del1_{uid}@example.com",
        )
        author2 = await create_author(
            name=f"Delete Author 2 {uid}",
            email=f"del2_{uid}@example.com",
        )
        pk1, pk2 = author1.pk, author2.pk
        request = create_mock_request(user)
        result = await handle_action(
            "author",
            {"action": "delete_selected", "ids": [pk1, pk2]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["success"] is True
        assert parsed["action"] == "delete_selected"
        assert parsed["affected_count"] == 2
        # Verify authors are deleted
        assert not await author_exists(pk1)
        assert not await author_exists(pk2)

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_action_param(self):
        """Test that handle_action returns error when action param missing."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_action("author", {"ids": [1]}, request)
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "action parameter is required" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_ids_param(self):
        """Test that handle_action returns error when ids param missing."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_action(
            "author",
            {"action": "delete_selected"},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "ids parameter is required" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_action(self):
        """Test that handle_action returns error for unknown action."""
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(
            name=f"Test Author {uid}",
            email=f"author_unk_{uid}@example.com",
        )
        request = create_mock_request(user)
        result = await handle_action(
            "author",
            {"action": "unknown_action", "ids": [author.pk]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "not found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_no_objects_found(self):
        """Test that handle_action returns error when no objects match IDs."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_action(
            "author",
            {"action": "delete_selected", "ids": [999999]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "No objects found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_unregistered_model(self):
        """Test that handle_action returns error for unknown model."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_action(
            "nonexistent",
            {"action": "delete_selected", "ids": [1]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "not registered" in parsed["error"]

    @pytest.mark.asyncio
    async def test_permission_denied_for_anonymous_user(self):
        """Test that handle_action denies anonymous user."""
        request = create_mock_request(AnonymousUser())  # Explicit anonymous user for permission testing
        result = await handle_action(
            "author",
            {"action": "delete_selected", "ids": [1]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Permission denied" in parsed["error"]


@pytest.mark.django_db(transaction=True)
class TestHandleBulk:
    """Tests for handle_bulk function."""

    @pytest.mark.asyncio
    async def test_bulk_create_multiple_items(self):
        """Test bulk create with multiple items."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {
                "operation": "create",
                "items": [
                    {"name": f"Bulk Author A {uid}", "email": f"bulka_{uid}@example.com"},
                    {"name": f"Bulk Author B {uid}", "email": f"bulkb_{uid}@example.com"},
                ],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["operation"] == "create"
        assert parsed["success_count"] == 2
        assert parsed["error_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_create_with_error(self):
        """Test bulk create with partial failure."""
        uid = unique_id()
        user = await create_superuser(uid)
        # Create an author with this email first
        await create_author(
            name=f"Existing Author {uid}",
            email=f"existing_{uid}@example.com",
        )
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {
                "operation": "create",
                "items": [
                    {"name": f"New Author {uid}", "email": f"new_{uid}@example.com"},
                    # This should fail (duplicate email)
                    {"name": f"Dup Author {uid}", "email": f"existing_{uid}@example.com"},
                ],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["success_count"] == 1
        assert parsed["error_count"] == 1

    @pytest.mark.asyncio
    async def test_bulk_update_single_item(self):
        """Test bulk update with a single item."""
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(
            name=f"Update Author {uid}",
            email=f"update_{uid}@example.com",
        )
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {
                "operation": "update",
                "items": [{"id": author.pk, "data": {"name": f"Updated Name {uid}"}}],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["operation"] == "update"
        assert parsed["success_count"] == 1
        assert parsed["error_count"] == 0
        # Verify update
        author = await refresh_author(author)
        assert author.name == f"Updated Name {uid}"

    @pytest.mark.asyncio
    async def test_bulk_update_missing_id(self):
        """Test bulk update with missing id returns error."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {
                "operation": "update",
                "items": [{"data": {"name": "No ID"}}],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["error_count"] == 1
        assert "id is required" in parsed["results"]["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_bulk_update_not_found(self):
        """Test bulk update with non-existent id."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {
                "operation": "update",
                "items": [{"id": 999999, "data": {"name": "Not Found"}}],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["error_count"] == 1
        assert "not found" in parsed["results"]["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_bulk_delete_multiple_items(self):
        """Test bulk delete with multiple items."""
        uid = unique_id()
        user = await create_superuser(uid)
        author1 = await create_author(
            name=f"Delete A {uid}",
            email=f"dela_{uid}@example.com",
        )
        author2 = await create_author(
            name=f"Delete B {uid}",
            email=f"delb_{uid}@example.com",
        )
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {"operation": "delete", "items": [author1.pk, author2.pk]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["success_count"] == 2
        assert parsed["error_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_not_found(self):
        """Test bulk delete with non-existent id."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {"operation": "delete", "items": [999999]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["error_count"] == 1
        assert "not found" in parsed["results"]["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_operation(self):
        """Test that handle_bulk returns error when operation missing."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk("author", {"items": []}, request)
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "operation parameter is required" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_operation(self):
        """Test that handle_bulk returns error for invalid operation."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "author",
            {"operation": "invalid", "items": []},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "must be 'create', 'update', or 'delete'" in parsed["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_unregistered_model(self):
        """Test that handle_bulk returns error for unknown model."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        result = await handle_bulk(
            "nonexistent",
            {"operation": "create", "items": []},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "not registered" in parsed["error"]

    @pytest.mark.asyncio
    async def test_permission_denied_for_anonymous_user(self):
        """Test that handle_bulk denies anonymous user."""
        request = create_mock_request(AnonymousUser())
        result = await handle_bulk(
            "author",
            {"operation": "create", "items": []},
            request,
        )
        parsed = json.loads(result[0].text)
        assert "error" in parsed
        assert "Permission denied" in parsed["error"]
