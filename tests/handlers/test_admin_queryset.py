"""
Regression tests: MCP list/get/action must honor ModelAdmin.get_queryset().

Proxy admins that partition a shared table via get_queryset should expose the
same row scope through list_* / get_* / action_* as Django admin changelists.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser, User

from django_admin_mcp.handlers import create_mock_request, handle_action, handle_get, handle_list
from tests.models import CatalogItem, CatalogItemA


def unique_id() -> str:
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_catalog_item(title: str, channel: str) -> CatalogItem:
    return CatalogItem.objects.create(title=title, channel=channel)


@sync_to_async
def create_superuser(uid: str) -> User:
    return User.objects.create_superuser(
        username=f"qs_super_{uid}",
        email=f"qs_super_{uid}@example.com",
        password="testpass",
    )


@pytest.mark.django_db
@pytest.mark.asyncio
class TestAdminGetQueryset:
    """list_* / get_* must start from model_admin.get_queryset(request)."""

    async def test_list_proxy_a_returns_only_channel_a(self):
        uid = unique_id()
        item_a = await create_catalog_item(f"Item A {uid}", "A")
        item_b = await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_list(
            "catalogitema",
            {"filters": {"title__icontains": uid}},
            request,
        )
        data = json.loads(result[0].text)

        assert "error" not in data
        assert data["total_count"] == 1
        assert data["count"] == 1
        assert data["results"][0]["id"] == item_a.pk
        assert data["results"][0]["channel"] == "A"
        assert item_b.pk not in {row["id"] for row in data["results"]}

    async def test_list_proxy_b_returns_only_channel_b(self):
        uid = unique_id()
        item_a = await create_catalog_item(f"Item A {uid}", "A")
        item_b = await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_list(
            "catalogitemb",
            {"filters": {"title__icontains": uid}},
            request,
        )
        data = json.loads(result[0].text)

        assert "error" not in data
        assert data["total_count"] == 1
        assert data["results"][0]["id"] == item_b.pk
        assert data["results"][0]["channel"] == "B"
        assert item_a.pk not in {row["id"] for row in data["results"]}

    async def test_list_client_filters_compose_with_admin_queryset(self):
        uid = unique_id()
        match = await create_catalog_item(f"Keep Me {uid}", "A")
        await create_catalog_item(f"Skip Me {uid}", "A")
        await create_catalog_item(f"Keep Me {uid}", "B")  # other channel
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_list(
            "catalogitema",
            {"filters": {"title": f"Keep Me {uid}"}},
            request,
        )
        data = json.loads(result[0].text)

        assert data["total_count"] == 1
        assert data["results"][0]["id"] == match.pk
        assert data["results"][0]["channel"] == "A"

    async def test_get_proxy_a_hides_channel_b_row(self):
        uid = unique_id()
        item_b = await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_get("catalogitema", {"id": item_b.pk}, request)
        data = json.loads(result[0].text)

        assert "error" in data
        assert "not found" in data["error"].lower()

    async def test_get_proxy_a_returns_channel_a_row(self):
        uid = unique_id()
        item_a = await create_catalog_item(f"Item A {uid}", "A")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_get("catalogitema", {"id": item_a.pk}, request)
        data = json.loads(result[0].text)

        assert "error" not in data
        assert data["id"] == item_a.pk
        assert data["channel"] == "A"

    async def test_list_permission_still_required(self):
        uid = unique_id()
        await create_catalog_item(f"Item A {uid}", "A")
        request = create_mock_request(user=AnonymousUser())

        result = await handle_list("catalogitema", {}, request)
        data = json.loads(result[0].text)

        assert data.get("code") == "permission_denied"

    async def test_mcp_use_admin_queryset_false_opt_out(self):
        """mcp_use_admin_queryset=False falls back to model.objects.all()."""
        from django.contrib import admin  # noqa: PLC0415

        uid = unique_id()
        await create_catalog_item(f"Item A {uid}", "A")
        await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        model_admin = admin.site._registry[CatalogItemA]
        had_instance_attr = "mcp_use_admin_queryset" in model_admin.__dict__
        original = model_admin.__dict__.get("mcp_use_admin_queryset")
        model_admin.mcp_use_admin_queryset = False
        try:
            result = await handle_list(
                "catalogitema",
                {"filters": {"title__icontains": uid}},
                request,
            )
            data = json.loads(result[0].text)
            assert data["total_count"] == 2
            channels = {row["channel"] for row in data["results"]}
            assert channels == {"A", "B"}
        finally:
            if had_instance_attr:
                model_admin.mcp_use_admin_queryset = original
            else:
                delattr(model_admin, "mcp_use_admin_queryset")


@pytest.mark.django_db
@pytest.mark.asyncio
class TestAdminActionGetQueryset:
    """action_* must only operate on rows inside model_admin.get_queryset()."""

    async def test_action_rejects_out_of_scope_pk(self):
        """Knowing a PK outside the admin queryset must not allow acting on it."""
        uid = unique_id()
        item_b = await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_action(
            "catalogitema",
            {"action": "delete_selected", "ids": [item_b.pk]},
            request,
        )
        data = json.loads(result[0].text)

        assert "error" in data
        assert "No objects found" in data["error"]
        assert await sync_to_async(CatalogItem.objects.filter(pk=item_b.pk).exists)()

    async def test_action_only_affects_in_scope_ids(self):
        """Mixed IDs: only rows in the admin queryset are acted on."""
        uid = unique_id()
        item_a = await create_catalog_item(f"Item A {uid}", "A")
        item_b = await create_catalog_item(f"Item B {uid}", "B")
        request = create_mock_request(user=await create_superuser(uid))

        result = await handle_action(
            "catalogitema",
            {"action": "delete_selected", "ids": [item_a.pk, item_b.pk]},
            request,
        )
        data = json.loads(result[0].text)

        assert data.get("success") is True
        assert data["affected_count"] == 1
        assert not await sync_to_async(CatalogItem.objects.filter(pk=item_a.pk).exists)()
        assert await sync_to_async(CatalogItem.objects.filter(pk=item_b.pk).exists)()
