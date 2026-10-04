"""
Regression tests for issue #114: updates must change only the fields the
caller sent, whatever POST shape the admin form's widgets expect.

Every test goes through the real ``ModelAdmin.get_form()`` path (a user is on
the request), because that is where ``AdminSplitDateTime`` and friends come from.
"""

import datetime
import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.admin.widgets import AdminSplitDateTime
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import create_mock_request, handle_bulk, handle_create, handle_update
from django_admin_mcp.handlers.base import get_admin_form_class
from tests.models import Article, Author, Event, EventSession

UTC = datetime.timezone.utc
STARTS = datetime.datetime(2026, 3, 1, 9, 30, 15, 123456, tzinfo=UTC)
ENDS = datetime.datetime(2026, 3, 1, 17, 0, 0, tzinfo=UTC)


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def superuser_request():
    uid = unique_id()
    user = User.objects.create_superuser(username=f"admin_{uid}", email=f"admin_{uid}@example.com", password="x")
    return create_mock_request(user)


@sync_to_async
def make_event(**overrides):
    uid = unique_id()
    speakers = overrides.pop("speakers", None)
    values = {
        "name": f"Event {uid}",
        "slug": f"event-{uid}",
        "starts_at": STARTS,
        "ends_at": ENDS,
        "metadata": {"room": "A"},
        "labels": ["x"],
        "capacity": 5,
        "status": "live",
        "is_public": False,
    }
    values.update(overrides)
    event = Event.objects.create(**values)
    if speakers is None:
        speakers = [
            Author.objects.create(name=f"Speaker {uid} {i}", email=f"speaker_{uid}_{i}@example.com") for i in range(2)
        ]
    event.speakers.set(speakers)
    return event


@sync_to_async
def reload(obj):
    return type(obj).objects.get(pk=obj.pk)


@sync_to_async
def speaker_ids(event):
    return sorted(event.speakers.values_list("pk", flat=True))


async def update(model_name, request, obj, data, **extra):
    result = await handle_update(model_name, {"id": obj.pk, "data": data, **extra}, request)
    return json.loads(result[0].text)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUpdateTouchesOnlySentFields:
    async def test_admin_form_uses_split_datetime_widget(self):
        """Guard: the tests below really exercise the admin widget path."""
        request = await superuser_request()
        form_class = await sync_to_async(get_admin_form_class)(Event, admin.site._registry[Event], request)
        assert isinstance(form_class.base_fields["starts_at"].widget, AdminSplitDateTime)

    async def test_optional_datetime_survives_unrelated_update(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"name": "Renamed"})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.name == "Renamed"
        assert event.ends_at == ENDS

    async def test_required_datetime_does_not_block_update(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"capacity": 42})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.capacity == 42
        assert event.starts_at == STARTS

    async def test_untouched_datetime_keeps_microseconds(self):
        request = await superuser_request()
        event = await make_event()

        await update("event", request, event, {"capacity": 1})

        event = await reload(event)
        assert event.starts_at == STARTS
        assert event.starts_at.microsecond == 123456

    async def test_all_untouched_fields_keep_their_values(self):
        request = await superuser_request()
        event = await make_event()
        before_speakers = await speaker_ids(event)

        data = await update("event", request, event, {"status": "draft"})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.status == "draft"
        assert event.starts_at == STARTS
        assert event.ends_at == ENDS
        assert event.metadata == {"room": "A"}
        assert event.labels == ["x"]
        assert event.capacity == 5
        assert event.is_public is False
        assert await speaker_ids(event) == before_speakers

    async def test_update_with_empty_json_containers(self):
        request = await superuser_request()
        event = await make_event(metadata={}, labels=[])

        data = await update("event", request, event, {"name": "Still here"})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.metadata == {}
        assert event.labels == []

    async def test_set_json_to_empty_container(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"metadata": {}, "labels": []})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.metadata == {}
        assert event.labels == []

    async def test_set_json_value(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"metadata": {"room": "B", "floor": 2}})

        assert data.get("success") is True, data
        assert (await reload(event)).metadata == {"room": "B", "floor": 2}

    async def test_untouched_file_field_is_kept(self):
        request = await superuser_request()
        event = await make_event()

        @sync_to_async
        def attach():
            event.brochure.save(f"brochure_{unique_id()}.txt", ContentFile(b"hello"), save=True)
            return event.brochure.name

        name = await attach()
        try:
            data = await update("event", request, event, {"capacity": 9})
            assert data.get("success") is True, data
            assert (await reload(event)).brochure.name == name
        finally:
            await sync_to_async(event.brochure.delete)(save=False)

    async def test_file_field_without_file_on_disk_does_not_block_update(self):
        request = await superuser_request()
        event = await make_event(brochure="brochures/missing-on-disk.pdf")

        data = await update("event", request, event, {"capacity": 9})

        assert data.get("success") is True, data
        assert (await reload(event)).brochure.name == "brochures/missing-on-disk.pdf"

    async def test_m2m_can_be_changed_and_cleared(self):
        request = await superuser_request()
        event = await make_event()
        keep = (await speaker_ids(event))[0]

        data = await update("event", request, event, {"speakers": [keep]})
        assert data.get("success") is True, data
        assert await speaker_ids(event) == [keep]

        data = await update("event", request, event, {"speakers": []})
        assert data.get("success") is True, data
        assert await speaker_ids(event) == []
        assert (await reload(event)).starts_at == STARTS

    async def test_explicit_null_clears_optional_datetime(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"ends_at": None})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.ends_at is None
        assert event.starts_at == STARTS

    async def test_explicit_null_on_required_datetime_is_rejected(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"starts_at": None})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["starts_at"]
        assert (await reload(event)).starts_at == STARTS

    async def test_sent_field_is_still_validated(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"capacity": -1})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["capacity"]

    async def test_uniqueness_is_still_validated(self):
        request = await superuser_request()
        first = await make_event()
        second = await make_event()

        data = await update("event", request, second, {"slug": first.slug})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["slug"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDateTimeAcceptsIsoString:
    async def test_update_with_aware_iso_string(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"ends_at": "2026-06-01T12:00:00+02:00"})

        assert data.get("success") is True, data
        event = await reload(event)
        assert event.ends_at == datetime.datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        assert event.starts_at == STARTS

    async def test_update_with_naive_iso_string_uses_current_timezone(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"starts_at": "2026-06-01T12:00:00"})

        assert data.get("success") is True, data
        expected = timezone.make_aware(datetime.datetime(2026, 6, 1, 12, 0))
        assert (await reload(event)).starts_at == expected

    async def test_update_with_z_suffix_and_microseconds(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"ends_at": "2026-06-01T12:00:00.250000Z"})

        assert data.get("success") is True, data
        assert (await reload(event)).ends_at == datetime.datetime(2026, 6, 1, 12, 0, 0, 250000, tzinfo=UTC)

    async def test_update_with_invalid_datetime_string_is_rejected(self):
        request = await superuser_request()
        event = await make_event()

        data = await update("event", request, event, {"ends_at": "not a date"})

        assert data.get("code") == "validation_error", data
        assert data["validation_errors"]["fields_with_errors"] == ["ends_at"]
        assert (await reload(event)).ends_at == ENDS

    async def test_create_with_iso_string(self):
        request = await superuser_request()
        uid = unique_id()

        result = await handle_create(
            "event",
            {
                "data": {
                    "name": f"Created {uid}",
                    "slug": f"created-{uid}",
                    "starts_at": "2026-06-01T12:00:00Z",
                    "ends_at": "2026-06-01T13:00:00+00:00",
                    "capacity": 1,
                    "price": "1.00",
                    "status": "live",
                }
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.starts_at == datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        assert event.ends_at == datetime.datetime(2026, 6, 1, 13, 0, tzinfo=UTC)

    async def test_create_with_split_keys_still_works(self):
        request = await superuser_request()
        uid = unique_id()

        result = await handle_create(
            "event",
            {
                "data": {
                    "name": f"Split {uid}",
                    "slug": f"split-{uid}",
                    "starts_at_0": "2026-06-01",
                    "starts_at_1": "12:00:00",
                    "capacity": 1,
                    "price": "1.00",
                    "status": "live",
                }
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        event = await sync_to_async(Event.objects.get)(pk=data["id"])
        assert event.starts_at == timezone.make_aware(datetime.datetime(2026, 6, 1, 12, 0))

    async def test_bulk_create_with_iso_string(self):
        request = await superuser_request()
        uid = unique_id()

        result = await handle_bulk(
            "event",
            {
                "operation": "create",
                "items": [
                    {
                        "name": f"Bulk {uid}",
                        "slug": f"bulk-{uid}",
                        "starts_at": "2026-06-01T12:00:00Z",
                        "capacity": 1,
                        "price": "1.00",
                        "status": "live",
                    }
                ],
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        event = await sync_to_async(Event.objects.get)(slug=f"bulk-{uid}")
        assert event.starts_at == datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkUpdateTouchesOnlySentFields:
    async def test_bulk_update_keeps_untouched_fields(self):
        request = await superuser_request()
        event = await make_event(metadata={}, labels=[])
        before_speakers = await speaker_ids(event)

        result = await handle_bulk(
            "event",
            {"operation": "update", "items": [{"id": event.pk, "data": {"name": "Bulk renamed"}}]},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        event = await reload(event)
        assert event.name == "Bulk renamed"
        assert event.starts_at == STARTS
        assert event.ends_at == ENDS
        assert event.metadata == {}
        assert event.labels == []
        assert await speaker_ids(event) == before_speakers

    async def test_bulk_update_sets_datetime_from_iso_string(self):
        request = await superuser_request()
        event = await make_event()

        result = await handle_bulk(
            "event",
            {"operation": "update", "items": [{"id": event.pk, "data": {"ends_at": "2027-01-02T03:04:05Z"}}]},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success_count"] == 1, data
        assert (await reload(event)).ends_at == datetime.datetime(2027, 1, 2, 3, 4, 5, tzinfo=UTC)


@sync_to_async
def make_session(event, **overrides):
    values = {"event": event, "title": "Keynote", "starts_at": STARTS, "ends_at": ENDS, "notes": {}, "seats": 3}
    values.update(overrides)
    return EventSession.objects.create(**values)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineUpdateTouchesOnlySentFields:
    async def test_inline_only_update_passes_parent_validation(self):
        request = await superuser_request()
        event = await make_event()
        session = await make_session(event)

        data = await update(
            "event", request, event, {}, inlines={"eventsession": [{"id": session.pk, "data": {"title": "Opening"}}]}
        )

        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        session = await reload(session)
        assert session.title == "Opening"
        assert session.starts_at == STARTS
        assert session.ends_at == ENDS
        assert session.notes == {}
        assert session.seats == 3
        assert (await reload(event)).starts_at == STARTS

    async def test_inline_update_sets_datetime_from_iso_string(self):
        request = await superuser_request()
        event = await make_event()
        session = await make_session(event)

        data = await update(
            "event",
            request,
            event,
            {},
            inlines={"eventsession": [{"id": session.pk, "data": {"ends_at": "2026-03-01T18:00:00Z"}}]},
        )

        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        session = await reload(session)
        assert session.ends_at == datetime.datetime(2026, 3, 1, 18, 0, tzinfo=UTC)
        assert session.starts_at == STARTS

    async def test_inline_create_accepts_iso_datetime(self):
        request = await superuser_request()
        event = await make_event()

        data = await update(
            "event",
            request,
            event,
            {},
            inlines={
                "eventsession": [{"data": {"title": "Workshop", "starts_at": "2026-03-02T09:00:00Z", "seats": 4}}]
            },
        )

        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        session = await sync_to_async(EventSession.objects.get)(event=event, title="Workshop")
        assert session.starts_at == datetime.datetime(2026, 3, 2, 9, 0, tzinfo=UTC)

    async def test_existing_inline_keeps_optional_datetime(self):
        """Article is an inline of Author with an optional DateTimeField."""
        request = await superuser_request()
        uid = unique_id()
        author = await sync_to_async(Author.objects.create)(name=f"A {uid}", email=f"a_{uid}@example.com")
        article = await sync_to_async(Article.objects.create)(
            title="Old", content="c", author=author, published_date=STARTS, is_published=True
        )

        data = await update(
            "author", request, author, {}, inlines={"article": [{"id": article.pk, "data": {"title": "New"}}]}
        )

        assert data.get("success") is True, data
        article = await reload(article)
        assert article.title == "New"
        assert article.published_date == STARTS
        assert article.is_published is True


@pytest.mark.asyncio
@pytest.mark.django_db
class TestStockUserAdmin:
    """The stock UserAdmin has a required DateTimeField (date_joined) and M2M fields."""

    @pytest.fixture
    def user_admin(self):
        class MCPUserAdmin(MCPAdminMixin, UserAdmin):
            mcp_expose = True

        with patch.dict(MCPAdminMixin._registered_models):
            yield MCPUserAdmin(User, admin.site)

    async def test_update_user(self, user_admin):
        request = await superuser_request()
        joined = datetime.datetime(2020, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)
        target = await sync_to_async(User.objects.create_user)(
            username=f"target_{unique_id()}", password="secret-pass", date_joined=joined, is_staff=True
        )
        password_hash = target.password

        data = await update("user", request, target, {"first_name": "Ada"})

        assert data.get("success") is True, data
        target = await reload(target)
        assert target.first_name == "Ada"
        assert target.date_joined == joined
        assert target.password == password_hash
        assert target.is_staff is True
        assert target.is_active is True
