"""
Tests for issue #105: inline create/update must honor the inline admin's
fields, exclude, and readonly_fields — the inline counterpart of the
top-level update guards.
"""

import json
import uuid
from contextlib import contextmanager

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_update
from django_admin_mcp.handlers.base import get_model_admin
from tests.models import Article, Author


def unique_id():
    return uuid.uuid4().hex[:8]


@contextmanager
def inline_field_config(fields=None, readonly_fields=None, exclude=None):
    """Temporarily configure the Author admin's article inline."""
    _, author_admin = get_model_admin("author")
    inline_class = author_admin.inlines[0]
    originals = {
        "fields": getattr(inline_class, "fields", None),
        "readonly_fields": getattr(inline_class, "readonly_fields", ()),
        "exclude": getattr(inline_class, "exclude", None),
    }
    inline_class.fields = fields
    inline_class.readonly_fields = readonly_fields or ()
    inline_class.exclude = exclude
    try:
        yield inline_class
    finally:
        for name, value in originals.items():
            setattr(inline_class, name, value)


@sync_to_async
def make_fixture(uid):
    author = Author.objects.create(name=f"Inline Author {uid}", email=f"inline_f_{uid}@example.com")
    article = Article.objects.create(
        title=f"Article {uid}", content="original content", author=author, is_published=False
    )
    user = User.objects.create_superuser(
        username=f"inline_fields_{uid}", email=f"inline_fields_{uid}@example.com", password="pw"
    )
    return author, article, user


@sync_to_async
def refresh(obj):
    obj.refresh_from_db()
    return obj


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineFieldRestrictions:
    """Inline writes must respect the inline admin's field configuration."""

    async def test_field_outside_declared_fields_is_rejected(self):
        uid = unique_id()
        author, article, user = await make_fixture(uid)
        request = create_mock_request(user)

        with inline_field_config(fields=["title", "content"]):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"id": article.pk, "data": {"is_published": True}}]},
                },
                request,
            )
        data = json.loads(result[0].text)

        errors = (data.get("inlines") or {}).get("errors", [])
        assert any("is_published" in e.get("error", "") for e in errors), data
        article = await refresh(article)
        assert article.is_published is False

    async def test_readonly_inline_field_is_rejected(self):
        uid = unique_id()
        author, article, user = await make_fixture(uid)
        request = create_mock_request(user)

        with inline_field_config(fields=["title", "content"], readonly_fields=["content"]):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"id": article.pk, "data": {"content": "HACKED"}}]},
                },
                request,
            )
        data = json.loads(result[0].text)

        errors = (data.get("inlines") or {}).get("errors", [])
        assert any("readonly" in e.get("error", "").lower() for e in errors), data
        article = await refresh(article)
        assert article.content == "original content"

    async def test_allowed_inline_field_still_updates(self):
        uid = unique_id()
        author, article, user = await make_fixture(uid)
        request = create_mock_request(user)

        with inline_field_config(fields=["title", "content"], readonly_fields=["content"]):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"id": article.pk, "data": {"title": f"Updated {uid}"}}]},
                },
                request,
            )
        data = json.loads(result[0].text)

        inlines = data.get("inlines") or {}
        assert inlines.get("updated"), data
        article = await refresh(article)
        assert article.title == f"Updated {uid}"

    async def test_inline_create_rejects_undeclared_field(self):
        uid = unique_id()
        author, article, user = await make_fixture(uid)
        request = create_mock_request(user)

        with inline_field_config(fields=["title", "content"]):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"data": {"title": f"New {uid}", "content": "c", "is_published": True}}]},
                },
                request,
            )
        data = json.loads(result[0].text)

        errors = (data.get("inlines") or {}).get("errors", [])
        assert any("is_published" in e.get("error", "") for e in errors), data
        count = await sync_to_async(Article.objects.filter(title=f"New {uid}").count)()
        assert count == 0

    async def test_inline_create_with_declared_fields_succeeds(self):
        uid = unique_id()
        author, article, user = await make_fixture(uid)
        request = create_mock_request(user)

        with inline_field_config(fields=["title", "content"]):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"data": {"title": f"New {uid}", "content": "c"}}]},
                },
                request,
            )
        data = json.loads(result[0].text)

        inlines = data.get("inlines") or {}
        assert inlines.get("created"), data
        created = await sync_to_async(Article.objects.filter(title=f"New {uid}").first)()
        assert created is not None
        assert created.author_id == author.pk
