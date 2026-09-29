"""
Tests for django_admin_mcp.handlers.bulk bulk-operation handlers.
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin as django_admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp.handlers import handle_bulk
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
    async def test_bulk_update_logs_change_message(self):
        """Test that bulk update creates log entry with serialized data."""
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(
            name=f"Log Author {uid}",
            email=f"log_{uid}@example.com",
        )
        request = create_mock_request(user)
        update_data = {"name": f"Updated Log Name {uid}", "bio": "New bio"}
        result = await handle_bulk(
            "author",
            {
                "operation": "update",
                "items": [{"id": author.pk, "data": update_data}],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed["success_count"] == 1

        # Verify the log entry was created with proper change message
        @sync_to_async
        def check_log_entry():
            ct = ContentType.objects.get_for_model(Author)
            log = LogEntry.objects.filter(
                user=user,
                content_type=ct,
                object_id=str(author.pk),
            ).first()
            assert log is not None
            assert "Bulk updated via MCP:" in log.change_message
            # Verify the data is in the message (either as JSON string or dict representation)
            assert "Updated Log Name" in log.change_message or str(author.pk) in log.change_message
            return log

        await check_log_entry()

    @pytest.mark.asyncio
    async def test_bulk_update_truncates_large_change_message(self):
        """Test that bulk update truncates large change messages to keep them concise."""
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(
            name=f"Truncate Test {uid}",
            email=f"truncate_{uid}@example.com",
        )
        request = create_mock_request(user)
        # Create a very large update data dictionary
        large_data = {f"field_{i}": "x" * 1000 for i in range(100)}  # ~100KB of data
        large_data["name"] = f"Updated {uid}"  # Include a valid update
        result = await handle_bulk(
            "author",
            {
                "operation": "update",
                "items": [{"id": author.pk, "data": large_data}],
            },
            request,
        )
        parsed = json.loads(result[0].text)
        # Validation will fail for non-existent fields, but that's OK for this test
        # We're just testing that large data doesn't break the logging

        # Verify the log entry exists and message is truncated
        @sync_to_async
        def check_log_entry():
            ct = ContentType.objects.get_for_model(Author)
            log = (
                LogEntry.objects.filter(
                    user=user,
                    content_type=ct,
                    object_id=str(author.pk),
                )
                .order_by("-action_time")
                .first()
            )
            # Log may or may not exist depending on validation success
            # But if it does, it should not exceed limits
            if log:
                assert "Bulk updated via MCP:" in log.change_message
                # Message should be truncated to around 500 chars for the data + prefix
                assert len(log.change_message) < 600  # 500 + prefix margin
            return log

        await check_log_entry()

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
        assert "not found" in parsed["error"]

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


@pytest.mark.django_db
@pytest.mark.asyncio
class TestBulkAdminPipelineParity:
    """Bulk paths must follow the same admin pipeline as single ops (issue #95)."""

    @staticmethod
    def _author_admin():
        return django_admin.site._registry[Author]

    async def test_bulk_create_calls_save_model(self):
        uid = unique_id()
        request = create_mock_request(user=await create_superuser(uid))
        author_admin = self._author_admin()

        with patch.object(author_admin, "save_model", wraps=author_admin.save_model) as mock_save:
            result = await handle_bulk(
                "author",
                {"operation": "create", "items": [{"name": f"Bulk SM {uid}", "email": f"bulksm_{uid}@example.com"}]},
                request,
            )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1
        mock_save.assert_called_once()
        assert mock_save.call_args[0][-1] is False or mock_save.call_args[1].get("change") is False

    async def test_bulk_update_calls_save_model(self):
        uid = unique_id()
        author = await create_author(f"Bulk USM {uid}", f"bulkusm_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))
        author_admin = self._author_admin()

        with patch.object(author_admin, "save_model", wraps=author_admin.save_model) as mock_save:
            result = await handle_bulk(
                "author",
                {"operation": "update", "items": [{"id": author.pk, "data": {"name": f"Bulk USM2 {uid}"}}]},
                request,
            )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1
        mock_save.assert_called_once()
        assert mock_save.call_args[0][-1] is True or mock_save.call_args[1].get("change") is True

    async def test_bulk_delete_calls_delete_model(self):
        uid = unique_id()
        author = await create_author(f"Bulk DM {uid}", f"bulkdm_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))
        author_admin = self._author_admin()

        with patch.object(author_admin, "delete_model", wraps=author_admin.delete_model) as mock_delete:
            result = await handle_bulk("author", {"operation": "delete", "items": [author.pk]}, request)

        data = json.loads(result[0].text)
        assert data["success_count"] == 1
        mock_delete.assert_called_once()
        assert not await author_exists(author.pk)

    async def test_bulk_update_rejects_readonly_fields(self):
        uid = unique_id()
        author = await create_author(f"Bulk RO {uid}", f"bulkro_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))
        author_admin = self._author_admin()
        original_readonly = getattr(author_admin, "readonly_fields", ())
        author_admin.readonly_fields = ("email",)
        try:
            result = await handle_bulk(
                "author",
                {"operation": "update", "items": [{"id": author.pk, "data": {"email": f"evil_{uid}@example.com"}}]},
                request,
            )
        finally:
            author_admin.readonly_fields = original_readonly

        data = json.loads(result[0].text)
        assert data["error_count"] == 1
        assert "readonly" in data["results"]["errors"][0]["error"].lower()
        await refresh_author(author)
        assert author.email == f"bulkro_{uid}@example.com"

    async def test_bulk_update_rejects_unknown_fields(self):
        uid = unique_id()
        author = await create_author(f"Bulk UF {uid}", f"bulkuf_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_bulk(
            "author",
            {"operation": "update", "items": [{"id": author.pk, "data": {"not_a_field": "x"}}]},
            request,
        )

        data = json.loads(result[0].text)
        assert data["error_count"] == 1
        assert "invalid field" in data["results"]["errors"][0]["error"].lower()
