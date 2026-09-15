"""
Security tests for permission bypass scenarios and token edge cases (issue #44).
"""

import datetime
import json
import uuid

import django
import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.test import AsyncClient
from django.utils import timezone

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_autocomplete,
    handle_describe,
    handle_history,
    handle_related,
)
from tests.factories import MCPTokenFactory
from tests.models import Author

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_plain_user(uid):
    return User.objects.create_user(
        username=f"noperm_{uid}", email=f"noperm_{uid}@example.com", password="x"
    )


@sync_to_async
def create_author(uid):
    return Author.objects.create(name=f"Bypass Author {uid}", email=f"bypass_{uid}@example.com")


@pytest.mark.asyncio
@pytest.mark.django_db
class TestReadHandlersDenyWithoutViewPermission:
    """Every read-oriented handler must deny users lacking view permission."""

    async def test_related_without_view_permission(self):
        uid = unique_id()
        author = await create_author(uid)
        request = create_mock_request(await create_plain_user(uid))
        result = await handle_related("author", {"id": author.pk, "relation": "articles"}, request)
        data = json.loads(result[0].text)
        assert data.get("code") == "permission_denied"

    async def test_history_without_view_permission(self):
        uid = unique_id()
        author = await create_author(uid)
        request = create_mock_request(await create_plain_user(uid))
        result = await handle_history("author", {"id": author.pk}, request)
        data = json.loads(result[0].text)
        assert data.get("code") == "permission_denied"

    async def test_autocomplete_without_view_permission(self):
        uid = unique_id()
        await create_author(uid)
        request = create_mock_request(await create_plain_user(uid))
        result = await handle_autocomplete("author", {"query": "Bypass"}, request)
        data = json.loads(result[0].text)
        assert data.get("code") == "permission_denied"

    async def test_describe_without_view_permission(self):
        uid = unique_id()
        request = create_mock_request(await create_plain_user(uid))
        result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)
        assert data.get("code") == "permission_denied"


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestTokenEdgeCases:
    """Token expiry boundaries and usage tracking."""

    async def _post(self, token_plaintext):
        client = AsyncClient()
        return await client.post(
            "/api/",
            data=json.dumps({"method": "tools/list", "id": 1}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token_plaintext}"},
        )

    @pytest.mark.asyncio
    async def test_token_expired_one_second_ago_is_rejected(self):
        token = await sync_to_async(MCPTokenFactory)(
            expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )
        response = await self._post(token.plaintext_token)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_expiring_in_the_future_is_accepted(self):
        token = await sync_to_async(MCPTokenFactory)(
            expires_at=timezone.now() + datetime.timedelta(hours=1)
        )
        response = await self._post(token.plaintext_token)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_inactive_token_not_marked_used(self):
        token = await sync_to_async(MCPTokenFactory)(is_active=False)
        response = await self._post(token.plaintext_token)
        assert response.status_code == 401

        @sync_to_async
        def get_last_used():
            token.refresh_from_db()
            return token.last_used_at

        assert await get_last_used() is None

    @pytest.mark.asyncio
    async def test_expired_token_not_marked_used(self):
        token = await sync_to_async(MCPTokenFactory)(
            expires_at=timezone.now() - datetime.timedelta(seconds=1)
        )
        response = await self._post(token.plaintext_token)
        assert response.status_code == 401

        @sync_to_async
        def get_last_used():
            token.refresh_from_db()
            return token.last_used_at

        assert await get_last_used() is None


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInputInjection:
    """Malicious filter/order inputs must be neutralized, never executed."""

    async def test_sql_injection_in_filter_keys_is_ignored(self):
        uid = unique_id()
        await create_author(uid)

        @sync_to_async
        def superuser_request():
            user = User.objects.create_superuser(
                username=f"inj_{uid}", email=f"inj_{uid}@example.com", password="x"
            )
            return create_mock_request(user)

        request = await superuser_request()
        from django_admin_mcp.handlers import handle_list  # noqa: PLC0415

        result = await handle_list(
            "author",
            {"filters": {"name; DROP TABLE tests_author; --": "x"}},
            request,
        )
        data = json.loads(result[0].text)
        # The malicious key is not a valid field: skipped, and the table survives
        assert "results" in data
        assert await sync_to_async(Author.objects.filter(name__icontains=uid).count)() == 1

    async def test_order_by_with_raw_sql_is_ignored(self):
        uid = unique_id()
        await create_author(uid)

        @sync_to_async
        def superuser_request():
            user = User.objects.create_superuser(
                username=f"inj2_{uid}", email=f"inj2_{uid}@example.com", password="x"
            )
            return create_mock_request(user)

        request = await superuser_request()
        from django_admin_mcp.handlers import handle_list  # noqa: PLC0415

        result = await handle_list(
            "author",
            {"order_by": ["name); DELETE FROM tests_author; --"]},
            request,
        )
        data = json.loads(result[0].text)
        assert "results" in data
        assert await sync_to_async(Author.objects.filter(name__icontains=uid).count)() == 1
