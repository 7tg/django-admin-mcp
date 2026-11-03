"""
Tests for models that use third-party field and relation machinery.

Covers:
- a field whose Python value is not JSON-serializable (django-markitup's
  ``Markup``) is serialized with the field's own ``value_to_string()``, so
  get_* / list_* return it instead of failing
- a partial update keeps such a field's stored value instead of saving the
  ``str()`` of its value object (for ``Markup``, the rendered HTML)
- an ``on_delete`` wrapped in a callable object without ``__name__``
  (django-polymorphic's ``PolymorphicGuard``) does not fail describe_*
- get_* finds inline rows whose FK points at a multi-table parent of the
  object's model, as Django's inline formsets do
"""

import contextlib
import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.auth.models import User

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import (
    create_mock_request,
    handle_describe,
    handle_get,
    handle_list,
    handle_update,
    serialize_instance,
)
from tests.models import Author, Booklet, DocumentPage, MarkedUp, Memo


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


class MemoAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True


class DocumentPageInline(admin.TabularInline):
    model = DocumentPage
    extra = 0


class BookletAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    inlines = [DocumentPageInline]


@contextlib.contextmanager
def registered_admin(admin_class, model):
    """Temporarily register ``admin_class`` as the MCP admin for ``model``."""
    registry = MCPAdminMixin._registered_models
    model_name = model._meta.model_name
    previous = registry.pop(model_name, None)
    model_admin = admin_class(model, admin.site)
    registry[model_name] = {"model": model, "admin": model_admin}
    try:
        yield model_admin
    finally:
        if previous is None:
            registry.pop(model_name, None)
        else:
            registry[model_name] = previous


async def superuser_request():
    uid = unique_id()
    user = await sync_to_async(User.objects.create_superuser)(
        username=f"admin_{uid}", email=f"admin_{uid}@example.com", password="pw"
    )
    return create_mock_request(user)


def make_memo(body="Some *marked up* text"):
    uid = unique_id()
    author = Author.objects.create(name=f"Author {uid}", email=f"author_{uid}@example.com")
    return Memo.objects.create(body=MarkedUp(body), author=author)


def make_booklet():
    booklet = Booklet.objects.create(title=f"Booklet {unique_id()}", file="documents/booklet.pdf", edition="2nd")
    DocumentPage.objects.create(document=booklet, label="Cover", scan="pages/cover.png")
    DocumentPage.objects.create(document=booklet, label="Back", scan="pages/back.png")
    return booklet


@pytest.mark.django_db
class TestCustomFieldValues:
    """Values of custom field types go through the field's value_to_string()."""

    def test_serialize_instance_uses_value_to_string(self):
        memo = Memo.objects.get(pk=make_memo().pk)
        result = serialize_instance(memo, MemoAdmin(Memo, admin.site))
        assert result["body"] == "Some *marked up* text"
        json.dumps(result)

    @pytest.mark.asyncio
    async def test_get_returns_custom_value(self):
        memo = await sync_to_async(make_memo)()
        with registered_admin(MemoAdmin, Memo):
            result = await handle_get("memo", {"id": memo.pk}, await superuser_request())
        data = json.loads(result[0].text)
        assert data["body"] == "Some *marked up* text"
        assert data["author"] == memo.author_id

    @pytest.mark.asyncio
    async def test_list_returns_custom_value(self):
        memo = await sync_to_async(make_memo)("Listed")
        with registered_admin(MemoAdmin, Memo):
            result = await handle_list("memo", {}, await superuser_request())
        data = json.loads(result[0].text)
        rows = {row["id"]: row for row in data["results"]}
        assert rows[memo.pk]["body"] == "Listed"

    @pytest.mark.asyncio
    async def test_update_keeps_omitted_custom_value(self):
        memo = await sync_to_async(make_memo)("Keep *me*")
        other = await sync_to_async(Author.objects.create)(name="Other", email=f"other_{unique_id()}@example.com")
        with registered_admin(MemoAdmin, Memo):
            result = await handle_update(
                "memo", {"id": memo.pk, "data": {"author": other.pk}}, await superuser_request()
            )
        data = json.loads(result[0].text)
        assert "error" not in data, data
        memo = await sync_to_async(Memo.objects.get)(pk=memo.pk)
        assert memo.body.raw == "Keep *me*"
        assert memo.author_id == other.pk

    @pytest.mark.asyncio
    async def test_update_sets_sent_custom_value(self):
        memo = await sync_to_async(make_memo)("Old")
        with registered_admin(MemoAdmin, Memo):
            result = await handle_update("memo", {"id": memo.pk, "data": {"body": "New"}}, await superuser_request())
        data = json.loads(result[0].text)
        assert data["object"]["body"] == "New"
        memo = await sync_to_async(Memo.objects.get)(pk=memo.pk)
        assert memo.body.raw == "New"


@pytest.mark.django_db
class TestWrappedOnDelete:
    """describe_* reports the wrapped on_delete handler."""

    @pytest.mark.asyncio
    async def test_describe_reports_wrapped_on_delete(self):
        with registered_admin(MemoAdmin, Memo):
            result = await handle_describe("memo", {}, await superuser_request())
        data = json.loads(result[0].text)
        relationships = {field["name"]: field for field in data["relationships"]}
        assert relationships["author"]["on_delete"] == "SET_NULL"


@pytest.mark.django_db
class TestParentModelInlines:
    """Inline rows whose FK points at a multi-table parent of the object's model."""

    @pytest.mark.asyncio
    async def test_get_includes_inline_rows_on_parent_fk(self):
        booklet = await sync_to_async(make_booklet)()
        with registered_admin(BookletAdmin, Booklet):
            result = await handle_get("booklet", {"id": booklet.pk, "include_inlines": True}, await superuser_request())
        data = json.loads(result[0].text)
        labels = sorted(row["label"] for row in data["_inlines"]["documentpage"])
        assert labels == ["Back", "Cover"]
