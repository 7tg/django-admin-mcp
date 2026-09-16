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
from django_admin_mcp.handlers.crud import InvalidFilterError, _build_filter_query, _serialize_data_for_log
from tests.models import Article, Author


class TestFilterLookupRestrictions:
    """_build_filter_query must only accept whitelisted lookups on direct fields,
    and reject everything else loudly (issue #111) instead of silently skipping."""

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

    def test_regex_lookup_raises(self):
        """Regex lookups are not whitelisted and must be rejected loudly."""
        with pytest.raises(InvalidFilterError, match="name__regex"):
            _build_filter_query(Author, {"name__regex": ".*"})
        with pytest.raises(InvalidFilterError, match="name__iregex"):
            _build_filter_query(Author, {"name__iregex": ".*"})

    def test_startswith_lookup_raises(self):
        """Undocumented lookups like startswith must be rejected loudly."""
        with pytest.raises(InvalidFilterError, match="startswith"):
            _build_filter_query(Author, {"name__startswith": "a"})
        with pytest.raises(InvalidFilterError, match="endswith"):
            _build_filter_query(Author, {"name__endswith": "a"})

    def test_unknown_field_raises(self):
        """Unknown field names must be rejected loudly."""
        with pytest.raises(InvalidFilterError, match="nonexistent"):
            _build_filter_query(Author, {"nonexistent": "x"})

    def test_relation_traversal_raises(self):
        """Lookups traversing relations must be rejected (permission bypass risk)."""
        with pytest.raises(InvalidFilterError, match="author__email"):
            _build_filter_query(Article, {"author__email": "x@example.com"})
        with pytest.raises(InvalidFilterError, match="author__email__icontains"):
            _build_filter_query(Article, {"author__email__icontains": "x"})

    def test_error_aggregates_all_invalid_keys(self):
        """Every invalid key is reported in a single error."""
        with pytest.raises(InvalidFilterError) as exc:
            _build_filter_query(Author, {"nonexistent": "x", "name__regex": ".*", "name": "ok"})
        assert "nonexistent" in str(exc.value)
        assert "name__regex" in str(exc.value)

    def test_fk_direct_lookups_still_work(self):
        """Direct FK filters (exact / isnull) remain allowed."""
        assert _build_filter_query(Article, {"author": 1}) != Q()
        assert _build_filter_query(Article, {"author__isnull": True}) != Q()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_handle_list_rejects_disallowed_lookup(self):
        """A disallowed lookup produces an error response, never a silently unfiltered list."""

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
        assert "error" in data
        assert "name__regex" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_handle_list_rejects_invalid_order_by(self):
        """Unknown order_by fields produce an error response, not default ordering."""

        @sync_to_async
        def setup():
            user = User.objects.create_superuser(
                username="ordersec_admin",
                email="ordersec_admin@example.com",
                password="admin",
            )
            return create_mock_request(user)

        request = await setup()

        result = await handle_list("author", {"order_by": ["not_a_field"]}, request)
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not_a_field" in data["error"]

        result = await handle_list("author", {"order_by": ["-name"]}, request)
        data = json.loads(result[0].text)
        assert "error" not in data


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
