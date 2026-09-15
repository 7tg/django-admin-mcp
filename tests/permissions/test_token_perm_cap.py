"""
Tests for issue #109: MCPToken's public permission API (has_perm, has_perms,
has_module_perms) must answer from the effective permissions — token grants
capped by the linked user — matching the TokenUser proxy.
"""

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from tests.factories import MCPTokenFactory, UserFactory
from tests.models import Article


def article_perm(codename):
    content_type = ContentType.objects.get_for_model(Article)
    return Permission.objects.get(content_type=content_type, codename=codename)


@pytest.mark.django_db(transaction=True)
class TestTokenPermissionCap:
    """MCPToken.has_perm and friends must never exceed the user's permissions."""

    def test_has_perm_denied_when_user_lacks_the_permission(self):
        user = UserFactory()  # zero permissions
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        assert not token.has_perm("tests.view_article")

    def test_has_perm_granted_when_user_also_holds_it(self):
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        assert token.has_perm("tests.view_article")

    def test_has_perm_accepts_permission_object(self):
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        assert token.has_perm(article_perm("view_article"))
        assert not token.has_perm(article_perm("delete_article"))

    def test_has_perms_capped_by_user(self):
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"), article_perm("add_article"))

        assert token.has_perms(["tests.view_article"])
        # add_article is granted on the token but the user lacks it
        assert not token.has_perms(["tests.view_article", "tests.add_article"])

    def test_has_module_perms_denied_when_cap_removes_all_app_perms(self):
        user = UserFactory()  # zero permissions
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        assert not token.has_module_perms("tests")

    def test_has_module_perms_granted_within_the_cap(self):
        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"))

        assert token.has_module_perms("tests")
        assert not token.has_module_perms("auth")

    def test_superuser_bound_token_uses_its_grants(self):
        superuser = UserFactory(is_superuser=True)
        token = MCPTokenFactory(user=superuser)
        token.permissions.add(article_perm("view_article"))

        assert token.has_perm("tests.view_article")
        assert not token.has_perm("tests.delete_article")
        assert token.has_module_perms("tests")

    def test_matches_token_user_proxy(self):
        """has_perm must agree with the TokenUser proxy used for MCP requests."""
        from django_admin_mcp.models import TokenUser  # noqa: PLC0415

        user = UserFactory()
        user.user_permissions.add(article_perm("view_article"))
        token = MCPTokenFactory(user=user)
        token.permissions.add(article_perm("view_article"), article_perm("add_article"))
        proxy = TokenUser(token)

        for perm in ("tests.view_article", "tests.add_article", "tests.delete_article"):
            assert token.has_perm(perm) == proxy.has_perm(perm), perm
