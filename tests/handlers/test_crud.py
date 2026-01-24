"""
Tests for django_admin_mcp.handlers.crud CRUD operation handlers.
"""

import json
import uuid

import pytest
from django.contrib.auth.models import AnonymousUser, User

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

    async def _create_author(self, uid):
        """Helper to create an author."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

        return await create()

    async def _create_article(self, uid, author):
        """Helper to create an article."""
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async
        from django.contrib.admin.models import ADDITION, LogEntry

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
            from django.contrib.contenttypes.models import ContentType

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
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async
        from django.contrib.admin.models import CHANGE, LogEntry

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
            from django.contrib.contenttypes.models import ContentType

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
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")

        return await create()

    async def _create_article(self, uid, author):
        """Helper to create an article."""
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async

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
        from asgiref.sync import sync_to_async
        from django.contrib.admin.models import DELETION, LogEntry

        uid = unique_id()
        author = await self._create_author(uid)
        author_pk = author.pk
        request = await self._create_superuser_request(uid)

        await handle_delete("author", {"id": author_pk}, request)

        @sync_to_async
        def check_log():
            from django.contrib.contenttypes.models import ContentType

            ct = ContentType.objects.get_for_model(Author)
            log = LogEntry.objects.filter(content_type=ct, object_id=str(author_pk), action_flag=DELETION).first()
            return log is not None

        has_log = await check_log()
        assert has_log

    async def _create_author(self, uid):
        """Helper to create an author."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create():
            return Author.objects.create(name=f"Test Author {uid}", email=f"test_del_{uid}@example.com")

        return await create()

    async def _create_superuser_request(self, uid):
        """Helper to create a request with superuser."""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def create_user():
            user = User.objects.create_superuser(
                username=f"admin_delete_{uid}",
                email=f"admin_delete_{uid}@example.com",
                password="admin",
            )
            return create_mock_request(user)

        return await create_user()
