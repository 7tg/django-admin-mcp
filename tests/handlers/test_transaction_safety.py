"""
Tests for transaction safety in CRUD and bulk operations.

These tests verify that database operations are properly wrapped in
transaction.atomic() to ensure data integrity.
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_bulk,
    handle_create,
    handle_delete,
    handle_update,
)
from tests.models import Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_author(uid):
    """Helper to create test author."""
    return Author.objects.create(
        name=f"Test Author {uid}",
        email=f"author{uid}@example.com",
        bio=f"Bio for {uid}",
    )


@sync_to_async
def create_superuser(uid):
    """Helper to create superuser."""
    return User.objects.create_superuser(
        username=f"admin{uid}",
        email=f"admin{uid}@example.com",
        password="password",
    )


@sync_to_async
def get_log_count():
    """Get count of LogEntry records."""
    return LogEntry.objects.count()


@sync_to_async
def get_author_count():
    """Get count of Author records."""
    return Author.objects.count()


class TestCreateTransactionSafety:
    """Tests for transaction safety in create operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_rollback_on_log_failure(self):
        """Test that create operation rolls back if logging fails."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        initial_author_count = await get_author_count()
        initial_log_count = await get_log_count()

        # Patch _log_action to raise an exception
        with patch("django_admin_mcp.handlers.crud._log_action", side_effect=Exception("Log failure")):
            result = await handle_create(
                "author",
                {
                    "data": {
                        "name": f"Test Author {uid}",
                        "email": f"author{uid}@example.com",
                        "bio": "Test bio",
                    }
                },
                request,
            )

            # Verify error response
            data = json.loads(result[0].text)
            assert "error" in data

        # Verify author was not created (transaction rolled back)
        final_author_count = await get_author_count()
        assert final_author_count == initial_author_count

        # Verify log entry was not created
        final_log_count = await get_log_count()
        assert final_log_count == initial_log_count


class TestUpdateTransactionSafety:
    """Tests for transaction safety in update operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_rollback_on_log_failure(self):
        """Test that update operation rolls back if logging fails."""
        uid = unique_id()
        author = await create_author(uid)
        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        original_name = author.name
        initial_log_count = await get_log_count()

        # Patch _log_action to raise an exception
        with patch("django_admin_mcp.handlers.crud._log_action", side_effect=Exception("Log failure")):
            result = await handle_update(
                "author",
                {
                    "id": author.id,
                    "data": {
                        "name": "Updated Name",
                    },
                },
                request,
            )

            # Verify error response
            data = json.loads(result[0].text)
            assert "error" in data

        # Verify author was not updated (transaction rolled back)
        @sync_to_async
        def check_author_unchanged():
            author.refresh_from_db()
            return author.name == original_name

        assert await check_author_unchanged()

        # Verify log entry was not created
        final_log_count = await get_log_count()
        assert final_log_count == initial_log_count


class TestDeleteTransactionSafety:
    """Tests for transaction safety in delete operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_rollback_on_log_failure(self):
        """Test that delete operation rolls back if logging fails."""
        uid = unique_id()
        author = await create_author(uid)
        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        author_id = author.id
        initial_author_count = await get_author_count()
        initial_log_count = await get_log_count()

        # Patch _log_action to raise an exception
        with patch("django_admin_mcp.handlers.crud._log_action", side_effect=Exception("Log failure")):
            result = await handle_delete(
                "author",
                {"id": author_id},
                request,
            )

            # Verify error response
            data = json.loads(result[0].text)
            assert "error" in data

        # Verify author was not deleted (transaction rolled back)
        final_author_count = await get_author_count()
        assert final_author_count == initial_author_count

        # Verify the author still exists
        @sync_to_async
        def author_exists():
            return Author.objects.filter(id=author_id).exists()

        assert await author_exists()

        # Verify log entry was not created
        final_log_count = await get_log_count()
        assert final_log_count == initial_log_count


class TestBulkCreateTransactionSafety:
    """Tests for transaction safety in bulk create operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_bulk_create_individual_rollback_on_log_failure(self):
        """Test that each bulk create item is independently transactional."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        initial_author_count = await get_author_count()
        initial_log_count = await get_log_count()

        # Create a mock that fails on the second call
        call_count = 0

        def log_action_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Log failure on second item")

        # Patch _log_action to fail on second item
        with patch("django_admin_mcp.handlers.actions._log_action", side_effect=log_action_side_effect):
            result = await handle_bulk(
                "author",
                {
                    "operation": "create",
                    "items": [
                        {
                            "name": f"Author 1 {uid}",
                            "email": f"author1{uid}@example.com",
                            "bio": "Bio 1",
                        },
                        {
                            "name": f"Author 2 {uid}",
                            "email": f"author2{uid}@example.com",
                            "bio": "Bio 2",
                        },
                        {
                            "name": f"Author 3 {uid}",
                            "email": f"author3{uid}@example.com",
                            "bio": "Bio 3",
                        },
                    ],
                },
                request,
            )

            data = json.loads(result[0].text)

        # Verify that first item succeeded and third item succeeded
        assert data["success_count"] == 2
        # Verify that second item failed
        assert data["error_count"] == 1

        # Verify only successful items were created (2 authors: 1st and 3rd)
        final_author_count = await get_author_count()
        # First succeeded, second failed (rolled back), third succeeded
        assert final_author_count == initial_author_count + 2


class TestBulkUpdateTransactionSafety:
    """Tests for transaction safety in bulk update operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_bulk_update_individual_rollback_on_log_failure(self):
        """Test that each bulk update item is independently transactional."""
        uid = unique_id()

        # Create test authors
        author1 = await create_author(f"{uid}_1")
        author2 = await create_author(f"{uid}_2")
        author3 = await create_author(f"{uid}_3")

        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        initial_log_count = await get_log_count()

        # Create a mock that fails on the second call
        call_count = 0

        def log_action_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Log failure on second item")

        # Patch _log_action to fail on second item
        with patch("django_admin_mcp.handlers.actions._log_action", side_effect=log_action_side_effect):
            result = await handle_bulk(
                "author",
                {
                    "operation": "update",
                    "items": [
                        {"id": author1.id, "data": {"name": "Updated 1"}},
                        {"id": author2.id, "data": {"name": "Updated 2"}},
                        {"id": author3.id, "data": {"name": "Updated 3"}},
                    ],
                },
                request,
            )

            data = json.loads(result[0].text)

        # Verify that first and third items succeeded
        assert data["success_count"] == 2
        # Verify that second item failed
        assert data["error_count"] == 1

        # Verify only first and third were updated, second was rolled back
        @sync_to_async
        def check_updates():
            author1.refresh_from_db()
            author2.refresh_from_db()
            author3.refresh_from_db()
            return (
                author1.name == "Updated 1",
                author2.name != "Updated 2",  # Should be original name
                author3.name == "Updated 3",
            )

        updated1, not_updated2, updated3 = await check_updates()
        assert updated1
        assert not_updated2
        assert updated3


class TestBulkDeleteTransactionSafety:
    """Tests for transaction safety in bulk delete operations."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_bulk_delete_individual_rollback_on_log_failure(self):
        """Test that each bulk delete item is independently transactional."""
        uid = unique_id()

        # Create test authors
        author1 = await create_author(f"{uid}_1")
        author2 = await create_author(f"{uid}_2")
        author3 = await create_author(f"{uid}_3")

        user = await create_superuser(uid)
        request = create_mock_request(user=user)

        initial_author_count = await get_author_count()
        initial_log_count = await get_log_count()

        # Create a mock that fails on the second call
        call_count = 0

        def log_action_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Log failure on second item")

        # Patch _log_action to fail on second item
        with patch("django_admin_mcp.handlers.actions._log_action", side_effect=log_action_side_effect):
            result = await handle_bulk(
                "author",
                {
                    "operation": "delete",
                    "items": [author1.id, author2.id, author3.id],
                },
                request,
            )

            data = json.loads(result[0].text)

        # Verify that first and third items succeeded
        assert data["success_count"] == 2
        # Verify that second item failed
        assert data["error_count"] == 1

        # Verify only first and third were deleted, second was rolled back
        @sync_to_async
        def check_deletions():
            return (
                not Author.objects.filter(id=author1.id).exists(),
                Author.objects.filter(id=author2.id).exists(),  # Should still exist
                not Author.objects.filter(id=author3.id).exists(),
            )

        deleted1, not_deleted2, deleted3 = await check_deletions()
        assert deleted1
        assert not_deleted2
        assert deleted3
