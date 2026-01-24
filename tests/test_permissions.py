"""
Tests for MCP token permissions functionality
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from tests.factories import MCPTokenFactory, UserFactory
from tests.models import Article


@pytest.mark.django_db(transaction=True)
class TestTokenPermissions:
    """Test suite for token permission checking."""

    def test_token_with_no_permissions_has_no_access(self):
        """Test that tokens without groups/permissions have no access (principle of least privilege)."""
        token = MCPTokenFactory()

        # Should have no permissions when no restrictions are set
        assert not token.has_perm("tests.view_article")
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_does_not_inherit_user_permissions(self):
        """Test that token does NOT inherit user's permissions (user is for logging only)."""
        # Create user with specific permissions
        user = UserFactory()
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create token associated with user
        token = MCPTokenFactory(user=user)

        # Should NOT have view permission from user - permissions are independent
        assert not token.has_perm("tests.view_article")
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_with_direct_permissions(self):
        """Test that token can have direct permissions."""
        token = MCPTokenFactory()

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
        token = MCPTokenFactory()

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

    def test_token_combines_group_and_direct_permissions(self):
        """Test that token combines permissions from groups and direct permissions (not user)."""
        # Create user with view permission (should NOT be inherited)
        user = UserFactory()
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_article")
        group.permissions.add(change_perm)

        # Create token with user and add direct permission
        token = MCPTokenFactory(user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(add_perm)

        # Should have group and direct permissions only
        assert not token.has_perm("tests.view_article")  # NOT from user
        assert token.has_perm("tests.change_article")  # from group
        assert token.has_perm("tests.add_article")  # direct
        # Should not have delete permission
        assert not token.has_perm("tests.delete_article")

    def test_get_all_permissions(self):
        """Test get_all_permissions returns permissions from groups and direct only (not user)."""
        # Create user with view permission (should NOT be included)
        user = UserFactory()
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        user.user_permissions.add(view_perm)

        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(content_type=content_type, codename="change_article")
        group.permissions.add(change_perm)

        # Create token with user and add direct permission
        token = MCPTokenFactory(user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(add_perm)

        # Get all permissions
        all_perms = token.get_all_permissions()

        # Should contain group and direct permissions only
        assert "tests.view_article" not in all_perms  # NOT from user
        assert "tests.change_article" in all_perms  # from group
        assert "tests.add_article" in all_perms  # direct

    def test_has_perms_checks_multiple_permissions(self):
        """Test has_perms checks all given permissions."""
        token = MCPTokenFactory()

        # Add view and add permissions
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(content_type=content_type, codename="view_article")
        add_perm = Permission.objects.get(content_type=content_type, codename="add_article")
        token.permissions.add(view_perm, add_perm)

        # Should pass when all permissions are present
        assert token.has_perms(["tests.view_article", "tests.add_article"])
        # Should fail when any permission is missing
        assert not token.has_perms(["tests.view_article", "tests.change_article"])
