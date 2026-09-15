"""
Tests for the TokenUser permission proxy placed on MCP requests.

TokenUser answers Django's permission API from the token's effective
permissions — the token's own permissions/groups capped by the linked
user's permissions — while delegating identity attributes to the user.
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

    def test_has_perm_requires_grant_on_the_token(self):
        """A permission the user holds but the token was not granted is denied."""
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"), article_perm("delete_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.view_article")
        assert not proxy.has_perm("tests.delete_article")  # user-only permission

    def test_token_cannot_exceed_linked_user_permissions(self):
        """A permission granted on the token but missing on the user is denied."""
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"), article_perm("delete_article"))

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.view_article")
        assert not proxy.has_perm("tests.delete_article")  # exceeds the user's access

    def test_superuser_bound_token_gets_no_implicit_access(self):
        """A token with no grants is denied even when bound to a superuser."""
        superuser = UserFactory(is_superuser=True, is_staff=True)
        token = MCPTokenFactory(user=superuser)

        proxy = TokenUser(token)

        assert not proxy.has_perm("tests.view_article")
        assert proxy.is_superuser is False

    def test_superuser_bound_token_uses_grants_as_is(self):
        """A superuser satisfies the cap, so the token's grants apply unchanged."""
        superuser = UserFactory(is_superuser=True)
        token = MCPTokenFactory(user=superuser)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.view_article")
        assert not proxy.has_perm("tests.add_article")

    def test_group_permissions_grant_access(self):
        """Permissions from the token's groups are honored (when the user also holds them)."""
        group = Group.objects.create(name="Proxy Editors")
        group.permissions.add(article_perm("change_article"))
        user = UserFactory()
        user.user_permissions.add(article_perm("change_article"))
        token = MCPTokenFactory(user=user)
        token.groups.add(group)

        proxy = TokenUser(token)

        assert proxy.has_perm("tests.change_article")
        assert not proxy.has_perm("tests.add_article")

    def test_has_perms_requires_all(self):
        """has_perms is True only when every permission is effective."""
        superuser = UserFactory(is_superuser=True)
        token = MCPTokenFactory(user=superuser)
        token.permissions.add(article_perm("view_article"), article_perm("add_article"))

        proxy = TokenUser(token)

        assert proxy.has_perms(["tests.view_article", "tests.add_article"])
        assert not proxy.has_perms(["tests.view_article", "tests.delete_article"])

    def test_has_module_perms_reflects_effective_permissions(self):
        """Module permission requires an effective permission in the app."""
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert proxy.has_module_perms("tests")
        assert not proxy.has_module_perms("auth")

    def test_has_module_perms_denied_when_cap_removes_all_app_perms(self):
        """A token grant the user lacks does not produce module access."""
        user = UserFactory()  # no permissions at all
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert not proxy.has_module_perms("tests")

    def test_get_all_permissions_returns_effective_permissions(self):
        """get_all_permissions reports token grants capped by the user's permissions."""
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"), article_perm("delete_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"), article_perm("add_article"))

        proxy = TokenUser(token)
        perms = proxy.get_all_permissions()

        assert "tests.view_article" in perms
        assert "tests.add_article" not in perms  # user lacks it
        assert "tests.delete_article" not in perms  # token lacks it

    def test_inactive_linked_user_disables_access(self):
        """Deactivating the linked user removes all of the token's effective permissions."""
        user = UserFactory(is_active=False)
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        proxy = TokenUser(token)

        assert not proxy.has_perm("tests.view_article")
        assert proxy.get_all_permissions() == set()

    def test_delegates_identity_attributes_to_linked_user(self):
        """Identity attributes (pk, username, is_authenticated) come from the linked user."""
        user = UserFactory()
        token = MCPTokenFactory(user=user)

        proxy = TokenUser(token)

        assert proxy.pk == user.pk
        assert proxy.username == user.username
        assert proxy.is_authenticated
        assert str(proxy) == str(user)
