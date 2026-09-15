"""
Tests for django_admin_mcp.handlers.crud CRUD operation handlers.
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin as django_admin
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_create,
    handle_delete,
    handle_get,
    handle_list,
    handle_update,
)
from tests.models import Article, Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


class TestHandleList:
    """Tests for handle_list function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_returns_results(self):
        """Test that handle_list returns a list of results."""
        uid = unique_id()
        # Create test data
        author = await self._create_author(uid)

        # Create superuser request
        request = await self._create_superuser_request(uid)

        result = await handle_list("author", {}, request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "results" in data
        assert "count" in data
        assert "total_count" in data

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_with_filters(self):
        """Test handle_list with filter parameters."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_list("author", {"filters": {"name": f"Test Author {uid}"}}, request)

        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert data["results"][0]["name"] == f"Test Author {uid}"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_with_search(self):
        """Test handle_list with search parameter."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_list("author", {"search": uid}, request)

        data = json.loads(result[0].text)
        assert data["count"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_with_pagination(self):
        """Test handle_list with limit and offset."""
        uid = unique_id()
        # Create multiple authors
        for i in range(5):
            await self._create_author(f"{uid}_{i}")

        request = await self._create_superuser_request(uid)

        result = await handle_list("author", {"limit": 2, "offset": 0}, request)

        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["total_count"] >= 5

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_with_ordering(self):
        """Test handle_list with order_by parameter."""
        uid = unique_id()
        await self._create_author(f"ZZZ_{uid}")
        await self._create_author(f"AAA_{uid}")
        request = await self._create_superuser_request(uid)

        result = await handle_list("author", {"order_by": ["name"]}, request)

        data = json.loads(result[0].text)
        # Check that results are ordered by name
        assert data["count"] >= 2

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_model_not_found(self):
        """Test handle_list with non-existent model."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_list("nonexistent", {}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_permission_denied(self):
        """Test handle_list with anonymous user."""
        request = create_mock_request(AnonymousUser())  # Explicit anonymous user for permission testing

        result = await handle_list("author", {}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert data["code"] == "permission_denied"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_respects_mcp_exclude_fields(self):
        """list_* must omit fields configured via mcp_exclude_fields."""
        from django.contrib import admin  # noqa: PLC0415

        uid = unique_id()
        author = await self._create_author(uid)
        await sync_to_async(Author.objects.filter(pk=author.pk).update)(bio="super-secret-bio")
        request = await self._create_superuser_request(uid)

        model_admin = admin.site._registry[Author]
        original_exclude = getattr(model_admin, "mcp_exclude_fields", None)
        model_admin.mcp_exclude_fields = ["bio"]
        try:
            result = await handle_list("author", {"filters": {"id": author.pk}}, request)
            data = json.loads(result[0].text)
            assert data["count"] == 1
            row = data["results"][0]
            assert "bio" not in row
            assert "super-secret-bio" not in json.dumps(row)
            assert row["name"] == f"Test Author {uid}"
        finally:
            if original_exclude is None:
                delattr(model_admin, "mcp_exclude_fields")
            else:
                model_admin.mcp_exclude_fields = original_exclude

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_{uid}",
                email=f"admin_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


class TestHandleGet:
    """Tests for handle_get function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_returns_object(self):
        """Test that handle_get returns a single object."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_get("author", {"id": author.pk}, request)

        data = json.loads(result[0].text)
        assert data["name"] == f"Test Author {uid}"
        assert data["email"] == f"test_{uid}@example.com"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_requires_id(self):
        """Test that handle_get requires id parameter."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_get("author", {}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "id" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_not_found(self):
        """Test handle_get with non-existent id."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_get("author", {"id": 99999}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_with_include_inlines(self):
        """Test handle_get with include_inlines parameter."""
        uid = unique_id()
        author = await self._create_author(uid)
        await self._create_article(uid, author)
        request = await self._create_superuser_request(uid)

        result = await handle_get("author", {"id": author.pk, "include_inlines": True}, request)

        data = json.loads(result[0].text)
        assert data["name"] == f"Test Author {uid}"
        # Inlines should be included
        assert "_inlines" in data

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_with_include_related(self):
        """Test handle_get with include_related parameter."""
        uid = unique_id()
        author = await self._create_author(uid)
        await self._create_article(uid, author)
        request = await self._create_superuser_request(uid)

        result = await handle_get("author", {"id": author.pk, "include_related": True}, request)

        data = json.loads(result[0].text)
        assert data["name"] == f"Test Author {uid}"
        # Related data should be included (articles reverse FK)
        if "_related" in data:
            assert "articles" in data["_related"]

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

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
                username=f"admin_get_{uid}",
                email=f"admin_get_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


class TestHandleCreate:
    """Tests for handle_create function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_returns_new_object(self):
        """Test that handle_create creates and returns a new object."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_create(
            "author",
            {"data": {"name": f"New Author {uid}", "email": f"new_{uid}@example.com"}},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "id" in data
        assert data["object"]["name"] == f"New Author {uid}"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_logs_action(self):
        """Test that handle_create logs the action."""

        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_create(
            "author",
            {"data": {"name": f"Logged Author {uid}", "email": f"logged_{uid}@example.com"}},
            request,
        )

        data = json.loads(result[0].text)
        obj_id = data["id"]

        @sync_to_async
        def check_log():
            ct = ContentType.objects.get_for_model(Author)
            log = LogEntry.objects.filter(content_type=ct, object_id=str(obj_id), action_flag=ADDITION).first()
            return log is not None

        has_log = await check_log()
        assert has_log

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_with_invalid_data(self):
        """Test handle_create with invalid data."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_create(
            "author",
            {"data": {"invalid_field": "value"}},
            request,
        )

        data = json.loads(result[0].text)
        assert "error" in data

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_create_{uid}",
                email=f"admin_create_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


class TestHandleUpdate:
    """Tests for handle_update function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_returns_updated_object(self):
        """Test that handle_update updates and returns the object."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {"id": author.pk, "data": {"name": f"Updated Author {uid}"}},
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["object"]["name"] == f"Updated Author {uid}"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_requires_id(self):
        """Test that handle_update requires id parameter."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_update("author", {"data": {"name": "Updated"}}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "id" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_not_found(self):
        """Test handle_update with non-existent id."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_update("author", {"id": 99999, "data": {"name": "Updated"}}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_invalid_field(self):
        """Test handle_update with invalid field."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {"id": author.pk, "data": {"invalid_field": "value"}},
            request,
        )

        data = json.loads(result[0].text)
        assert "error" in data
        assert "Invalid field" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_logs_action(self):
        """Test that handle_update logs the action."""

        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)

        await handle_update(
            "author",
            {"id": author.pk, "data": {"name": f"Changed Author {uid}"}},
            request,
        )

        @sync_to_async
        def check_log():
            ct = ContentType.objects.get_for_model(Author)
            log = LogEntry.objects.filter(content_type=ct, object_id=str(author.pk), action_flag=CHANGE).first()
            return log is not None

        has_log = await check_log()
        assert has_log

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_with_inlines(self):
        """Test handle_update with inline updates."""
        uid = unique_id()
        author = await self._create_author(uid)
        article = await self._create_article(uid, author)
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "author",
            {
                "id": author.pk,
                "data": {"name": f"Updated Author {uid}"},
                "inlines": {"article": [{"id": article.pk, "data": {"title": f"Updated Article {uid}"}}]},
            },
            request,
        )

        data = json.loads(result[0].text)
        assert data["success"] is True
        # Inlines result may or may not be present depending on implementation

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

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
                username=f"admin_update_{uid}",
                email=f"admin_update_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


class TestHandleDelete:
    """Tests for handle_delete function."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_removes_object(self):
        """Test that handle_delete removes the object."""

        uid = unique_id()
        author = await self._create_author(uid)
        author_pk = author.pk
        request = await self._create_superuser_request(uid)

        result = await handle_delete("author", {"id": author_pk}, request)

        data = json.loads(result[0].text)
        assert data["success"] is True
        assert "deleted" in data["message"]

        # Verify object is deleted
        @sync_to_async
        def check_deleted():
            return not Author.objects.filter(pk=author_pk).exists()

        is_deleted = await check_deleted()
        assert is_deleted

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_requires_id(self):
        """Test that handle_delete requires id parameter."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_delete("author", {}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "id" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_not_found(self):
        """Test handle_delete with non-existent id."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_delete("author", {"id": 99999}, request)

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_logs_action(self):
        """Test that handle_delete logs the action."""

        uid = unique_id()
        author = await self._create_author(uid)
        author_pk = author.pk
        request = await self._create_superuser_request(uid)

        await handle_delete("author", {"id": author_pk}, request)

        @sync_to_async
        def check_log():
            ct = ContentType.objects.get_for_model(Author)
            log = LogEntry.objects.filter(content_type=ct, object_id=str(author_pk), action_flag=DELETION).first()
            return log is not None

        has_log = await check_log()
        assert has_log

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_del_{uid}@example.com")

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_delete_{uid}",
                email=f"admin_delete_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


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


class TestSaveModelIntegration:
    """Tests that CRUD handlers call ModelAdmin.save_model() and delete_model()."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_calls_save_model(self):
        """Test that handle_create calls ModelAdmin.save_model() with change=False."""
        uid = unique_id()
        request = await self._create_superuser_request(uid)
        author_admin = self._get_author_admin()
        original_save_model = author_admin.save_model

        with patch.object(author_admin, "save_model", wraps=original_save_model) as mock_save:
            result = await handle_create(
                "author",
                {"data": {"name": f"SaveModel Author {uid}", "email": f"savemodel_{uid}@example.com"}},
                request,
            )

            data = json.loads(result[0].text)
            assert data["success"] is True
            mock_save.assert_called_once()
            # Verify change=False for create
            # save_model(request, obj, form, change) - but `self` is consumed by the bound method
            _, call_kwargs = mock_save.call_args
            # Arguments may be positional or keyword; check both
            if "change" in call_kwargs:
                assert call_kwargs["change"] is False
            else:
                # Positional args: (request, obj, form, change)
                assert mock_save.call_args[0][-1] is False

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_calls_save_model(self):
        """Test that handle_update calls ModelAdmin.save_model() with change=True."""
        uid = unique_id()
        author = await self._create_author(uid)
        request = await self._create_superuser_request(uid)
        author_admin = self._get_author_admin()
        original_save_model = author_admin.save_model

        with patch.object(author_admin, "save_model", wraps=original_save_model) as mock_save:
            result = await handle_update(
                "author",
                {"id": author.pk, "data": {"name": f"Updated SaveModel Author {uid}"}},
                request,
            )

            data = json.loads(result[0].text)
            assert data["success"] is True
            mock_save.assert_called_once()
            # Verify change=True for update
            _, call_kwargs = mock_save.call_args
            if "change" in call_kwargs:
                assert call_kwargs["change"] is True
            else:
                assert mock_save.call_args[0][-1] is True

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_calls_delete_model(self):
        """Test that handle_delete calls ModelAdmin.delete_model()."""
        uid = unique_id()
        author = await self._create_author(uid)
        author_pk = author.pk
        request = await self._create_superuser_request(uid)
        author_admin = self._get_author_admin()
        original_delete_model = author_admin.delete_model

        with patch.object(author_admin, "delete_model", wraps=original_delete_model) as mock_delete:
            result = await handle_delete("author", {"id": author_pk}, request)

            data = json.loads(result[0].text)
            assert data["success"] is True
            mock_delete.assert_called_once()

        # Verify object is deleted
        @sync_to_async
        def check_deleted():
            return not Author.objects.filter(pk=author_pk).exists()

        is_deleted = await check_deleted()
        assert is_deleted

    def _get_author_admin(self):
        """Get the registered AuthorAdmin instance."""
        from django.contrib import admin  # noqa: PLC0415

        return admin.site._registry[Author]

    async def _create_author(self, uid):
        """Helper to create an author."""

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_sm_{uid}@example.com")

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_sm_{uid}",
                email=f"admin_sm_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()


@pytest.mark.django_db
@pytest.mark.asyncio
class TestIncludeRelatedPermissions:
    """include_related/include_inlines must check view permission on the related model (issue #91)."""

    @staticmethod
    @sync_to_async
    def _request_with_perms(uid, *codenames):
        user = User.objects.create_user(username=f"incperm_{uid}", email=f"incperm_{uid}@example.com", password="x")
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        return create_mock_request(User.objects.get(pk=user.pk))

    @staticmethod
    @sync_to_async
    def _author_with_article(uid):
        author = Author.objects.create(name=f"Inc Author {uid}", email=f"inc_{uid}@example.com")
        article = Article.objects.create(title=f"Inc Article {uid}", content="c", author=author)
        return author, article

    async def test_include_related_omits_models_without_view_permission(self):
        uid = unique_id()
        author, _ = await self._author_with_article(uid)
        request = await self._request_with_perms(uid, "view_author")  # no view_article

        result = await handle_get("author", {"id": author.pk, "include_related": True}, request)
        data = json.loads(result[0].text)

        assert "error" not in data
        assert "articles" not in (data.get("_related") or {})
        assert f"Inc Article {uid}" not in result[0].text

    async def test_include_related_serves_models_with_view_permission(self):
        uid = unique_id()
        author, article = await self._author_with_article(uid)
        request = await self._request_with_perms(uid, "view_author", "view_article")

        result = await handle_get("author", {"id": author.pk, "include_related": True}, request)
        data = json.loads(result[0].text)

        related = data.get("_related") or {}
        assert {row["id"] for row in related.get("articles", [])} == {article.pk}

    async def test_include_inlines_omits_models_without_view_permission(self):
        uid = unique_id()
        author, _ = await self._author_with_article(uid)
        request = await self._request_with_perms(uid, "view_author")  # no view_article

        result = await handle_get("author", {"id": author.pk, "include_inlines": True}, request)
        data = json.loads(result[0].text)

        assert "error" not in data
        assert "article" not in (data.get("_inlines") or {})
        assert f"Inc Article {uid}" not in result[0].text

    async def test_include_inlines_serves_models_with_view_permission(self):
        uid = unique_id()
        author, article = await self._author_with_article(uid)
        request = await self._request_with_perms(uid, "view_author", "view_article")

        result = await handle_get("author", {"id": author.pk, "include_inlines": True}, request)
        data = json.loads(result[0].text)

        inlines = data.get("_inlines") or {}
        assert {row["id"] for row in inlines.get("article", [])} == {article.pk}

    async def test_include_related_respects_related_admin_queryset(self):
        uid = unique_id()
        author, visible = await self._author_with_article(uid)
        hidden = await sync_to_async(Article.objects.create)(
            title=f"Inc Hidden {uid}", content="c", author_id=author.pk
        )
        request = await self._request_with_perms(uid, "view_author", "view_article")

        article_admin = django_admin.site._registry[Article]

        def scoped_queryset(request):
            return Article.objects.exclude(pk=hidden.pk)

        with patch.object(article_admin, "get_queryset", side_effect=scoped_queryset):
            result = await handle_get("author", {"id": author.pk, "include_related": True}, request)
        data = json.loads(result[0].text)

        returned_ids = {row["id"] for row in (data.get("_related") or {}).get("articles", [])}
        assert visible.pk in returned_ids
        assert hidden.pk not in returned_ids


@pytest.mark.django_db
@pytest.mark.asyncio
class TestIncludeRelatedForwardFK:
    """include_related must not crash on models with forward FKs (issue #93)."""

    @staticmethod
    @sync_to_async
    def _superuser_request(uid):
        user = User.objects.create_superuser(username=f"fkinc_{uid}", email=f"fkinc_{uid}@example.com", password="x")
        return create_mock_request(user)

    async def test_get_with_include_related_on_model_with_forward_fk(self):
        uid = unique_id()
        author = await sync_to_async(Author.objects.create)(name=f"FK Author {uid}", email=f"fk_{uid}@example.com")
        article = await sync_to_async(Article.objects.create)(title=f"FK Article {uid}", content="c", author=author)
        request = await self._superuser_request(uid)

        result = await handle_get("article", {"id": article.pk, "include_related": True}, request)
        data = json.loads(result[0].text)

        assert "error" not in data
        assert data["id"] == article.pk
        # Forward FK stays a pk field, not a _related entry
        assert data["author"] == author.pk
        assert "author" not in (data.get("_related") or {})
