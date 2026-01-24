"""
Tests for permission checking functionality via MCP tools
"""

import asyncio
import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestPermissionChecks:
    """Test suite for permission checking functionality."""

    async def test_superuser_can_do_everything(self):
        """Test that superuser has all permissions."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="superadmin",
                email="superadmin@example.com",
                password="superpass123",
            ),
        )

        # Create an author first
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Perm Test Author", email="permtest@example.com"),
        )

        # Test list (view permission)
        result = await MCPAdminMixin.handle_tool_call("list_author", {}, user=superuser)
        response = json.loads(result[0].text)
        assert "results" in response

        # Test get (view permission)
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id}, user=superuser)
        response = json.loads(result[0].text)
        assert response["name"] == "Perm Test Author"

        # Test create (add permission)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "New Author", "email": "newauthor@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Test update (change permission)
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author.id, "data": {"name": "Updated Name"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_no_user_allows_all_operations(self):
        """Test that operations work without a user (backwards compatibility)."""
        # Create an author
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="No User Author", email="nouser@example.com"),
        )

        # Test list without user
        result = await MCPAdminMixin.handle_tool_call("list_author", {}, user=None)
        response = json.loads(result[0].text)
        assert "results" in response

        # Test create without user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Anonymous Create", "email": "anoncreate@example.com"}},
            user=None,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_regular_user_without_permissions(self):
        """Test that regular user without permissions gets denied."""
        User = get_user_model()

        # Create a regular user without any permissions
        regular_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(
                username="regularuser",
                email="regular@example.com",
                password="regularpass123",
            ),
        )

        # Test create without permission (should be denied)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Should Fail", "email": "shouldfail@example.com"}},
            user=regular_user,
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert response.get("code") == "permission_denied"

    async def test_staff_user_with_add_permission(self):
        """Test that staff user with add permission can create."""
        User = get_user_model()

        # Create a staff user
        staff_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(
                username="staffuser",
                email="staff@example.com",
                password="staffpass123",
                is_staff=True,
            ),
        )

        # Add the add_author permission
        def add_permission():
            content_type = ContentType.objects.get_for_model(Author)
            permission = Permission.objects.get(codename="add_author", content_type=content_type)
            staff_user.user_permissions.add(permission)
            staff_user.save()
            # Clear permission cache
            staff_user._perm_cache = {}
            staff_user._user_perm_cache = {}

        await asyncio.get_event_loop().run_in_executor(None, add_permission)

        # Refetch user to get fresh permissions
        staff_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.get(pk=staff_user.pk),
        )

        # Test create with permission (should succeed)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Staff Create", "email": "staffcreate@example.com"}},
            user=staff_user,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_bulk_permission_check(self):
        """Test that bulk operations check permissions."""
        User = get_user_model()

        # Create a regular user without permissions
        regular_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(username="bulkuser", email="bulk@example.com", password="bulkpass123"),
        )

        # Test bulk create without permission (should be denied)
        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {
                "operation": "create",
                "items": [{"name": "Bulk Fail", "email": "bulkfail@example.com"}],
            },
            user=regular_user,
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert response.get("code") == "permission_denied"

    async def test_related_permission_check(self):
        """Test that related tool checks view permissions."""
        User = get_user_model()

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Related Perm Author", email="relatedperm@example.com"),
        )

        # Create a regular user without permissions
        regular_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(
                username="relateduser",
                email="related@example.com",
                password="relatedpass123",
            ),
        )

        # Test related without permission (should be denied)
        result = await MCPAdminMixin.handle_tool_call(
            "related_author",
            {"id": author.id, "relation": "articles"},
            user=regular_user,
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert response.get("code") == "permission_denied"

    async def test_related_superuser_allowed(self):
        """Test that superuser can access related objects."""
        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="relatedsuper",
                email="relatedsuper@example.com",
                password="superpass123",
            ),
        )

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Super Related Author", email="superrelated@example.com"),
        )

        # Test related with superuser (should succeed)
        result = await MCPAdminMixin.handle_tool_call(
            "related_author",
            {"id": author.id, "relation": "articles"},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert "error" not in response
        assert response["relation"] == "articles"
        assert response["type"] == "many"
