"""
Edge case and boundary condition tests (issue #47).

Covers integer/string boundaries, empty and null inputs, and special
characters across list/get/create handlers.
"""

import json
import sys
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_create, handle_get, handle_list
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_author(uid, **kwargs):
    defaults = {"name": f"Edge Author {uid}", "email": f"edge_{uid}@example.com"}
    defaults.update(kwargs)
    return Author.objects.create(**defaults)


@sync_to_async
def superuser_request(uid):
    user = User.objects.create_superuser(
        username=f"edge_admin_{uid}", email=f"edge_admin_{uid}@example.com", password="x"
    )
    return create_mock_request(user)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestIntegerBoundaries:
    async def test_list_limit_is_capped(self, settings):
        """Excessive limit values are capped by MCP_MAX_LIST_LIMIT (DoS guard)."""
        settings.MCP_MAX_LIST_LIMIT = 2
        uid = unique_id()
        for i in range(4):
            await create_author(f"{uid}_{i}")
        request = await superuser_request(uid)

        result = await handle_list("author", {"limit": 999999, "filters": {"name__icontains": uid}}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["total_count"] == 4

    async def test_list_default_cap_still_serves_normal_requests(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"limit": 999999}, request)
        data = json.loads(result[0].text)
        assert "results" in data

    async def test_list_negative_limit_is_rejected(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"limit": -5}, request)
        data = json.loads(result[0].text)
        assert "error" in data

    async def test_list_negative_offset_is_rejected(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"offset": -1}, request)
        data = json.loads(result[0].text)
        assert "error" in data

    async def test_list_excessive_offset_returns_empty(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"offset": 999999}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 0

    async def test_get_with_max_int_id(self):
        uid = unique_id()
        request = await superuser_request(uid)
        result = await handle_get("author", {"id": sys.maxsize}, request)
        data = json.loads(result[0].text)
        assert "not found" in data["error"]

    async def test_get_with_negative_id(self):
        uid = unique_id()
        request = await superuser_request(uid)
        result = await handle_get("author", {"id": -1}, request)
        data = json.loads(result[0].text)
        assert "error" in data


@pytest.mark.asyncio
@pytest.mark.django_db
class TestEmptyAndNullInputs:
    async def test_list_with_empty_filter_value(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"name": ""}}, request)
        data = json.loads(result[0].text)
        assert "results" in data

    async def test_list_with_null_filter_value(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"id": None}}, request)
        data = json.loads(result[0].text)
        # Must not crash; either an empty result or a handled error
        assert "results" in data or "error" in data

    async def test_order_by_empty_list(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"order_by": []}, request)
        data = json.loads(result[0].text)
        assert "results" in data

    async def test_search_with_whitespace_only(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"search": "   "}, request)
        data = json.loads(result[0].text)
        assert "results" in data

    async def test_create_null_on_required_field(self):
        uid = unique_id()
        request = await superuser_request(uid)
        result = await handle_create("author", {"data": {"name": None, "email": f"null_{uid}@example.com"}}, request)
        data = json.loads(result[0].text)
        assert "validation_errors" in data or "error" in data


@pytest.mark.asyncio
@pytest.mark.django_db
class TestStringBoundaries:
    async def test_create_max_length_field(self):
        uid = unique_id()
        request = await superuser_request(uid)
        name = "x" * 200  # Author.name max_length=200
        result = await handle_create("author", {"data": {"name": name, "email": f"max_{uid}@example.com"}}, request)
        data = json.loads(result[0].text)
        assert data.get("success") is True, data

    async def test_create_exceeds_max_length(self):
        uid = unique_id()
        request = await superuser_request(uid)
        name = "x" * 201
        result = await handle_create("author", {"data": {"name": name, "email": f"over_{uid}@example.com"}}, request)
        data = json.loads(result[0].text)
        assert "validation_errors" in data, data

    async def test_create_with_unicode_emoji(self):
        uid = unique_id()
        request = await superuser_request(uid)
        result = await handle_create(
            "author", {"data": {"name": f"Émoji 🎉 {uid}", "email": f"emoji_{uid}@example.com"}}, request
        )
        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert "🎉" in data["object"]["name"]

    async def test_filter_with_very_long_value(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"name": "y" * 10000}}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 0


@pytest.mark.asyncio
@pytest.mark.django_db
class TestSpecialCharacters:
    async def test_filter_with_sql_wildcards_is_literal(self):
        """% and _ in exact filters must match literally, not as wildcards."""
        uid = unique_id()
        await create_author(uid, name=f"Wild {uid}")
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"name": f"%ild {uid}"}}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 0

    async def test_search_with_regex_chars_is_literal(self):
        uid = unique_id()
        await create_author(uid, name=f"Regex {uid}")
        request = await superuser_request(uid)
        result = await handle_list("author", {"search": ".*+?[]"}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 0

    async def test_filter_with_null_bytes(self):
        uid = unique_id()
        await create_author(uid)
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"name": "a\x00b"}}, request)
        data = json.loads(result[0].text)
        assert "results" in data or "error" in data

    async def test_filter_with_rtl_text(self):
        uid = unique_id()
        await create_author(uid, name=f"مرحبا {uid}")
        request = await superuser_request(uid)
        result = await handle_list("author", {"filters": {"name__icontains": "مرحبا"}}, request)
        data = json.loads(result[0].text)
        assert data["count"] >= 1
