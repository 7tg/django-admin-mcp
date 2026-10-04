"""
Regression tests for issue #115: create must apply model defaults for omitted
fields and honor ``prepopulated_fields``, as the admin add form does.
"""

import datetime
import json
import uuid
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_bulk, handle_create, handle_update
from tests.models import Event, EventSession

START = "2026-06-01T12:00:00Z"
NEW_YEAR = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def superuser_request():
    uid = unique_id()
    user = User.objects.create_superuser(username=f"admin_{uid}", email=f"admin_{uid}@example.com", password="x")
    return create_mock_request(user)


async def create(request, data):
    result = await handle_create("event", {"data": data}, request)
    return json.loads(result[0].text)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCreateAppliesModelDefaults:
    async def test_omitted_fields_fall_back_to_defaults(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"E {uid}", "slug": f"e-{uid}", "starts_at": START})

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.capacity == 0
        assert event.price == Decimal("0")
        assert event.status == "draft"
        assert event.is_public is True
        assert event.metadata == {}
        assert event.labels == []
        assert event.ends_at is None

    async def test_explicit_values_win_over_defaults(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(
            request,
            {
                "name": f"E {uid}",
                "slug": f"e-{uid}",
                "starts_at": START,
                "capacity": 7,
                "price": "4.50",
                "status": "live",
                "is_public": False,
                "metadata": {"k": "v"},
            },
        )

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.capacity == 7
        assert event.price == Decimal("4.50")
        assert event.status == "live"
        assert event.is_public is False
        assert event.metadata == {"k": "v"}

    async def test_explicit_null_is_still_validated(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"E {uid}", "slug": f"e-{uid}", "starts_at": START, "capacity": None})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["capacity"]

    async def test_required_field_without_default_is_still_required(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"E {uid}", "slug": f"e-{uid}"})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["starts_at"]

    async def test_bulk_create_applies_defaults(self):
        request = await superuser_request()
        uid = unique_id()

        result = await handle_bulk(
            "event",
            {"operation": "create", "items": [{"name": f"B {uid}", "slug": f"b-{uid}", "starts_at": START}]},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        event = await sync_to_async(Event.objects.get)(slug=f"b-{uid}")
        assert event.capacity == 0
        assert event.status == "draft"
        assert event.is_public is True

    async def test_inline_create_applies_defaults(self):
        request = await superuser_request()
        uid = unique_id()
        event = await sync_to_async(Event.objects.create)(name=f"P {uid}", slug=f"p-{uid}", starts_at=NEW_YEAR)

        result = await handle_update(
            "event",
            {"id": event.pk, "data": {}, "inlines": {"eventsession": [{"data": {"title": "S", "starts_at": START}}]}},
            request,
        )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        session = await sync_to_async(EventSession.objects.get)(event=event)
        assert session.seats == 10
        assert session.notes == {}


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCreateHonorsPrepopulatedFields:
    async def test_omitted_slug_is_derived_from_source(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"Board Games {uid}", "starts_at": START})

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.slug == f"board-games-{uid}"

    async def test_empty_slug_is_derived_from_source(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"Card Games {uid}", "slug": "", "starts_at": START})

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.slug == f"card-games-{uid}"

    async def test_explicit_slug_wins(self):
        request = await superuser_request()
        uid = unique_id()

        data = await create(request, {"name": f"Dice {uid}", "slug": f"custom-{uid}", "starts_at": START})

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.slug == f"custom-{uid}"

    async def test_derived_slug_respects_max_length(self):
        request = await superuser_request()

        data = await create(request, {"name": "x" * 80, "starts_at": START})

        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.slug == "x" * 50

    async def test_bulk_create_derives_slug(self):
        request = await superuser_request()
        uid = unique_id()

        result = await handle_bulk(
            "event",
            {"operation": "create", "items": [{"name": f"Bulk Slug {uid}", "starts_at": START}]},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        assert await sync_to_async(Event.objects.filter(slug=f"bulk-slug-{uid}").exists)()

    async def test_update_does_not_rewrite_slug(self):
        request = await superuser_request()
        uid = unique_id()
        event = await sync_to_async(Event.objects.create)(name=f"Orig {uid}", slug=f"orig-{uid}", starts_at=NEW_YEAR)

        result = await handle_update("event", {"id": event.pk, "data": {"name": "Renamed"}}, request)

        assert json.loads(result[0].text).get("success") is True
        assert (await sync_to_async(Event.objects.get)(pk=event.pk)).slug == f"orig-{uid}"
