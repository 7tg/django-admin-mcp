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
from tests.models import Gadget


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def make_fixture(uid):
    gadget = Gadget.objects.create(title=f"Gadget {uid}", api_key="ORIGINAL")
    user = User.objects.create_superuser(
        username=f"bulklog_{uid}", email=f"bulklog_{uid}@example.com", password="pw"
    )
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

        result = await handle_update(
            "gadget", {"id": gadget.pk, "data": {"api_key": f"SINGLE_SECRET_{uid}"}}, request
        )
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
