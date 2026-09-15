"""
Concurrent access and transaction semantics tests (issue #45).
"""

import asyncio
import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_create,
    handle_delete,
    handle_update,
)
from django_admin_mcp.handlers.actions import handle_bulk_update
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_author(uid):
    return Author.objects.create(name=f"Conc Author {uid}", email=f"conc_{uid}@example.com")


@sync_to_async
def superuser_request(uid):
    user = User.objects.create_superuser(
        username=f"conc_admin_{uid}", email=f"conc_admin_{uid}@example.com", password="x"
    )
    return create_mock_request(user)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestConcurrentCrud:
    async def test_concurrent_update_same_object_keeps_data_consistent(self):
        uid = unique_id()
        author = await create_author(uid)
        request = await superuser_request(uid)

        results = await asyncio.gather(
            handle_update("author", {"id": author.pk, "data": {"name": f"Title A {uid}"}}, request),
            handle_update("author", {"id": author.pk, "data": {"name": f"Title B {uid}"}}, request),
            return_exceptions=True,
        )

        for result in results:
            assert not isinstance(result, Exception), result
            data = json.loads(result[0].text)
            assert data.get("success") is True, data

        @sync_to_async
        def final_name():
            author.refresh_from_db()
            return author.name

        assert await final_name() in {f"Title A {uid}", f"Title B {uid}"}

    async def test_concurrent_delete_same_object(self):
        """Two deletes of the same object: one succeeds, the other reports not found."""
        uid = unique_id()
        author = await create_author(uid)
        request = await superuser_request(uid)

        results = await asyncio.gather(
            handle_delete("author", {"id": author.pk}, request),
            handle_delete("author", {"id": author.pk}, request),
            return_exceptions=True,
        )

        outcomes = []
        for result in results:
            assert not isinstance(result, Exception), result
            outcomes.append(json.loads(result[0].text))

        successes = [o for o in outcomes if o.get("success")]
        not_found = [o for o in outcomes if "not found" in str(o.get("error", ""))]
        assert len(successes) == 1, outcomes
        assert len(not_found) == 1, outcomes
        assert await sync_to_async(Author.objects.filter(pk=author.pk).count)() == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestTransactionSemantics:
    async def test_create_rolls_back_when_logging_fails(self):
        """If admin logging fails, the created object must roll back too."""
        uid = unique_id()
        request = await superuser_request(uid)

        with patch(
            "django_admin_mcp.handlers.crud._log_action",
            side_effect=RuntimeError("log backend down"),
        ):
            result = await handle_create(
                "author",
                {"data": {"name": f"Ghost {uid}", "email": f"ghost_{uid}@example.com"}},
                request,
            )

        data = json.loads(result[0].text)
        assert "error" in data
        assert await sync_to_async(Author.objects.filter(name=f"Ghost {uid}").count)() == 0

    async def test_bulk_update_is_per_item_not_all_or_nothing(self):
        """Bulk operations apply valid items and report invalid ones independently."""
        uid = unique_id()
        good = await create_author(f"good_{uid}")
        request = await superuser_request(uid)

        result = await handle_bulk_update(
            "author",
            {
                "items": [
                    {"id": good.pk, "data": {"name": f"Updated {uid}"}},
                    {"id": 99999999, "data": {"name": "nope"}},
                ]
            },
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        assert data["error_count"] == 1, data

        @sync_to_async
        def good_name():
            good.refresh_from_db()
            return good.name

        assert await good_name() == f"Updated {uid}"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestTokenConcurrency:
    async def test_token_survives_concurrent_authenticated_requests(self):
        import django  # noqa: PLC0415

        if django.VERSION < (4, 2):
            pytest.skip("AsyncClient headers= requires Django 4.2+")

        from django.test import AsyncClient  # noqa: PLC0415

        from tests.factories import MCPTokenFactory  # noqa: PLC0415

        token = await sync_to_async(MCPTokenFactory)()

        async def hit():
            client = AsyncClient()
            return await client.post(
                "/api/",
                data=json.dumps({"method": "tools/list", "id": 1}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {token.plaintext_token}"},
            )

        responses = await asyncio.gather(hit(), hit(), hit())
        assert all(r.status_code == 200 for r in responses)

        @sync_to_async
        def last_used():
            token.refresh_from_db()
            return token.last_used_at

        assert await last_used() is not None
