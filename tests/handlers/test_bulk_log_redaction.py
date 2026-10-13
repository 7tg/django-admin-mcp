"""
Tests for issue #104: bulk update must redact sensitive values in LogEntry,
exactly like the single update path.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_bulk, handle_update
from tests.models import Article, Author, Gadget


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def make_fixture(uid):
    gadget = Gadget.objects.create(title=f"Gadget {uid}", api_key="ORIGINAL")
    user = User.objects.create_superuser(username=f"bulklog_{uid}", email=f"bulklog_{uid}@example.com", password="pw")
    return gadget, user


@sync_to_async
def latest_log_message(obj):
    entry = LogEntry.objects.filter(object_id=str(obj.pk)).order_by("-id").first()
    return entry.change_message if entry else None


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkUpdateLogRedaction:
    """Bulk updated LogEntry messages must never contain sensitive values."""

    async def test_bulk_update_redacts_sensitive_values(self):
        uid = unique_id()
        gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_bulk(
            "gadget",
            {"operation": "update", "items": [{"id": gadget.pk, "data": {"api_key": f"BULK_SECRET_{uid}"}}]},
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data

        message = await latest_log_message(gadget)
        assert message is not None
        assert f"BULK_SECRET_{uid}" not in message
        assert "REDACTED" in message

    async def test_single_update_still_redacts(self):
        """Parity check: the single path keeps its redaction."""
        uid = unique_id()
        gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_update("gadget", {"id": gadget.pk, "data": {"api_key": f"SINGLE_SECRET_{uid}"}}, request)
        data = json.loads(result[0].text)
        assert data.get("success") is True, data

        message = await latest_log_message(gadget)
        assert f"SINGLE_SECRET_{uid}" not in message
        assert "REDACTED" in message

    async def test_bulk_update_truncation_has_no_stray_quote(self):
        uid = unique_id()
        gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_bulk(
            "gadget",
            {"operation": "update", "items": [{"id": gadget.pk, "data": {"title": "x" * 1000}}]},
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data

        message = await latest_log_message(gadget)
        assert '(truncated)"' not in message
        assert message.endswith("...")


@sync_to_async
def make_article_fixture(uid):
    first = Author.objects.create(name=f"First {uid}", email=f"first_{uid}@example.com")
    second = Author.objects.create(name=f"Second {uid}", email=f"second_{uid}@example.com")
    article = Article.objects.create(title=f"Article {uid}", content="x", author=first)
    user = User.objects.create_superuser(username=f"authlog_{uid}", email=f"authlog_{uid}@example.com", password="pw")
    return article, second, user


@pytest.mark.asyncio
@pytest.mark.django_db
class TestAuthorFieldNotRedacted:
    """A field named ``author`` is not a credential; its change must stay readable in history."""

    async def test_update_logs_author_value(self):
        uid = unique_id()
        article, second, user = await make_article_fixture(uid)
        request = create_mock_request(user)

        result = await handle_update("article", {"id": article.pk, "data": {"author": second.pk}}, request)
        data = json.loads(result[0].text)
        assert data.get("success") is True, data

        message = await latest_log_message(article)
        assert "REDACTED" not in message
        assert f'"author":{second.pk}' in message.replace(" ", "")

    async def test_bulk_update_logs_author_value(self):
        uid = unique_id()
        article, second, user = await make_article_fixture(uid)
        request = create_mock_request(user)

        result = await handle_bulk(
            "article",
            {"operation": "update", "items": [{"id": article.pk, "data": {"author": second.pk}}]},
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data

        message = await latest_log_message(article)
        assert "REDACTED" not in message
        assert f'"author":{second.pk}' in message.replace(" ", "")
