"""
Tests for issue #100: admin hooks calling message_user() must not crash MCP writes,
and issue #119: the messages they queue are returned in the tool response.

The synthetic requests used by MCP handlers (MCPRequest and the request built
in views._request_for_token) need a messages storage so ModelAdmin hooks that
call self.message_user(request, ...) don't raise MessageFailure and roll back
the surrounding transaction.
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_action,
    handle_create,
    handle_delete,
    handle_update,
)
from django_admin_mcp.handlers.base import get_model_admin
from django_admin_mcp.models import MCPToken
from django_admin_mcp.views import _request_for_token
from tests.factories import MCPTokenFactory
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid):
    return User.objects.create_superuser(
        username=f"msg_admin_{uid}",
        email=f"msg_{uid}@example.com",
        password="pw",
    )


class TestSyntheticRequestMessages:
    """messages.add_message on synthetic MCP requests must not raise."""

    def test_mock_request_accepts_messages(self):
        request = create_mock_request(None)
        messages.add_message(request, messages.INFO, "hello")

    @pytest.mark.django_db
    def test_request_for_token_accepts_messages(self):
        token = MCPTokenFactory()
        request = _request_for_token(token)
        messages.add_message(request, messages.INFO, "hello")


@pytest.mark.asyncio
@pytest.mark.django_db
class TestMessageUserDoesNotBreakWrites:
    """Admin save_model hooks calling message_user must not abort MCP writes."""

    async def test_create_mcptoken_succeeds_despite_message_user(self):
        """MCPTokenAdmin.save_model calls message_user; create_mcptoken must succeed."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)

        result = await handle_create(
            "mcptoken",
            {"data": {"name": f"tok {uid}", "user": user.pk, "is_active": True}},
            request,
        )
        data = json.loads(result[0].text)

        assert data.get("success") is True, data
        assert await sync_to_async(MCPToken.objects.filter(name=f"tok {uid}").exists)()


@sync_to_async
def create_author(uid):
    return Author.objects.create(name=f"Msg Author {uid}", email=f"msg_author_{uid}@example.com")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestMessagesReturnedInResponses:
    """Issue #119: messages queued by admin code are returned to the caller."""

    async def test_action_returns_queued_messages(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")

        def discontinue(modeladmin, request, queryset):
            modeladmin.message_user(request, f"{queryset.count()} authors discontinued", messages.SUCCESS)
            modeladmin.message_user(request, "1 author skipped", messages.WARNING)

        with patch.object(author_admin, "actions", [discontinue]):
            result = await handle_action("author", {"action": "discontinue", "ids": [author.pk]}, request)
        data = json.loads(result[0].text)

        assert data["success"] is True, data
        assert data["result"] is None
        assert data["messages"] == [
            {"level": "success", "message": "1 authors discontinued"},
            {"level": "warning", "message": "1 author skipped"},
        ]

    async def test_action_without_messages_omits_key(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")

        def quiet(modeladmin, request, queryset):
            return None

        with patch.object(author_admin, "actions", [quiet]):
            result = await handle_action("author", {"action": "quiet", "ids": [author.pk]}, request)
        data = json.loads(result[0].text)

        assert data["success"] is True, data
        assert "messages" not in data

    async def test_messages_are_not_repeated_on_a_reused_request(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")

        def notify(modeladmin, request, queryset):
            modeladmin.message_user(request, "notified")

        with patch.object(author_admin, "actions", [notify]):
            await handle_action("author", {"action": "notify", "ids": [author.pk]}, request)
            result = await handle_action("author", {"action": "notify", "ids": [author.pk]}, request)
        data = json.loads(result[0].text)

        assert data["messages"] == [{"level": "info", "message": "notified"}]

    async def test_create_returns_messages_from_save_model(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        _, author_admin = get_model_admin("author")
        original = author_admin.save_model

        def save_model(request, obj, form, change):
            original(request, obj, form, change)
            author_admin.message_user(request, "Welcome mail queued", messages.INFO)

        with patch.object(author_admin, "save_model", save_model):
            result = await handle_create(
                "author", {"data": {"name": f"New {uid}", "email": f"new_{uid}@example.com"}}, request
            )
        data = json.loads(result[0].text)

        assert data["success"] is True, data
        assert data["messages"] == [{"level": "info", "message": "Welcome mail queued"}]

    async def test_update_returns_messages_from_save_model(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")
        original = author_admin.save_model

        def save_model(request, obj, form, change):
            original(request, obj, form, change)
            author_admin.message_user(request, "Search index refreshed", messages.SUCCESS)

        with patch.object(author_admin, "save_model", save_model):
            result = await handle_update("author", {"id": author.pk, "data": {"name": f"Renamed {uid}"}}, request)
        data = json.loads(result[0].text)

        assert data["success"] is True, data
        assert data["messages"] == [{"level": "success", "message": "Search index refreshed"}]

    async def test_delete_returns_messages_from_delete_model(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")
        original = author_admin.delete_model

        def delete_model(request, obj):
            original(request, obj)
            author_admin.message_user(request, "Archive copy kept", messages.WARNING)

        with patch.object(author_admin, "delete_model", delete_model):
            result = await handle_delete("author", {"id": author.pk}, request)
        data = json.loads(result[0].text)

        assert data["success"] is True, data
        assert data["messages"] == [{"level": "warning", "message": "Archive copy kept"}]

    async def test_crud_responses_omit_messages_when_none_queued(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))

        result = await handle_create(
            "author", {"data": {"name": f"Quiet {uid}", "email": f"quiet_{uid}@example.com"}}, request
        )
        created = json.loads(result[0].text)
        result = await handle_update("author", {"id": created["id"], "data": {"name": f"Quieter {uid}"}}, request)
        updated = json.loads(result[0].text)
        result = await handle_delete("author", {"id": created["id"]}, request)
        deleted = json.loads(result[0].text)

        for data in (created, updated, deleted):
            assert data["success"] is True, data
            assert "messages" not in data


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestReturnMessagesOptOut:
    """Issue #119: mcp_return_messages = False keeps queued messages out of responses."""

    async def test_opted_out_admin_returns_no_messages(self):
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        doomed = await create_author(unique_id())
        _, author_admin = get_model_admin("author")
        original_save = author_admin.save_model
        original_delete = author_admin.delete_model

        def save_model(request, obj, form, change):
            original_save(request, obj, form, change)
            author_admin.message_user(request, "internal detail")

        def delete_model(request, obj):
            original_delete(request, obj)
            author_admin.message_user(request, "internal detail")

        def notify(modeladmin, request, queryset):
            modeladmin.message_user(request, "internal detail")

        with (
            patch.object(author_admin, "mcp_return_messages", False, create=True),
            patch.object(author_admin, "save_model", save_model),
            patch.object(author_admin, "delete_model", delete_model),
            patch.object(author_admin, "actions", [notify]),
        ):
            results = [
                await handle_create(
                    "author", {"data": {"name": f"Opt {uid}", "email": f"opt_{uid}@example.com"}}, request
                ),
                await handle_update("author", {"id": author.pk, "data": {"name": f"Opted {uid}"}}, request),
                await handle_action("author", {"action": "notify", "ids": [author.pk]}, request),
                await handle_delete("author", {"id": doomed.pk}, request),
            ]

        for result in results:
            data = json.loads(result[0].text)
            assert data["success"] is True, data
            assert "messages" not in data
            assert "internal detail" not in result[0].text

    async def test_opted_out_messages_are_drained_not_carried_over(self):
        """Suppressed messages must not surface on a later call that reuses the request."""
        uid = unique_id()
        request = create_mock_request(await create_superuser(uid))
        author = await create_author(uid)
        _, author_admin = get_model_admin("author")

        def notify(modeladmin, request, queryset):
            modeladmin.message_user(request, "internal detail")

        def quiet(modeladmin, request, queryset):
            return None

        with patch.object(author_admin, "actions", [notify, quiet]):
            with patch.object(author_admin, "mcp_return_messages", False, create=True):
                await handle_action("author", {"action": "notify", "ids": [author.pk]}, request)
            result = await handle_action("author", {"action": "quiet", "ids": [author.pk]}, request)

        assert "messages" not in json.loads(result[0].text)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestMCPTokenAdminNeverReturnsTokenMaterial:
    """
    Issue #119: MCPTokenAdmin reports a new token's plaintext via message_user().
    Returning it over MCP would let a narrowed token mint a wider one and read
    its secret, so the token admin opts out of returning messages.
    """

    async def test_create_mcptoken_does_not_return_plaintext(self):
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        plaintexts = []
        original = MCPToken.get_plaintext_token

        def recording(self):
            plaintext = original(self)
            if plaintext:
                plaintexts.append(plaintext)
            return plaintext

        with patch.object(MCPToken, "get_plaintext_token", recording):
            result = await handle_create(
                "mcptoken", {"data": {"name": f"tok {uid}", "user": user.pk, "is_active": True}}, request
            )
        text = result[0].text
        data = json.loads(text)

        assert data.get("success") is True, data
        assert "messages" not in data
        # The admin did queue the plaintext; none of it may reach the response
        assert len(plaintexts) == 1
        key, secret = plaintexts[0][len("mcp_") :].split(".", 1)
        assert plaintexts[0] not in text
        assert key not in text
        assert secret not in text

    async def test_update_and_delete_selected_mcptoken_return_no_token_material(self):
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)
        token = await sync_to_async(MCPTokenFactory)(user=user)
        key, secret = token.plaintext_token[len("mcp_") :].split(".", 1)

        results = [
            await handle_update("mcptoken", {"id": token.pk, "data": {"name": f"renamed {uid}"}}, request),
            await handle_action("mcptoken", {"action": "delete_selected", "ids": [token.pk]}, request),
        ]

        for result in results:
            data = json.loads(result[0].text)
            assert data["success"] is True, data
            assert "messages" not in data
            assert key not in result[0].text
            assert secret not in result[0].text
