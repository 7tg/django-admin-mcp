"""
Inline and related object operation tests (issue #46).
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_delete,
    handle_related,
    handle_update,
)
from django_admin_mcp.handlers.actions import handle_bulk_create, handle_bulk_update
from tests.models import Article, Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_author_with_articles(uid, count=2):
    author = Author.objects.create(name=f"Rel Author {uid}", email=f"rel_{uid}@example.com")
    articles = [
        Article.objects.create(title=f"Rel Article {i} {uid}", content="c", author=author) for i in range(count)
    ]
    return author, articles


@sync_to_async
def superuser_request(uid):
    user = User.objects.create_superuser(
        username=f"rel_admin_{uid}", email=f"rel_admin_{uid}@example.com", password="x"
    )
    return create_mock_request(user)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineOperations:
    async def test_inline_form_validation_errors_are_reported(self):
        """Invalid inline data must surface field-level validation errors."""
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 0)
        request = await superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},
                # Missing required 'content' field on the inline article
                "inlines": {"article": [{"data": {"title": f"No content {uid}"}}]},
            },
            request,
        )
        data = json.loads(result[0].text)
        errors = (data.get("inlines") or {}).get("errors", [])
        assert errors, data
        assert any("validation_errors" in e for e in errors), errors

    async def test_inline_extra_unknown_fields_are_ignored(self):
        """Unknown fields in inline data don't break creation (ModelForm ignores them)."""
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 0)
        request = await superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},
                "inlines": {"article": [{"data": {"title": f"Extra {uid}", "content": "c", "not_a_field": "ignored"}}]},
            },
            request,
        )
        data = json.loads(result[0].text)
        created = (data.get("inlines") or {}).get("created", [])
        assert len(created) == 1, data

    async def test_inline_update_nonexistent_id_is_an_error_entry(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 1)
        request = await superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},
                "inlines": {"article": [{"id": 99999999, "data": {"title": "nope"}}]},
            },
            request,
        )
        data = json.loads(result[0].text)
        errors = (data.get("inlines") or {}).get("errors", [])
        assert errors, data


@pytest.mark.asyncio
@pytest.mark.django_db
class TestRelatedOperations:
    async def test_related_empty_reverse_accessor(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 0)
        request = await superuser_request(uid)

        result = await handle_related("author", {"id": author.pk, "relation": "articles"}, request)
        data = json.loads(result[0].text)
        assert data["count"] == 0
        assert data["results"] == []

    async def test_related_pagination_with_offset(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 3)
        request = await superuser_request(uid)

        result = await handle_related(
            "author", {"id": author.pk, "relation": "articles", "limit": 2, "offset": 2}, request
        )
        data = json.loads(result[0].text)
        assert data["total_count"] == 3
        assert data["count"] == 1


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkWithRelations:
    async def test_bulk_create_with_fk_parent(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 0)
        request = await superuser_request(uid)

        result = await handle_bulk_create(
            "article",
            {
                "items": [
                    {"title": f"Bulk A {uid}", "content": "c", "author": author.pk},
                    {"title": f"Bulk B {uid}", "content": "c", "author": author.pk},
                ]
            },
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 2, data
        assert await sync_to_async(Article.objects.filter(author=author).count)() == 2

    async def test_bulk_update_different_fields_per_item(self):
        uid = unique_id()
        author, articles = await create_author_with_articles(uid, 2)
        request = await superuser_request(uid)

        result = await handle_bulk_update(
            "article",
            {
                "items": [
                    {"id": articles[0].pk, "data": {"title": f"New Title {uid}"}},
                    {"id": articles[1].pk, "data": {"content": f"New Content {uid}"}},
                ]
            },
            request,
        )
        data = json.loads(result[0].text)
        assert data["success_count"] == 2, data

        @sync_to_async
        def refreshed():
            a0 = Article.objects.get(pk=articles[0].pk)
            a1 = Article.objects.get(pk=articles[1].pk)
            return a0, a1

        a0, a1 = await refreshed()
        assert a0.title == f"New Title {uid}"
        assert a0.content == "c"  # untouched field preserved
        assert a1.content == f"New Content {uid}"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDeleteCascade:
    async def test_delete_parent_cascades_to_children(self):
        uid = unique_id()
        author, articles = await create_author_with_articles(uid, 2)
        request = await superuser_request(uid)

        result = await handle_delete("author", {"id": author.pk}, request)
        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert await sync_to_async(Article.objects.filter(pk__in=[a.pk for a in articles]).count)() == 0
