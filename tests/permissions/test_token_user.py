"""
Tests for the TokenUser permission proxy placed on MCP requests.

TokenUser answers Django's permission API from the token's own
permissions/groups while delegating identity attributes to the linked user.
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp.models import TokenUser
from tests.factories import MCPTokenFactory, UserFactory
from tests.models import Article


def article_perm(codename):
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Article),
        codename=codename,
    )


@pytest.mark.django_db(transaction=True)
class TestTokenUser:
    """Test suite for the TokenUser permission proxy."""

    def test_has_perm_uses_token_permissions_not_user(self):
        """Permissions come from the token; the linked user's own permissions are not inherited."""
        user = UserFactory()
        user.user_permissions.add(article_perm("delete_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.view_article")
        assert not proxy.has_perm("tests.delete_article")  # user-only permission

    def test_superuser_bound_token_gets_no_implicit_access(self):
        """A token bound to a superuser has no permissions unless granted on the token."""
        superuser = UserFactory(is_superuser=True, is_staff=True)
        token = MCPTokenFactory(user=superuser)

        proxy = TokenUser(token)

        assert not proxy.has_perm("tests.view_article")
        assert proxy.is_superuser is False

    def test_group_permissions_grant_access(self):
        """Permissions from the token's groups are honored."""
        group = Group.objects.create(name="Proxy Editors")
        group.permissions.add(article_perm("change_article"))
        token = MCPTokenFactory()
        token.groups.add(group)

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.change_article")
        assert not proxy.has_perm("tests.add_article")

    def test_has_perms_requires_all(self):
        """has_perms is True only when every permission is granted."""
        token = MCPTokenFactory()
        token.permissions.add(article_perm("view_article"), article_perm("add_article"))

        proxy = TokenUser(token)

        assert proxy.has_perms(["tests.view_article", "tests.add_article"])
        assert not proxy.has_perms(["tests.view_article", "tests.delete_article"])

    def test_has_module_perms_reflects_token_permissions(self):
        """Module permission is granted only for apps where the token holds a permission."""
        token = MCPTokenFactory()
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert proxy.has_module_perms("tests")
        assert not proxy.has_module_perms("auth")

    def test_get_all_permissions_returns_token_permissions(self):
        """get_all_permissions reports token permissions, not the linked user's."""
        user = UserFactory()
        user.user_permissions.add(article_perm("delete_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)
        perms = proxy.get_all_permissions()

        assert "tests.view_article" in perms
        assert "tests.delete_article" not in perms

    def test_delegates_identity_attributes_to_linked_user(self):
        """Identity attributes (pk, username, is_authenticated) come from the linked user."""
        user = UserFactory()
        token = MCPTokenFactory(user=user)

        proxy = TokenUser(token)

        assert proxy.pk == user.pk
        assert proxy.username == user.username
        assert proxy.is_authenticated
        assert str(proxy) == str(user)
