"""
Tests for issue #103: search_fields operator prefixes (^, =, @) must not break
list search or autocomplete — searching goes through the admin's
get_search_results() pipeline.
"""

import json
import uuid
from contextlib import contextmanager

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, get_model_admin, handle_autocomplete, handle_list
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@contextmanager
def author_search_fields(fields):
    """Temporarily set search_fields on the registered Author admin."""
    _, model_admin = get_model_admin("author")
    original = model_admin.search_fields
    model_admin.search_fields = fields
    try:
        yield model_admin
    finally:
        model_admin.search_fields = original


@sync_to_async
def make_fixture(uid):
    ada = Author.objects.create(name=f"Ada {uid}", email=f"ada_{uid}@example.com")
    grada = Author.objects.create(name=f"Grada {uid}", email=f"grada_{uid}@example.com")
    user = User.objects.create_superuser(username=f"search_{uid}", email=f"search_{uid}@example.com", password="pw")
    return ada, grada, user


@pytest.mark.asyncio
@pytest.mark.django_db
class TestSearchFieldPrefixes:
    """Prefixed search_fields must work through list search and autocomplete."""

    async def test_list_search_with_startswith_prefix(self):
        uid = unique_id()
        ada, grada, user = await make_fixture(uid)
        request = create_mock_request(user)

        with author_search_fields(["^name", "=email"]):
            result = await handle_list("author", {"search": "Ada"}, request)
        data = json.loads(result[0].text)

        assert "error" not in data, data
        names = {row["name"] for row in data["results"]}
        # ^name is a startswith match: "Ada ..." matches, "Grada ..." does not
        assert ada.name in names
        assert grada.name not in names

    async def test_autocomplete_with_startswith_prefix(self):
        uid = unique_id()
        ada, grada, user = await make_fixture(uid)
        request = create_mock_request(user)

        with author_search_fields(["^name", "=email"]):
            result = await handle_autocomplete("author", {"term": "Ada"}, request)
        data = json.loads(result[0].text)

        assert "error" not in data, data
        ids = {row["id"] for row in data["results"]}
        assert ada.pk in ids
        assert grada.pk not in ids

    async def test_list_search_uses_custom_get_search_results(self):
        uid = unique_id()
        ada, grada, user = await make_fixture(uid)
        request = create_mock_request(user)
        _, model_admin = get_model_admin("author")

        def only_grada(request, queryset, search_term):
            return queryset.filter(pk=grada.pk), False

        original = model_admin.get_search_results
        model_admin.get_search_results = only_grada
        try:
            result = await handle_list("author", {"search": "anything"}, request)
        finally:
            model_admin.get_search_results = original
        data = json.loads(result[0].text)

        assert "error" not in data, data
        assert {row["name"] for row in data["results"]} == {grada.name}
