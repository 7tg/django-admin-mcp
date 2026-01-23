"""
Tests for MCP token permissions functionality
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp.models import MCPToken
from tests.models import Article

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestTokenPermissions:
    """Test suite for token permission checking."""

    def test_token_with_no_permissions_has_full_access(self):
        """Test that tokens without user/groups/permissions have full access (backward compatibility)."""
        token = MCPToken.objects.create(name="Test Token")

        # Should have all permissions when no restrictions are set
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.add_article")
        assert token.has_perm("tests.change_article")
        assert token.has_perm("tests.delete_article")

    def test_token_with_user_inherits_permissions(self):
        """Test that token with user inherits user's permissions."""
        # Create user with specific permissions
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create token associated with user
        token = MCPToken.objects.create(name="User Token", user=user)

        # Should have view permission from user
        assert token.has_perm("tests.view_article")
        # Should not have other permissions
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_with_direct_permissions(self):
        """Test that token can have direct permissions."""
        token = MCPToken.objects.create(name="Test Token")

        # Add specific permissions
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(view_perm, add_perm)

        # Should have assigned permissions
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.add_article")
        # Should not have other permissions
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_with_group_permissions(self):
        """Test that token inherits permissions from groups."""
        token = MCPToken.objects.create(name="Test Token")

        # Create group with permissions
        group = Group.objects.create(name="Article Editors")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_article")
        group.permissions.add(view_perm, change_perm)

        # Add group to token
        token.groups.add(group)

        # Should have group permissions
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.change_article")
        # Should not have other permissions
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_combines_all_permission_sources(self):
        """Test that token combines permissions from user, groups, and direct permissions."""
        # Create user with view permission
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_article")
        group.permissions.add(change_perm)

        # Create token with user and add direct permission
        token = MCPToken.objects.create(name="Combined Token", user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(add_perm)

        # Should have all three permissions
        assert token.has_perm("tests.view_article")  # from user
        assert token.has_perm("tests.change_article")  # from group
        assert token.has_perm("tests.add_article")  # direct
        # Should not have delete permission
        assert not token.has_perm("tests.delete_article")

    def test_get_all_permissions(self):
        """Test get_all_permissions returns all permissions from all sources."""
        # Create user with view permission
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_article")
        group.permissions.add(change_perm)

        # Create token with user and add direct permission
        token = MCPToken.objects.create(name="Combined Token", user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(add_perm)

        # Get all permissions
        all_perms = token.get_all_permissions()

        # Should contain all three permissions
        assert "tests.view_article" in all_perms
        assert "tests.change_article" in all_perms
        assert "tests.add_article" in all_perms

    def test_has_perms_checks_multiple_permissions(self):
        """Test has_perms checks all given permissions."""
        token = MCPToken.objects.create(name="Test Token")

        # Add view and add permissions
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(view_perm, add_perm)

        # Should pass when all permissions are present
        assert token.has_perms(["tests.view_article", "tests.add_article"])
        # Should fail when any permission is missing
        assert not token.has_perms(["tests.view_article", "tests.change_article"])
