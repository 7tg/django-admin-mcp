"""
Tests for InlineModelAdmin min_num / max_num enforcement in inline editing.

Covers issues #61 (max_num) and #62 (min_num).
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
def inline_constraints(min_num=None, max_num=None):
    """Temporarily set min_num/max_num on the Author admin's article inline."""
    _, author_admin = get_model_admin("author")
    inline_class = author_admin.inlines[0]
    original_min = getattr(inline_class, "min_num", None)
    original_max = getattr(inline_class, "max_num", None)
    inline_class.min_num = min_num
    inline_class.max_num = max_num
    try:
        yield inline_class
    finally:
        inline_class.min_num = original_min
        inline_class.max_num = original_max


@sync_to_async
def create_author_with_articles(uid, article_count):
    author = Author.objects.create(name=f"Inline Author {uid}", email=f"inline_{uid}@example.com")
    articles = [
        Article.objects.create(title=f"Article {i} {uid}", content="content", author=author)
        for i in range(article_count)
    ]
    return author, articles


@sync_to_async
def create_superuser_request(uid):
    user = User.objects.create_superuser(
        username=f"inline_admin_{uid}",
        email=f"inline_admin_{uid}@example.com",
        password="admin",
    )
    return create_mock_request(user)


@sync_to_async
def count_articles(author):
    return Article.objects.filter(author=author).count()


@pytest.mark.asyncio
@pytest.mark.django_db
class TestMaxNumEnforcement:
    """max_num must cap the number of inline objects (issue #61)."""

    async def test_addition_exceeding_max_num_is_rejected(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 2)
        request = await create_superuser_request(uid)

        with inline_constraints(max_num=2):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"data": {"title": f"Extra {uid}", "content": "c"}}]},
                },
                request,
            )

        data = json.loads(result[0].text)
        errors = (data.get("inlines") or {}).get("errors", [])
        assert any(e.get("code") == "max_num_exceeded" for e in errors), data
        assert await count_articles(author) == 2  # nothing was created

    async def test_addition_within_max_num_is_allowed(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 2)
        request = await create_superuser_request(uid)

        with inline_constraints(max_num=3):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"data": {"title": f"Extra {uid}", "content": "c"}}]},
                },
                request,
            )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert await count_articles(author) == 3

    async def test_no_max_num_allows_unlimited(self):
        uid = unique_id()
        author, _ = await create_author_with_articles(uid, 2)
        request = await create_superuser_request(uid)

        with inline_constraints(max_num=None):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"data": {"title": f"Extra {uid}", "content": "c"}}]},
                },
                request,
            )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert await count_articles(author) == 3


@pytest.mark.asyncio
@pytest.mark.django_db
class TestMinNumEnforcement:
    """min_num must keep a floor on the number of inline objects (issue #62)."""

    async def test_deletion_below_min_num_is_rejected(self):
        uid = unique_id()
        author, articles = await create_author_with_articles(uid, 2)
        request = await create_superuser_request(uid)

        with inline_constraints(min_num=2):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"id": articles[0].pk, "_delete": True}]},
                },
                request,
            )

        data = json.loads(result[0].text)
        errors = (data.get("inlines") or {}).get("errors", [])
        assert any(e.get("code") == "min_num_violated" for e in errors), data
        assert await count_articles(author) == 2  # nothing was deleted

    async def test_deletion_above_min_num_is_allowed(self):
        uid = unique_id()
        author, articles = await create_author_with_articles(uid, 3)
        request = await create_superuser_request(uid)

        with inline_constraints(min_num=2):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {"article": [{"id": articles[0].pk, "_delete": True}]},
                },
                request,
            )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        assert await count_articles(author) == 2

    async def test_delete_and_add_composes_for_constraint_check(self):
        """Deleting one and adding one keeps the count stable — allowed at the floor."""
        uid = unique_id()
        author, articles = await create_author_with_articles(uid, 2)
        request = await create_superuser_request(uid)

        with inline_constraints(min_num=2, max_num=2):
            result = await handle_update(
                "author",
                {
                    "id": author.pk,
                    "data": {},
                    "inlines": {
                        "article": [
                            {"id": articles[0].pk, "_delete": True},
                            {"data": {"title": f"Replacement {uid}", "content": "c"}},
                        ]
                    },
                },
                request,
            )

        data = json.loads(result[0].text)
        assert data.get("success") is True, data
        errors = (data.get("inlines") or {}).get("errors", [])
        assert not errors, data
        assert await count_articles(author) == 2
