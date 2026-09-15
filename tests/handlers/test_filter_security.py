"""
Tests for filter lookup restrictions and audit-log redaction.

Covers security issues #40 (filter lookup types not restricted) and
#42 (sensitive data may be logged in audit trail).
"""

import json

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.db.models import Q

from django_admin_mcp.handlers import create_mock_request, handle_list
from django_admin_mcp.handlers.crud import _build_filter_query, _serialize_data_for_log
from tests.models import Article, Author


class TestFilterLookupRestrictions:
    """_build_filter_query must only accept whitelisted lookups on direct fields."""

    def test_allowed_lookups_build_filters(self):
        """Documented safe lookups produce a non-empty query."""
        allowed = [
            {"name": "x"},
            {"name__exact": "x"},
            {"name__icontains": "x"},
            {"name__contains": "x"},
            {"id__gte": 1},
            {"id__lte": 1},
            {"id__gt": 1},
            {"id__lt": 1},
            {"id__in": [1, 2]},
            {"bio__isnull": True},
        ]
        for filters in allowed:
            q = _build_filter_query(Author, filters)
            assert q != Q(), f"{filters} should be accepted"

    def test_regex_lookup_ignored(self):
        """Regex lookups are not whitelisted and must be skipped."""
        assert _build_filter_query(Author, {"name__regex": ".*"}) == Q()
        assert _build_filter_query(Author, {"name__iregex": ".*"}) == Q()

    def test_startswith_lookup_ignored(self):
        """Undocumented lookups like startswith must be skipped."""
        assert _build_filter_query(Author, {"name__startswith": "a"}) == Q()
        assert _build_filter_query(Author, {"name__endswith": "a"}) == Q()

    def test_relation_traversal_ignored(self):
        """Lookups traversing relations must be skipped (permission bypass risk)."""
        assert _build_filter_query(Article, {"author__email": "x@example.com"}) == Q()
        assert _build_filter_query(Article, {"author__email__icontains": "x"}) == Q()

    def test_fk_direct_lookups_still_work(self):
        """Direct FK filters (exact / isnull) remain allowed."""
        assert _build_filter_query(Article, {"author": 1}) != Q()
        assert _build_filter_query(Article, {"author__isnull": True}) != Q()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_handle_list_ignores_disallowed_lookup(self):
        """A disallowed lookup is skipped, not applied, at the handler level."""

        @sync_to_async
        def setup():
            Author.objects.create(name="Filter Sec One", email="filtersec1@example.com")
            Author.objects.create(name="Filter Sec Two", email="filtersec2@example.com")
            user = User.objects.create_superuser(
                username="filtersec_admin",
                email="filtersec_admin@example.com",
                password="admin",
            )
            return create_mock_request(user)

        request = await setup()

        result = await handle_list(
            "author",
            {"filters": {"name__regex": "^Filter Sec One$", "name__icontains": "Filter Sec"}},
            request,
        )

        data = json.loads(result[0].text)
        # The regex lookup must be ignored; only the icontains filter applies.
        assert data["count"] == 2


class TestSerializeDataForLogRedaction:
    """_serialize_data_for_log must redact sensitive values before logging."""

    def test_sensitive_keys_redacted(self):
        data = {
            "password": "hunter2secret",
            "api_token": "tok_123456",
            "secret_key": "sk_livevalue",
            "auth_header": "Bearer abcdef",
            "name": "public name",
        }
        result = _serialize_data_for_log(data)

        assert "hunter2secret" not in result
        assert "tok_123456" not in result
        assert "sk_livevalue" not in result
        assert "Bearer abcdef" not in result
        assert "public name" in result
        assert "REDACTED" in result

    def test_non_sensitive_data_unchanged(self):
        result = _serialize_data_for_log({"title": "hello", "count": 3})
        assert "hello" in result
        assert "REDACTED" not in result

    def test_truncation_still_applies(self):
        result = _serialize_data_for_log({"title": "x" * 1000}, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")
