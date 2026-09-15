"""
Tests for issue #110: input-validation gaps.

1. pk=0 is a legitimate primary key, not a missing id.
2. bulk_* with non-list items must return an error, not a success-shaped no-op.
3. handle_history must honor the offset it accepts.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_bulk,
    handle_delete,
    handle_get,
    handle_history,
    handle_update,
)
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def make_superuser(uid):
    return User.objects.create_superuser(
        username=f"validation_{uid}", email=f"validation_{uid}@example.com", password="pw"
    )


@sync_to_async
def make_author_with_pk_zero(uid):
    Author.objects.filter(pk=0).delete()
    return Author.objects.create(id=0, name=f"Zero {uid}", email=f"zero_{uid}@example.com")


@pytest.mark.asyncio
@pytest.mark.django_db
class TestFalsyPrimaryKeys:
    """pk=0 must be looked up, not rejected as missing."""

    async def test_get_with_pk_zero(self):
        uid = unique_id()
        author = await make_author_with_pk_zero(uid)
        request = create_mock_request(await make_superuser(uid))

        result = await handle_get("author", {"id": 0}, request)
        data = json.loads(result[0].text)

        assert data.get("error") is None, data
        assert data["name"] == author.name

    async def test_update_with_pk_zero(self):
        uid = unique_id()
        author = await make_author_with_pk_zero(uid)
        request = create_mock_request(await make_superuser(uid))

        result = await handle_update("author", {"id": 0, "data": {"name": f"Zero2 {uid}"}}, request)
        data = json.loads(result[0].text)

        assert data.get("success") is True, data

    async def test_history_with_pk_zero(self):
        uid = unique_id()
        author = await make_author_with_pk_zero(uid)
        request = create_mock_request(await make_superuser(uid))

        result = await handle_history("author", {"id": 0}, request)
        data = json.loads(result[0].text)

        assert data.get("error") is None, data
        assert data["object_id"] == 0

    async def test_delete_with_pk_zero(self):
        uid = unique_id()
        author = await make_author_with_pk_zero(uid)
        request = create_mock_request(await make_superuser(uid))

        result = await handle_delete("author", {"id": 0}, request)
        data = json.loads(result[0].text)

        assert data.get("success") is True, data

    async def test_empty_string_id_is_still_missing(self):
        uid = unique_id()
        request = create_mock_request(await make_superuser(uid))

        result = await handle_get("author", {"id": ""}, request)
        data = json.loads(result[0].text)

        assert data.get("error") == "id parameter is required"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkItemsMustBeAList:
    """bulk_* with a non-list items argument must error, not silently no-op."""

    async def test_bulk_delete_with_string_items_errors(self):
        uid = unique_id()
        request = create_mock_request(await make_superuser(uid))

        result = await handle_bulk("author", {"operation": "delete", "items": "abc"}, request)
        data = json.loads(result[0].text)

        assert data.get("error") == "items must be a list"

    async def test_bulk_update_with_dict_items_errors(self):
        uid = unique_id()
        request = create_mock_request(await make_superuser(uid))

        result = await handle_bulk("author", {"operation": "update", "items": {"id": 1}}, request)
        data = json.loads(result[0].text)

        assert data.get("error") == "items must be a list"

    async def test_bulk_create_with_string_items_errors(self):
        uid = unique_id()
        request = create_mock_request(await make_superuser(uid))

        result = await handle_bulk("author", {"operation": "create", "items": "nope"}, request)
        data = json.loads(result[0].text)

        assert data.get("error") == "items must be a list"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestHistoryOffset:
    """handle_history must honor the offset argument it validates."""

    async def test_history_offset_pages_through_entries(self):
        uid = unique_id()
        user = await make_superuser(uid)
        request = create_mock_request(user)

        @sync_to_async
        def make_author():
            return Author.objects.create(name=f"Hist {uid}", email=f"hist_{uid}@example.com")

        author = await make_author()

        # Generate three history entries
        for i in range(3):
            await handle_update("author", {"id": author.pk, "data": {"bio": f"v{i}"}}, request)

        full = json.loads((await handle_history("author", {"id": author.pk}, request))[0].text)
        assert full["count"] == 3

        page1 = json.loads((await handle_history("author", {"id": author.pk, "limit": 2}, request))[0].text)
        assert page1["count"] == 2

        page2 = json.loads(
            (await handle_history("author", {"id": author.pk, "limit": 2, "offset": 2}, request))[0].text
        )
        assert page2["count"] == 1

        beyond = json.loads(
            (await handle_history("author", {"id": author.pk, "limit": 2, "offset": 10}, request))[0].text
        )
        assert beyond["count"] == 0
