"""
Security tests for access paths that sidestepped the admin's own checks:
hidden-field oracles, related models without an MCP admin, object-level
permissions, cascade deletes, inline view permission, and token management.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory

from django_admin_mcp.admin import MCPTokenAdmin
from django_admin_mcp.handlers import (
    create_mock_request,
    handle_action,
    handle_autocomplete,
    handle_bulk,
    handle_delete,
    handle_get,
    handle_history,
    handle_list,
    handle_related,
    handle_update,
)
from django_admin_mcp.handlers.actions import _prepare_action_request
from django_admin_mcp.handlers.base import _serialize_data_for_log
from django_admin_mcp.models import MCPToken
from tests.factories import MCPTokenFactory, UserFactory
from tests.models import Article, Author, Gadget


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_user_with_perms(*codenames, **kwargs):
    uid = unique_id()
    user = User.objects.create_user(username=f"sec_{uid}", email=f"sec_{uid}@example.com", password="x", **kwargs)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


@sync_to_async
def create_author_with_article():
    uid = unique_id()
    author = Author.objects.create(name=f"Sec Author {uid}", email=f"sec_{uid}@example.com")
    article = Article.objects.create(title=f"Sec Article {uid}", content="c", author=author)
    return author, article


def payload(result):
    return json.loads(result[0].text)


@pytest.fixture
def hidden_api_key(monkeypatch):
    """Hide Gadget.api_key from MCP."""
    monkeypatch.setattr(admin.site._registry[Gadget], "mcp_exclude_fields", ["api_key"], raising=False)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestHiddenFieldOracles:
    """Hidden fields must not be recoverable through filters, ordering, search or history."""

    async def test_filter_on_hidden_field_is_rejected(self, hidden_api_key):
        await sync_to_async(Gadget.objects.create)(title="g", api_key="s3cr3t")
        request = create_mock_request(await create_user_with_perms("view_gadget"))
        data = payload(await handle_list("gadget", {"filters": {"api_key__contains": "s3"}}, request))
        assert "unknown field 'api_key'" in data["error"]

    async def test_order_by_hidden_field_is_rejected(self, hidden_api_key):
        request = create_mock_request(await create_user_with_perms("view_gadget"))
        data = payload(await handle_list("gadget", {"order_by": ["-api_key"]}, request))
        assert "api_key" in data["error"]

    async def test_primary_key_stays_queryable_under_include_list(self, monkeypatch):
        monkeypatch.setattr(admin.site._registry[Gadget], "mcp_fields", ["title"], raising=False)
        gadget = await sync_to_async(Gadget.objects.create)(title="g")
        request = create_mock_request(await create_user_with_perms("view_gadget"))
        data = payload(await handle_list("gadget", {"filters": {"id": gadget.pk}, "order_by": ["-id"]}, request))
        assert data["total_count"] == 1

    async def test_reverse_relation_filter_is_rejected(self):
        request = create_mock_request(await create_user_with_perms("view_author"))
        data = payload(await handle_list("author", {"filters": {"articles__isnull": False}}, request))
        assert "unknown field 'articles'" in data["error"]

    async def test_autocomplete_fallback_skips_hidden_fields(self, hidden_api_key):
        await sync_to_async(Gadget.objects.create)(title="plain", api_key="s3cr3t")
        request = create_mock_request(await create_user_with_perms("view_gadget"))
        data = payload(await handle_autocomplete("gadget", {"term": "s3cr3t"}, request))
        assert data["count"] == 0

    async def test_hidden_forward_relation_is_not_served(self, monkeypatch):
        monkeypatch.setattr(admin.site._registry[Gadget], "mcp_exclude_fields", ["owner"], raising=False)
        author, _ = await create_author_with_article()
        gadget = await sync_to_async(Gadget.objects.create)(title="g", owner=author)
        request = create_mock_request(await create_user_with_perms("view_gadget", "view_author"))
        data = payload(await handle_related("gadget", {"id": gadget.pk, "relation": "owner"}, request))
        assert data == {"error": "Relation 'owner' not found on model"}

    def test_hidden_field_values_are_redacted_from_audit_log(self, hidden_api_key):
        logged = _serialize_data_for_log({"title": "g", "api_key": "s3cr3t"}, model_admin=admin.site._registry[Gadget])
        assert "s3cr3t" not in logged
        assert '"title":"g"' in logged


@pytest.mark.asyncio
@pytest.mark.django_db
class TestRelatedModelPermissions:
    """Models reached through a relation answer to their own admin's permissions."""

    async def test_related_model_outside_mcp_requires_its_view_permission(self):
        token = await sync_to_async(MCPTokenFactory)()
        request = create_mock_request(await create_user_with_perms("view_mcptoken", is_superuser=False))
        # Superuser-free lookup: scope the queryset to this user by owning the token
        await sync_to_async(MCPToken.objects.filter(pk=token.pk).update)(user=request.user)

        data = payload(await handle_related("mcptoken", {"id": token.pk, "relation": "user"}, request))

        assert data.get("code") == "permission_denied"
        assert "password" not in json.dumps(data)

    async def test_related_model_outside_mcp_served_with_view_permission(self):
        token = await sync_to_async(MCPTokenFactory)()
        request = create_mock_request(await create_user_with_perms("view_mcptoken", "view_user"))
        await sync_to_async(MCPToken.objects.filter(pk=token.pk).update)(user=request.user)

        data = payload(await handle_related("mcptoken", {"id": token.pk, "relation": "user"}, request))

        assert data["result"]["username"] == request.user.username

    async def test_inlines_require_view_permission_on_inline_model(self):
        author, _ = await create_author_with_article()

        request = create_mock_request(await create_user_with_perms("view_author"))
        data = payload(await handle_get("author", {"id": author.pk, "include_inlines": True}, request))
        assert "article" not in data["_inlines"]

        request = create_mock_request(await create_user_with_perms("view_author", "view_article"))
        data = payload(await handle_get("author", {"id": author.pk, "include_inlines": True}, request))
        assert len(data["_inlines"]["article"]) == 1


@pytest.mark.asyncio
@pytest.mark.django_db
class TestObjectLevelPermissions:
    """has_*_permission(request, obj) overrides must be honored for row operations."""

    @pytest.fixture(autouse=True)
    def deny_objects(self, monkeypatch):
        author_admin = admin.site._registry[Author]
        for name in ("has_view_permission", "has_change_permission", "has_delete_permission"):
            monkeypatch.setattr(author_admin, name, lambda request, obj=None: obj is None, raising=False)

    async def _request(self):
        return create_mock_request(await create_user_with_perms("view_author", "change_author", "delete_author"))

    async def test_get_related_history_denied(self):
        author, _ = await create_author_with_article()
        request = await self._request()
        for handler, arguments in (
            (handle_get, {"id": author.pk}),
            (handle_related, {"id": author.pk, "relation": "articles"}),
            (handle_history, {"id": author.pk}),
        ):
            assert payload(await handler("author", arguments, request)).get("code") == "permission_denied"

    async def test_update_and_delete_denied(self):
        author, _ = await create_author_with_article()
        request = await self._request()

        data = payload(await handle_update("author", {"id": author.pk, "data": {"name": "changed"}}, request))
        assert data.get("code") == "permission_denied"
        data = payload(await handle_delete("author", {"id": author.pk}, request))
        assert data.get("code") == "permission_denied"

        await sync_to_async(author.refresh_from_db)()
        assert author.name != "changed"

    async def test_bulk_and_delete_selected_denied(self):
        author, _ = await create_author_with_article()
        request = await self._request()

        items = [{"id": author.pk, "data": {"name": "changed"}}]
        data = payload(await handle_bulk("author", {"operation": "update", "items": items}, request))
        assert data["results"]["errors"][0]["code"] == "permission_denied"
        data = payload(await handle_bulk("author", {"operation": "delete", "items": [author.pk]}, request))
        assert data["results"]["errors"][0]["code"] == "permission_denied"
        data = payload(await handle_action("author", {"action": "delete_selected", "ids": [author.pk]}, request))
        assert data.get("code") == "permission_denied"

        assert await sync_to_async(Author.objects.filter(pk=author.pk, name=author.name).exists)()


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCascadeDeletePermissions:
    """Deleting must not cascade into related objects the user may not delete."""

    async def test_delete_denied_when_cascade_hits_undeletable_model(self):
        request = create_mock_request(await create_user_with_perms("view_author", "change_author", "delete_author"))

        for call in (
            lambda pk: handle_delete("author", {"id": pk}, request),
            lambda pk: handle_action("author", {"action": "delete_selected", "ids": [pk]}, request),
        ):
            author, article = await create_author_with_article()
            data = payload(await call(author.pk))
            assert data.get("code") == "permission_denied"
            assert await sync_to_async(Article.objects.filter(pk=article.pk).exists)()

        author, article = await create_author_with_article()
        data = payload(await handle_bulk("author", {"operation": "delete", "items": [author.pk]}, request))
        assert data["results"]["errors"][0]["code"] == "permission_denied"
        assert await sync_to_async(Article.objects.filter(pk=article.pk).exists)()

    async def test_delete_allowed_with_permission_on_cascaded_model(self):
        author, article = await create_author_with_article()
        request = create_mock_request(await create_user_with_perms("delete_author", "delete_article"))

        data = payload(await handle_delete("author", {"id": author.pk}, request))

        assert data.get("success") is True
        assert not await sync_to_async(Article.objects.filter(pk=article.pk).exists)()


class TestActionConfirmationData:
    def test_confirmation_data_cannot_override_selection_fields(self):
        request = create_mock_request()
        _prepare_action_request(
            request, "publish", [1], True, {"_selected_action": "999", "action": "delete_selected", "reason": "ok"}
        )
        assert request.POST.getlist("_selected_action") == ["1"]
        assert request.POST["action"] == "publish"
        assert request.POST["reason"] == "ok"


@pytest.mark.django_db
class TestTokenAdminScoping:
    """Non-superusers must not be able to take over another user's token authority."""

    def _request(self, user):
        request = RequestFactory().get("/admin/django_admin_mcp/mcptoken/")
        request.user = user
        return request

    def test_non_superuser_sees_only_own_tokens(self):
        staff = UserFactory(is_staff=True)
        own = MCPTokenFactory(user=staff)
        other = MCPTokenFactory()  # someone else's token
        token_admin = MCPTokenAdmin(MCPToken, admin.site)

        assert list(token_admin.get_queryset(self._request(staff))) == [own]
        assert other in token_admin.get_queryset(self._request(UserFactory(is_superuser=True)))

    def test_non_superuser_can_only_link_tokens_to_self(self):
        staff = UserFactory(is_staff=True)
        staff.user_permissions.set(Permission.objects.filter(codename__in=["add_mcptoken", "change_mcptoken"]))
        other = UserFactory(is_superuser=True)
        token_admin = MCPTokenAdmin(MCPToken, admin.site)

        form_class = token_admin.get_form(self._request(staff))
        assert list(form_class.base_fields["user"].queryset) == [staff]
        assert not form_class(data={"name": "t", "is_active": "on", "user": str(other.pk)}).is_valid()

        superuser_form = token_admin.get_form(self._request(other))
        assert staff in superuser_form.base_fields["user"].queryset
