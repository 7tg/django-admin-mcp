"""
Tests for inline permission checking in handle_update
(django_admin_mcp.handlers.inlines).
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_update
from tests.models import Article, Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


class TestInlinePermissions:
    """Tests for inline permission checking in handle_update."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_create_permission_denied(self):
        """Test that users without add permission cannot create inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        # Create a regular user without add_article permission
        request = await self._create_regular_user_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "data": {
                                "title": f"New Article {uid}",
                                "content": "Test content",
                            }
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        # The parent update should fail due to permission check on parent
        # or the inline create should fail with permission denied
        if "error" in data:
            assert data["code"] == "permission_denied"
        elif "inlines" in data:
            # Check inline errors
            errors = data["inlines"].get("errors", [])
            assert len(errors) > 0
            assert any("permission" in e.get("error", "").lower() for e in errors)

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_update_permission_denied(self):
        """Test that users without change permission cannot update inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        article = await self._create_article(uid, author)
        # Create a regular user without change_article permission
        request = await self._create_regular_user_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "id": article.pk,
                            "data": {"title": f"Updated Article {uid}"},
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        # The parent update should fail due to permission check on parent
        # or the inline update should fail with permission denied
        if "error" in data:
            assert data["code"] == "permission_denied"
        elif "inlines" in data:
            errors = data["inlines"].get("errors", [])
            assert len(errors) > 0
            assert any("permission" in e.get("error", "").lower() for e in errors)

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_delete_permission_denied(self):
        """Test that users without delete permission cannot delete inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        article = await self._create_article(uid, author)
        # Create a regular user without delete_article permission
        request = await self._create_regular_user_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "id": article.pk,
                            "_delete": True,
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        # The parent update should fail due to permission check on parent
        # or the inline delete should fail with permission denied
        if "error" in data:
            assert data["code"] == "permission_denied"
        elif "inlines" in data:
            errors = data["inlines"].get("errors", [])
            assert len(errors) > 0
            assert any("permission" in e.get("error", "").lower() for e in errors)

        # Verify article was not deleted
        @sync_to_async
        def check_exists():
            return Article.objects.filter(pk=article.pk).exists()

        exists = await check_exists()
        assert exists, "Article should not be deleted without permission"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_create_superuser_allowed(self):
        """Test that superuser can create inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "data": {
                                "title": f"New Article {uid}",
                                "content": "Test content",
                            }
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        if "inlines" in data:
            assert len(data["inlines"].get("created", [])) > 0
            assert len(data["inlines"].get("errors", [])) == 0

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_update_superuser_allowed(self):
        """Test that superuser can update inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        article = await self._create_article(uid, author)
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "id": article.pk,
                            "data": {"title": f"Updated Article {uid}"},
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        if "inlines" in data:
            assert len(data["inlines"].get("updated", [])) > 0
            assert len(data["inlines"].get("errors", [])) == 0

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_inline_delete_superuser_allowed(self):
        """Test that superuser can delete inlines."""
        uid = unique_id()
        author = await self._create_author(uid)
        article = await self._create_article(uid, author)
        article_pk = article.pk
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {},  # No parent changes
                "inlines": {
                    "article": [
                        {
                            "id": article_pk,
                            "_delete": True,
                        }
                    ]
                },
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        if "inlines" in data:
            assert len(data["inlines"].get("deleted", [])) > 0
            assert len(data["inlines"].get("errors", [])) == 0

        # Verify article was deleted
        @sync_to_async
        def check_deleted():
            return not Article.objects.filter(pk=article_pk).exists()

        deleted = await check_deleted()
        assert deleted, "Article should be deleted by superuser"

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_inline_{uid}@example.com")

        return await create()

    async def _create_article(self, uid, author):
        """Helper to create an article."""

        @sync_to_async
        def create():
            return Article.objects.create(
                title=f"Test Article {uid}",
                content="Test content",
                author=author,
            )

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_inline_{uid}",
                email=f"admin_inline_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()

    async def _create_regular_user_request(self, uid):
        """Helper to create a request with regular user (no permissions)."""

        @sync_to_async
        def create_user():
            user = User.objects.create_user(
                username=f"user_inline_{uid}",
                email=f"user_inline_{uid}@example.com",
                password="user",
            )
            return create_mock_request(user)

        return await create_user()
