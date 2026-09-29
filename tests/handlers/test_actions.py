"""
Tests for django_admin_mcp.handlers.actions module.
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

from django_admin_mcp.handlers import (
    handle_action,
    handle_actions,
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
        assert "not found" in parsed["error"]

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
    async def test_listed_string_action_can_be_executed(self):
        """Test that string-referenced method actions can be listed and executed.

        Reproduces https://github.com/7tg/django-admin-mcp/issues/69
        Django supports actions as strings referencing methods on the ModelAdmin.
        These are listed by handle_actions but fail to execute via handle_action.
        """
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(
            name=f"Action Test {uid}",
            email=f"action_{uid}@example.com",
        )
        request = create_mock_request(user)

        @sync_to_async
        def add_string_action():
            author_admin = django_admin.site._registry[Author]
            admin_class = author_admin.__class__
            original_actions = getattr(author_admin, "actions", [])

            # Add a method to the admin class and reference it by string
            # This is the standard Django pattern for admin actions
            def set_status_disabled(modeladmin, request, queryset):
                return f"Disabled {queryset.count()} items"

            set_status_disabled.short_description = "Set status disabled"
            admin_class.set_status_disabled = set_status_disabled
            author_admin.actions = list(original_actions or []) + ["set_status_disabled"]
            return author_admin, admin_class, original_actions

        @sync_to_async
        def restore(admin_instance, admin_class, original):
            admin_instance.actions = original
            if hasattr(admin_class, "set_status_disabled"):
                delattr(admin_class, "set_status_disabled")

        admin_instance, admin_class, original = await add_string_action()
        try:
            # List actions — set_status_disabled should appear
            list_result = await handle_actions("author", {}, request)
            listed = json.loads(list_result[0].text)
            action_names = [a["name"] for a in listed["actions"]]
            assert "set_status_disabled" in action_names, f"set_status_disabled not in listed actions: {action_names}"

            # Execute that same action — currently fails with "Action not found"
            exec_result = await handle_action(
                "author",
                {"action": "set_status_disabled", "ids": [author.pk]},
                request,
            )
            parsed = json.loads(exec_result[0].text)
            assert "error" not in parsed, f"Action listed but not executable: {parsed}"
            assert parsed["success"] is True
            assert parsed["action"] == "set_status_disabled"
        finally:
            await restore(admin_instance, admin_class, original)

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
        assert "not found" in parsed["error"]

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

    @pytest.mark.asyncio
    async def test_delete_selected_requires_delete_permission(self):
        """Users with change but not delete must not run delete_selected."""
        from django.contrib.auth.models import Permission  # noqa: PLC0415

        uid = unique_id()
        author = await create_author(
            name=f"NoDelete Author {uid}",
            email=f"nodelete_{uid}@example.com",
        )

        @sync_to_async
        def create_change_only_user():
            user = User.objects.create_user(
                username=f"change_only_{uid}",
                email=f"change_only_{uid}@example.com",
                password="testpass",
                is_staff=True,
            )
            change_perm = Permission.objects.get(codename="change_author")
            user.user_permissions.add(change_perm)
            return user

        user = await create_change_only_user()
        request = create_mock_request(user)
        result = await handle_action(
            "author",
            {"action": "delete_selected", "ids": [author.pk]},
            request,
        )
        parsed = json.loads(result[0].text)
        assert parsed.get("code") == "permission_denied"
        assert "delete" in parsed["error"].lower()
        assert await author_exists(author.pk)


@pytest.mark.django_db
@pytest.mark.asyncio
class TestAdminPipelineParity:
    """Action paths must follow the same admin pipeline as single ops (issue #95)."""

    @staticmethod
    def _author_admin():
        return django_admin.site._registry[Author]

    async def test_delete_selected_writes_log_entries(self):
        uid = unique_id()
        author = await create_author(f"Del Log {uid}", f"dellog_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_action("author", {"action": "delete_selected", "ids": [author.pk]}, request)
        data = json.loads(result[0].text)

        assert data.get("success") is True

        @sync_to_async
        def deletion_logged():
            content_type = ContentType.objects.get_for_model(Author)
            return LogEntry.objects.filter(content_type=content_type, object_id=str(author.pk), action_flag=3).exists()

        assert await deletion_logged()

    async def test_delete_selected_uses_delete_queryset(self):
        uid = unique_id()
        author = await create_author(f"Del Hook {uid}", f"delhook_{uid}@example.com")
        request = create_mock_request(user=await create_superuser(uid))
        author_admin = self._author_admin()

        with patch.object(author_admin, "delete_queryset", wraps=author_admin.delete_queryset) as mock_delete_queryset:
            result = await handle_action("author", {"action": "delete_selected", "ids": [author.pk]}, request)

        data = json.loads(result[0].text)
        assert data.get("success") is True
        mock_delete_queryset.assert_called_once()
        assert not await author_exists(author.pk)
