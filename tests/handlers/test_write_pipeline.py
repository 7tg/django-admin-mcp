"""
Regression tests for issue #118: the write pipeline must match the admin's
``changeform_view``.

- ``save_related()`` and ``save_formset()`` run, so project overrides do too
- parent and inline writes are one transaction
- ``create_*`` accepts ``inlines``
- read-only checks use ``get_readonly_fields(request, obj)``
- a key the form will not consume is rejected, never dropped
- ``bulk_*`` returns ``message_user()`` output through ``attach_messages``
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import create_mock_request, handle_bulk, handle_create, handle_update
from django_admin_mcp.handlers.base import get_model_admin
from django_admin_mcp.handlers.write import WriteRejected, save_through_admin
from django_admin_mcp.models import MCPToken
from django_admin_mcp.tools.registry import get_model_tools
from tests.models import Article, Author, Event, EventSession, Product

START = "2026-03-01T09:00:00Z"


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def superuser_request():
    uid = unique_id()
    user = User.objects.create_superuser(username=f"wp_admin_{uid}", email=f"wp_{uid}@example.com", password="x")
    return create_mock_request(user)


@sync_to_async
def request_with_perms(*codenames):
    uid = unique_id()
    user = User.objects.create_user(username=f"wp_user_{uid}", password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return create_mock_request(User.objects.get(pk=user.pk))


@sync_to_async
def make_event(sessions=0):
    uid = unique_id()
    event = Event.objects.create(name=f"Event {uid}", slug=f"event-{uid}", starts_at=START)
    rows = [EventSession.objects.create(event=event, title=f"S{i}", starts_at=START) for i in range(sessions)]
    return event, rows


@sync_to_async
def reload(obj):
    return type(obj).objects.get(pk=obj.pk)


@sync_to_async
def session_titles(event_id):
    return sorted(EventSession.objects.filter(event_id=event_id).values_list("title", flat=True))


def event_data(**overrides):
    uid = unique_id()
    return {"name": f"Event {uid}", "slug": f"event-{uid}", "starts_at": START, **overrides}


async def call(handler, model_name, arguments, request):
    result = await handler(model_name, arguments, request)
    return json.loads(result[0].text)


def event_admin():
    return get_model_admin("event")[1]


def recording(original, calls):
    """Wrap an admin hook so calls are recorded and the original still runs."""

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    return wrapper


def registered(admin_class, model):
    """Register ``admin_class`` as the MCP admin for ``model`` until the patch is undone."""
    model_admin = admin_class(model, admin.site)
    entry = {"model": model, "admin": model_admin}
    return patch.dict(MCPAdminMixin._registered_models, {model._meta.model_name: entry})


@pytest.fixture
def product_admin():
    """A Product admin whose form leaves out ``cost``; Product has editable=False fields."""

    class ProductAdmin(MCPAdminMixin, admin.ModelAdmin):
        mcp_expose = True
        exclude = ["cost"]

    with patch.dict(MCPAdminMixin._registered_models), registered(ProductAdmin, Product):
        yield


@pytest.fixture
def user_admin():
    class MCPUserAdmin(MCPAdminMixin, UserAdmin):
        mcp_expose = True

    with patch.dict(MCPAdminMixin._registered_models), registered(MCPUserAdmin, User):
        yield


@pytest.mark.asyncio
@pytest.mark.django_db
class TestAdminSaveHooksRun:
    async def test_create_calls_save_related(self):
        request = await superuser_request()
        speaker = await sync_to_async(Author.objects.create)(name="Sp", email=f"sp_{unique_id()}@example.com")
        calls = []
        model_admin = event_admin()

        with patch.object(model_admin, "save_related", recording(model_admin.save_related, calls)):
            data = await call(handle_create, "event", {"data": event_data(speakers=[speaker.pk])}, request)

        assert data.get("success") is True, data
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert kwargs.get("change", args[-1]) is False
        # save_related is what saves many-to-many data
        assert data["object"]["speakers"] == [speaker.pk]

    async def test_update_calls_save_related_with_the_inline_formsets(self):
        request = await superuser_request()
        event, _ = await make_event()
        calls = []
        model_admin = event_admin()

        with patch.object(model_admin, "save_related", recording(model_admin.save_related, calls)):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {},
                    "inlines": {"eventsession": [{"data": {"title": "A", "starts_at": START}}]},
                },
                request,
            )

        assert data.get("success") is True, data
        assert len(calls) == 1
        args, _kwargs = calls[0]
        formsets = args[2]
        assert [formset.model for formset in formsets] == [EventSession]
        assert await session_titles(event.pk) == ["A"]

    async def test_bulk_create_and_update_call_save_related(self):
        request = await superuser_request()
        event, _ = await make_event()
        calls = []
        model_admin = event_admin()

        with patch.object(model_admin, "save_related", recording(model_admin.save_related, calls)):
            created = await call(handle_bulk, "event", {"operation": "create", "items": [event_data()]}, request)
            updated = await call(
                handle_bulk,
                "event",
                {"operation": "update", "items": [{"id": event.pk, "data": {"capacity": 9}}]},
                request,
            )

        assert created["success_count"] == 1, created
        assert updated["success_count"] == 1, updated
        assert len(calls) == 2

    async def test_inline_rows_are_saved_through_save_formset(self):
        request = await superuser_request()
        event, (existing, doomed) = await make_event(sessions=2)
        model_admin = event_admin()

        def stamping_save_formset(request, form, formset, change):
            for instance in formset.save(commit=False):
                instance.notes = {"by": request.user.username}
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
            formset.save_m2m()

        with patch.object(model_admin, "save_formset", stamping_save_formset):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {},
                    "inlines": {
                        "eventsession": [
                            {"id": existing.pk, "data": {"title": "Renamed"}},
                            {"data": {"title": "New", "starts_at": START}},
                            {"id": doomed.pk, "_delete": True},
                        ]
                    },
                },
                request,
            )

        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        assert data["inlines"]["updated"] == [{"model": "eventsession", "id": existing.pk}]
        assert data["inlines"]["deleted"] == [{"model": "eventsession", "id": doomed.pk}]
        assert len(data["inlines"]["created"]) == 1
        stamp = {"by": request.user.username}
        rows = await sync_to_async(lambda: {s.title: s.notes for s in EventSession.objects.filter(event=event)})()
        assert rows == {"Renamed": stamp, "New": stamp}


@pytest.mark.asyncio
@pytest.mark.django_db
class TestParentAndInlinesAreOneTransaction:
    async def test_invalid_inline_row_rolls_back_everything(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update,
            "event",
            {
                "id": event.pk,
                "data": {"name": "Changed"},
                "inlines": {
                    "eventsession": [
                        {"data": {"title": "Good", "starts_at": START, "seats": 5}},
                        {"data": {"title": "Bad", "starts_at": START, "seats": -1}},
                    ]
                },
            },
            request,
        )

        assert "success" not in data, data
        assert data["code"] == "inline_error"
        assert "error" in data
        errors = data["inlines"]["errors"]
        assert len(errors) == 1
        assert errors[0]["model"] == "eventsession"
        assert errors[0]["index"] == 1
        assert errors[0]["validation_errors"]["fields_with_errors"] == ["seats"]
        assert await session_titles(event.pk) == []
        assert (await reload(event)).name == event.name

    async def test_inline_permission_error_rolls_back_everything(self):
        request = await request_with_perms("view_event", "change_event", "add_eventsession", "view_eventsession")
        event, (row,) = await make_event(sessions=1)

        data = await call(
            handle_update,
            "event",
            {
                "id": event.pk,
                "data": {"name": "Changed"},
                "inlines": {
                    "eventsession": [
                        {"data": {"title": "Added", "starts_at": START}},
                        {"id": row.pk, "_delete": True},
                    ]
                },
            },
            request,
        )

        assert "success" not in data, data
        assert data["code"] == "inline_error"
        assert [e["code"] for e in data["inlines"]["errors"]] == ["permission_denied"]
        assert await session_titles(event.pk) == ["S0"]
        assert (await reload(event)).name == event.name

    async def test_max_num_violation_rolls_back_the_parent_change(self):
        request = await superuser_request()
        event, _ = await make_event(sessions=1)
        inline_class = event_admin().inlines[0]

        with patch.object(inline_class, "max_num", 1):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {"name": "Changed"},
                    "inlines": {"eventsession": [{"data": {"title": "Extra", "starts_at": START}}]},
                },
                request,
            )

        assert "success" not in data, data
        assert [e["code"] for e in data["inlines"]["errors"]] == ["max_num_exceeded"]
        assert (await reload(event)).name == event.name

    async def test_failure_while_saving_inlines_rolls_back_the_parent(self):
        request = await superuser_request()
        event, _ = await make_event()
        model_admin = event_admin()

        def exploding_save_formset(request, form, formset, change):
            formset.save()
            raise RuntimeError("boom")

        with patch.object(model_admin, "save_formset", exploding_save_formset):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {"name": "Changed"},
                    "inlines": {"eventsession": [{"data": {"title": "A", "starts_at": START}}]},
                },
                request,
            )

        assert "error" in data and "success" not in data, data
        assert await session_titles(event.pk) == []
        assert (await reload(event)).name == event.name

    async def test_unknown_inline_name_is_an_error(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update,
            "event",
            {"id": event.pk, "data": {"name": "Changed"}, "inlines": {"nosuchinline": [{"data": {"x": 1}}]}},
            request,
        )

        assert "success" not in data, data
        assert data["inlines"]["errors"][0]["code"] == "unknown_inline"
        assert (await reload(event)).name == event.name

    async def test_unknown_inline_field_rolls_back_the_other_rows(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update,
            "event",
            {
                "id": event.pk,
                "data": {},
                "inlines": {
                    "eventsession": [
                        {"data": {"title": "Good", "starts_at": START}},
                        {"data": {"title": "Bad", "starts_at": START, "bogus": 1}},
                    ]
                },
            },
            request,
        )

        assert "success" not in data, data
        assert "bogus" in data["inlines"]["errors"][0]["error"]
        assert await session_titles(event.pk) == []

    async def test_explicitly_requested_row_of_defaults_is_validated(self):
        """A row the caller asked for is never skipped as an 'empty extra form'."""
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update, "event", {"id": event.pk, "data": {}, "inlines": {"eventsession": [{"data": {}}]}}, request
        )

        assert "success" not in data, data
        assert "title" in data["inlines"]["errors"][0]["validation_errors"]["fields_with_errors"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCreateAcceptsInlines:
    async def test_create_with_inlines_creates_the_rows(self):
        request = await superuser_request()

        data = await call(
            handle_create,
            "event",
            {
                "data": event_data(),
                "inlines": {
                    "eventsession": [
                        {"data": {"title": "One", "starts_at": START}},
                        {"data": {"title": "Two", "starts_at": START, "seats": 3}},
                    ]
                },
            },
            request,
        )

        assert data.get("success") is True, data
        assert data["inlines"]["errors"] == []
        assert len(data["inlines"]["created"]) == 2
        assert await session_titles(data["id"]) == ["One", "Two"]

    async def test_create_with_invalid_inline_creates_nothing(self):
        request = await superuser_request()
        payload = event_data()
        title = f"One {unique_id()}"

        data = await call(
            handle_create,
            "event",
            {
                "data": payload,
                "inlines": {
                    "eventsession": [
                        {"data": {"title": title, "starts_at": START}},
                        {"data": {"title": "Two", "starts_at": "not a date"}},
                    ]
                },
            },
            request,
        )

        assert "success" not in data, data
        assert data["code"] == "inline_error"
        assert data["inlines"]["errors"][0]["index"] == 1
        assert not await sync_to_async(Event.objects.filter(slug=payload["slug"]).exists)()
        assert not await sync_to_async(EventSession.objects.filter(title=title).exists)()

    async def test_create_cannot_reference_existing_inline_rows(self):
        request = await superuser_request()
        _, (row,) = await make_event(sessions=1)
        payload = event_data()

        data = await call(
            handle_create,
            "event",
            {"data": payload, "inlines": {"eventsession": [{"id": row.pk, "data": {"title": "Stolen"}}]}},
            request,
        )

        assert data["inlines"]["errors"][0]["code"] == "not_found", data
        assert not await sync_to_async(Event.objects.filter(slug=payload["slug"]).exists)()


def test_tool_schemas_document_inlines_and_datetimes():
    tools = {tool.name: tool for tool in get_model_tools(Event)}
    create, update = tools["create_event"], tools["update_event"]

    assert "inlines" in create.inputSchema["properties"]
    assert "inlines" in update.inputSchema["properties"]
    for tool in (create, update):
        assert "ISO 8601" in tool.description


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDynamicReadonlyFields:
    @pytest.fixture
    def capacity_locked(self):
        model_admin = event_admin()
        seen = []

        def get_readonly_fields(request, obj=None):
            seen.append(obj)
            return ["capacity"]

        with patch.object(model_admin, "get_readonly_fields", get_readonly_fields):
            yield seen

    async def test_update_rejects_a_dynamically_readonly_field(self, capacity_locked):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(handle_update, "event", {"id": event.pk, "data": {"capacity": 99, "name": "N"}}, request)

        assert "success" not in data, data
        assert data["readonly_fields"] == ["capacity"]
        assert "readonly" in data["error"].lower()
        assert (await reload(event)).name == event.name
        assert event in capacity_locked

    async def test_create_rejects_a_dynamically_readonly_field(self, capacity_locked):
        request = await superuser_request()
        payload = event_data(capacity=99)

        data = await call(handle_create, "event", {"data": payload}, request)

        assert "success" not in data, data
        assert data["readonly_fields"] == ["capacity"]
        assert not await sync_to_async(Event.objects.filter(slug=payload["slug"]).exists)()

    async def test_bulk_rejects_a_dynamically_readonly_field(self, capacity_locked):
        request = await superuser_request()
        event, _ = await make_event()

        created = await call(handle_bulk, "event", {"operation": "create", "items": [event_data(capacity=99)]}, request)
        updated = await call(
            handle_bulk,
            "event",
            {"operation": "update", "items": [{"id": event.pk, "data": {"capacity": 99}}]},
            request,
        )

        for data in (created, updated):
            assert data["success_count"] == 0, data
            assert data["results"]["errors"][0]["readonly_fields"] == ["capacity"]

    async def test_inline_rejects_a_dynamically_readonly_field(self):
        request = await superuser_request()
        event, (row,) = await make_event(sessions=1)
        inline_class = event_admin().inlines[0]

        def get_readonly_fields(self, request, obj=None):
            return ["seats"]

        with patch.object(inline_class, "get_readonly_fields", get_readonly_fields):
            data = await call(
                handle_update,
                "event",
                {"id": event.pk, "data": {}, "inlines": {"eventsession": [{"id": row.pk, "data": {"seats": 1}}]}},
                request,
            )

        assert "success" not in data, data
        assert data["inlines"]["errors"][0]["readonly_fields"] == ["seats"]
        assert (await reload(row)).seats == 10


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUnconsumedKeysAreRejected:
    async def test_create_rejects_an_unknown_key(self):
        request = await superuser_request()
        payload = event_data(bogus=1)

        data = await call(handle_create, "event", {"data": payload}, request)

        assert "success" not in data, data
        assert data["error"] == "Invalid field: bogus"
        assert data["invalid_fields"] == ["bogus"]
        assert not await sync_to_async(Event.objects.filter(slug=payload["slug"]).exists)()

    async def test_non_editable_field_is_rejected(self, product_admin):
        request = await superuser_request()
        product = await sync_to_async(Product.objects.create)(name="P")
        name = f"X {unique_id()}"

        created = await call(handle_create, "product", {"data": {"name": name, "internal_code": "abc"}}, request)
        updated = await call(handle_update, "product", {"id": product.pk, "data": {"internal_code": "abc"}}, request)

        for data in (created, updated):
            assert "success" not in data, data
            assert data["invalid_fields"] == ["internal_code"]
        assert not await sync_to_async(Product.objects.filter(name=name).exists)()
        assert (await reload(product)).internal_code == ""

    async def test_field_excluded_from_the_form_is_rejected(self, product_admin):
        request = await superuser_request()
        product = await sync_to_async(Product.objects.create)(name="P")

        created = await call(handle_create, "product", {"data": {"name": "X", "cost": "3.00"}}, request)
        updated = await call(handle_update, "product", {"id": product.pk, "data": {"cost": "3.00"}}, request)

        for data in (created, updated):
            assert "success" not in data, data
            assert data["invalid_fields"] == ["cost"]

    async def test_bulk_rejects_unconsumed_keys_per_item(self, product_admin):
        request = await superuser_request()
        product = await sync_to_async(Product.objects.create)(name="P")

        created = await call(
            handle_bulk,
            "product",
            {"operation": "create", "items": [{"name": "Ok"}, {"name": "X", "bogus": 1}, {"name": "Y", "cost": "1"}]},
            request,
        )
        updated = await call(
            handle_bulk,
            "product",
            {"operation": "update", "items": [{"id": product.pk, "data": {"internal_code": "abc"}}]},
            request,
        )

        assert created["success_count"] == 1, created
        errors = created["results"]["errors"]
        assert [(e["index"], e["invalid_fields"]) for e in errors] == [(1, ["bogus"]), (2, ["cost"])]
        assert updated["success_count"] == 0, updated
        assert updated["results"]["errors"][0]["invalid_fields"] == ["internal_code"]

    async def test_bulk_update_rejects_unknown_item_keys(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_bulk,
            "event",
            {
                "operation": "update",
                "items": [{"id": event.pk, "data": {"capacity": 3}, "inlines": {"eventsession": []}}],
            },
            request,
        )

        assert data["success_count"] == 0, data
        assert "inlines" in data["results"]["errors"][0]["error"]
        assert (await reload(event)).capacity == 0

    async def test_fk_id_alias_is_accepted_on_create_and_update(self):
        request = await superuser_request()
        uid = unique_id()
        first = await sync_to_async(Author.objects.create)(name="A", email=f"a_{uid}@example.com")
        second = await sync_to_async(Author.objects.create)(name="B", email=f"b_{uid}@example.com")

        created = await call(
            handle_create, "article", {"data": {"title": "T", "content": "c", "author_id": first.pk}}, request
        )
        assert created.get("success") is True, created
        updated = await call(handle_update, "article", {"id": created["id"], "data": {"author_id": second.pk}}, request)

        assert updated.get("success") is True, updated
        article = await sync_to_async(Article.objects.get)(pk=created["id"])
        assert article.author_id == second.pk

    async def test_multiwidget_sub_keys_are_accepted(self):
        request = await superuser_request()
        payload = event_data()
        del payload["starts_at"]
        payload.update({"starts_at_0": "2026-03-01", "starts_at_1": "09:00:00"})

        created = await call(handle_create, "event", {"data": payload}, request)
        assert created.get("success") is True, created
        updated = await call(
            handle_update,
            "event",
            {"id": created["id"], "data": {"ends_at_0": "2026-03-02", "ends_at_1": "10:00:00"}},
            request,
        )

        assert updated.get("success") is True, updated
        event = await sync_to_async(Event.objects.get)(pk=created["id"])
        assert event.ends_at is not None

    async def test_add_form_fields_that_are_not_model_fields_are_accepted(self, user_admin):
        request = await superuser_request()
        username = f"made_{unique_id()}"

        data = await call(
            handle_create,
            "user",
            {"data": {"username": username, "password1": "s3cret-Pass-9", "password2": "s3cret-Pass-9"}},
            request,
        )

        assert data.get("success") is True, data
        user = await sync_to_async(User.objects.get)(username=username)
        assert user.check_password("s3cret-Pass-9")

    async def test_field_the_form_disables_is_rejected(self, user_admin):
        """UserChangeForm.password is a disabled field: the form would ignore the value."""
        request = await superuser_request()
        target = await sync_to_async(User.objects.create_user)(username=f"t_{unique_id()}", password="old-pass")

        data = await call(handle_update, "user", {"id": target.pk, "data": {"password": "new-pass"}}, request)

        assert "success" not in data, data
        assert data["invalid_fields"] == ["password"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkMessages:
    async def test_bulk_returns_queued_messages(self):
        request = await superuser_request()
        model_admin = event_admin()
        original = model_admin.save_model

        def chatty_save_model(request, obj, form, change):
            original(request, obj, form, change)
            model_admin.message_user(request, f"saved {obj.name}", messages.INFO)

        payload = event_data()
        with patch.object(model_admin, "save_model", chatty_save_model):
            data = await call(handle_bulk, "event", {"operation": "create", "items": [payload]}, request)

        assert data["success_count"] == 1, data
        assert data["messages"] == [{"level": "info", "message": f"saved {payload['name']}"}]

    async def test_bulk_without_messages_omits_the_key(self):
        request = await superuser_request()

        data = await call(handle_bulk, "event", {"operation": "create", "items": [event_data()]}, request)

        assert data["success_count"] == 1, data
        assert "messages" not in data

    async def test_bulk_mcptoken_create_returns_no_token_material(self):
        request = await superuser_request()
        name = f"bulk tok {unique_id()}"

        result = await handle_bulk(
            "mcptoken",
            {"operation": "create", "items": [{"name": name, "user": request.user.pk, "is_active": True}]},
            request,
        )
        text = result[0].text
        data = json.loads(text)

        assert data["success_count"] == 1, data
        assert "messages" not in data
        token = await sync_to_async(MCPToken.objects.get)(name=name)
        assert token.token_key not in text
        assert "mcp_" not in text


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineOperationShape:
    """Malformed inline input is an error, never a silently skipped row."""

    async def _errors(self, inlines, sessions=1):
        request = await superuser_request()
        event, rows = await make_event(sessions=sessions)
        if callable(inlines):
            inlines = inlines(event, rows)
        data = await call(
            handle_update, "event", {"id": event.pk, "data": {"name": "Changed"}, "inlines": inlines}, request
        )
        assert "success" not in data, data
        assert data["code"] == "inline_error"
        assert (await reload(event)).name == event.name
        assert await session_titles(event.pk) == [row.title for row in rows]
        return data["inlines"]["errors"]

    async def test_inlines_must_be_an_object(self):
        errors = await self._errors([{"title": "x"}])
        assert "must be an object" in errors[0]["error"]

    async def test_operations_must_be_a_list(self):
        errors = await self._errors({"eventsession": {"title": "x"}})
        assert errors[0]["error"] == "Inline operations must be a list"

    async def test_operation_must_be_an_object(self):
        errors = await self._errors({"eventsession": ["x"]})
        assert errors[0]["index"] == 0

    async def test_stray_operation_key_is_rejected(self):
        errors = await self._errors({"eventsession": [{"data": {"title": "T", "starts_at": START}, "delete": True}]})
        assert errors[0]["error"] == "Invalid key: delete"

    async def test_delete_needs_an_id(self):
        errors = await self._errors({"eventsession": [{"_delete": True}]})
        assert errors[0]["error"] == "id is required to delete"

    async def test_delete_cannot_carry_data(self):
        errors = await self._errors(
            lambda e, rows: {"eventsession": [{"id": rows[0].pk, "_delete": True, "title": "x"}]}
        )
        assert errors[0]["error"] == "Cannot combine _delete with data"

    async def test_same_row_twice_is_rejected(self):
        errors = await self._errors(
            lambda e, rows: {
                "eventsession": [
                    {"id": rows[0].pk, "data": {"title": "A"}},
                    {"id": rows[0].pk, "data": {"title": "B"}},
                ]
            }
        )
        assert errors[0]["index"] == 1
        assert "Duplicate" in errors[0]["error"]

    async def test_id_of_the_wrong_type_is_not_found(self):
        errors = await self._errors({"eventsession": [{"id": "not-a-number", "data": {"title": "A"}}]})
        assert errors[0]["code"] == "not_found"

    async def test_formset_bookkeeping_keys_cannot_be_supplied(self):
        """A caller-supplied DELETE would delete the row without the delete permission check."""
        errors = await self._errors(lambda e, rows: {"eventsession": [{"id": rows[0].pk, "data": {"DELETE": True}}]})
        assert errors[0]["invalid_fields"] == ["DELETE"]

    async def test_parent_fk_must_match_the_parent(self):
        other, _ = await make_event()
        errors = await self._errors(
            {"eventsession": [{"data": {"title": "T", "starts_at": START, "event_id": other.pk}}]}
        )
        assert errors[0]["validation_errors"]["fields_with_errors"] == ["event"]

    async def test_inline_that_forbids_deletion(self):
        inline_class = event_admin().inlines[0]
        with patch.object(inline_class, "can_delete", False):
            errors = await self._errors(lambda e, rows: {"eventsession": [{"id": rows[0].pk, "_delete": True}]})
        assert errors[0]["code"] == "permission_denied"

    async def test_parent_fk_alias_matching_the_parent_is_accepted(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update,
            "event",
            {
                "id": event.pk,
                "data": {},
                "inlines": {"eventsession": [{"data": {"title": "T", "starts_at": START, "event_id": event.pk}}]},
            },
            request,
        )

        assert data.get("success") is True, data
        assert await session_titles(event.pk) == ["T"]

    async def test_empty_operation_list_is_a_no_op(self):
        request = await superuser_request()
        event, _ = await make_event()

        data = await call(
            handle_update, "event", {"id": event.pk, "data": {}, "inlines": {"eventsession": []}}, request
        )

        assert data.get("success") is True, data
        assert data["inlines"] is None

    async def test_request_without_a_user_uses_the_declared_inline_configuration(self):
        """Without a user get_formset() cannot run; the fallback formset still saves through the hooks."""
        event, (row,) = await make_event(sessions=1)
        calls = []
        model_admin = event_admin()

        with patch.object(model_admin, "save_formset", recording(model_admin.save_formset, calls)):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {},
                    "inlines": {
                        "eventsession": [
                            {"id": row.pk, "data": {"title": "Renamed"}},
                            {"data": {"title": "New", "starts_at": START}},
                        ]
                    },
                },
                create_mock_request(),
            )

        assert data.get("success") is True, data
        assert len(calls) == 1
        assert await session_titles(event.pk) == ["New", "Renamed"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestWriteInputShape:
    async def test_data_must_be_an_object(self):
        request = await superuser_request()

        data = await call(handle_create, "event", {"data": ["name"]}, request)

        assert data == {"error": "data must be an object"}

    async def test_readonly_error_wording_differs_between_create_and_update(self):
        request = await superuser_request()
        event, _ = await make_event()
        model_admin = event_admin()

        with patch.object(model_admin, "get_readonly_fields", lambda request, obj=None: ["capacity"]):
            created = await call(handle_create, "event", {"data": event_data(capacity=1)}, request)
            updated = await call(handle_update, "event", {"id": event.pk, "data": {"capacity": 1}}, request)

        assert created["error"] == "Cannot set readonly fields: capacity"
        assert updated["error"] == "Cannot update readonly fields: capacity"


@pytest.mark.django_db
class TestSaveThroughAdminSync:
    """
    The pipeline itself, called synchronously.

    The handler tests above are async and skipped on Django < 4.2; these keep
    the formset synthesis covered on every supported Django version.
    """

    @staticmethod
    def _request():
        uid = unique_id()
        user = User.objects.create_superuser(username=f"wp_sync_{uid}", email=f"s_{uid}@example.com", password="x")
        return create_mock_request(user)

    def test_create_with_inlines(self):
        request = self._request()

        event, inlines = save_through_admin(
            Event,
            event_admin(),
            request,
            event_data(),
            inlines={"eventsession": [{"data": {"title": "One", "starts_at": START}}]},
        )

        session = EventSession.objects.get(event=event)
        assert session.title == "One"
        assert session.seats == 10
        assert inlines == {
            "created": [{"model": "eventsession", "id": session.pk}],
            "updated": [],
            "deleted": [],
            "errors": [],
        }

    def test_update_adds_changes_and_deletes_rows(self):
        request = self._request()
        event = Event.objects.get(pk=Event.objects.create(name="E", slug=f"e-{unique_id()}", starts_at=START).pk)
        kept = EventSession.objects.create(event=event, title="Kept", starts_at=START, seats=7)
        doomed = EventSession.objects.create(event=event, title="Doomed", starts_at=START)
        untouched = EventSession.objects.create(event=event, title="Untouched", starts_at=START)

        _, inlines = save_through_admin(
            Event,
            event_admin(),
            request,
            {"capacity": 12},
            obj=event,
            inlines={
                "eventsession": [
                    {"data": {"title": "New", "starts_at": START}},
                    {"id": kept.pk, "data": {"title": "Renamed"}},
                    {"id": doomed.pk, "_delete": True},
                ]
            },
        )

        assert Event.objects.get(pk=event.pk).capacity == 12
        assert sorted(EventSession.objects.filter(event=event).values_list("title", "seats")) == [
            ("New", 10),
            ("Renamed", 7),
            ("Untouched", 10),
        ]
        assert inlines["updated"] == [{"model": "eventsession", "id": kept.pk}]
        assert inlines["deleted"] == [{"model": "eventsession", "id": doomed.pk}]
        assert len(inlines["created"]) == 1
        assert EventSession.objects.filter(pk=untouched.pk).exists()

    def test_inline_error_rejects_the_write_before_anything_is_saved(self):
        request = self._request()
        event = Event.objects.get(pk=Event.objects.create(name="E", slug=f"e-{unique_id()}", starts_at=START).pk)
        model_admin = event_admin()

        with patch.object(model_admin, "save_model") as save_model:
            with pytest.raises(WriteRejected) as rejected:
                save_through_admin(
                    Event,
                    model_admin,
                    request,
                    {"capacity": 12},
                    obj=event,
                    inlines={"eventsession": [{"data": {"title": "Bad", "starts_at": START, "seats": -1}}]},
                )

        save_model.assert_not_called()
        assert rejected.value.payload["code"] == "inline_error"
        assert rejected.value.payload["inlines"]["errors"][0]["validation_errors"]["fields_with_errors"] == ["seats"]

    def test_inlines_without_a_model_admin_are_rejected(self):
        with pytest.raises(WriteRejected) as rejected:
            save_through_admin(
                Author,
                None,
                create_mock_request(),
                {"name": "N", "email": f"n_{unique_id()}@example.com"},
                inlines={"article": [{"data": {"title": "T", "content": "c"}}]},
            )

        assert "ModelAdmin" in rejected.value.payload["error"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestFileFields:
    """A file field reads uploads, which MCP cannot send: its name is not a consumed key."""

    async def test_file_field_value_is_rejected_instead_of_ignored(self):
        request = await superuser_request()
        event, _ = await make_event()

        created = await call(handle_create, "event", {"data": event_data(brochure="brochures/x.pdf")}, request)
        updated = await call(handle_update, "event", {"id": event.pk, "data": {"brochure": "brochures/x.pdf"}}, request)

        for data in (created, updated):
            assert "success" not in data, data
            assert data["invalid_fields"] == ["brochure"]

    async def test_file_field_can_be_cleared_through_the_widget_key(self):
        request = await superuser_request()
        event, _ = await make_event()
        await sync_to_async(Event.objects.filter(pk=event.pk).update)(brochure="brochures/old.pdf")

        data = await call(handle_update, "event", {"id": event.pk, "data": {"brochure-clear": True}}, request)

        assert data.get("success") is True, data
        assert not (await reload(event)).brochure


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineFormsetValidation:
    async def test_custom_formset_clean_runs_and_rejects_the_write(self):
        """The inline's own formset class validates across rows, as in the admin."""

        class NoDuplicateTitles(BaseInlineFormSet):
            def clean(self):
                super().clean()
                titles = [form.cleaned_data.get("title") for form in self.forms if hasattr(form, "cleaned_data")]
                if len(titles) != len(set(titles)):
                    raise ValidationError("Session titles must be unique")

        request = await superuser_request()
        event, _ = await make_event()
        inline_class = event_admin().inlines[0]

        with patch.object(inline_class, "formset", NoDuplicateTitles):
            data = await call(
                handle_update,
                "event",
                {
                    "id": event.pk,
                    "data": {"name": "Changed"},
                    "inlines": {
                        "eventsession": [
                            {"data": {"title": "Same", "starts_at": START}},
                            {"data": {"title": "Same", "starts_at": START}},
                        ]
                    },
                },
                request,
            )

        assert "success" not in data, data
        error = data["inlines"]["errors"][0]
        assert error["id"] is None and "index" not in error
        assert error["validation_errors"]["errors"] == [
            {"field": "__all__", "messages": ["Session titles must be unique"]}
        ]
        assert await session_titles(event.pk) == []
        assert (await reload(event)).name == event.name
