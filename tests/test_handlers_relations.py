"""
Tests for django_admin_mcp.handlers.relations module.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from django_admin_mcp.handlers import (
    handle_autocomplete,
    handle_history,
    handle_related,
)
from django_admin_mcp.handlers.base import create_mock_request
from tests.models import Article, Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_author(name, email):
    """Create an author asynchronously."""
    return Author.objects.create(name=name, email=email)


@sync_to_async
def create_article(title, content, author):
    """Create an article asynchronously."""
    return Article.objects.create(title=title, content=content, author=author)


@sync_to_async
def create_user(username, email, password):
    """Create a user asynchronously."""
    return User.objects.create_user(username=username, email=email, password=password)


@sync_to_async
def create_log_entry(user, content_type, object_id, object_repr, action_flag, change_message=""):
    """Create a log entry asynchronously."""
    return LogEntry.objects.create(
        user=user,
        content_type=content_type,
        object_id=object_id,
        object_repr=object_repr,
        action_flag=action_flag,
        change_message=change_message,
    )


@sync_to_async
def get_content_type(model):
    """Get content type for a model asynchronously."""
    return ContentType.objects.get_for_model(model)


class TestHandleRelated:
    """Tests for handle_related function."""

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_model_not_found(self):
        """Test error when model is not found."""
        request = create_mock_request()
        result = await handle_related(
            "nonexistent_model",
            {"id": 1, "relation": "something"},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_id_required(self):
        """Test error when id parameter is missing."""
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"relation": "articles"},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "id parameter is required" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_relation_required(self):
        """Test error when relation parameter is missing."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "relation parameter is required" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_object_not_found(self):
        """Test error when object with given id doesn't exist."""
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": 99999, "relation": "articles"},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_invalid_relation(self):
        """Test error when relation doesn't exist on model."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk, "relation": "nonexistent_relation"},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_many_relation_empty(self):
        """Test fetching empty many relation (reverse FK)."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk, "relation": "articles"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["relation"] == "articles"
        assert data["type"] == "many"
        assert data["count"] == 0
        assert data["total_count"] == 0
        assert data["results"] == []

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_many_relation_with_data(self):
        """Test fetching many relation with data."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        article1 = await create_article(f"Article 1 {uid}", "Content 1", author)
        article2 = await create_article(f"Article 2 {uid}", "Content 2", author)
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk, "relation": "articles"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["type"] == "many"
        assert data["count"] == 2
        assert data["total_count"] == 2
        assert len(data["results"]) == 2

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_many_relation_with_limit(self):
        """Test pagination with limit parameter."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        for i in range(5):
            await create_article(f"Article {i} {uid}", f"Content {i}", author)
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk, "relation": "articles", "limit": 2},
            request,
        )
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert data["total_count"] == 5

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_single_relation_fk(self):
        """Test fetching single relation (FK)."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        article = await create_article(f"Test Article {uid}", "Test content", author)
        request = create_mock_request()
        result = await handle_related(
            "article",
            {"id": article.pk, "relation": "author"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["relation"] == "author"
        assert data["type"] == "single"
        assert "result" in data
        assert data["result"]["name"] == f"Test Author {uid}"

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_simple_field_value(self):
        """Test fetching a simple field value (treated as value type)."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_related(
            "author",
            {"id": author.pk, "relation": "name"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["type"] == "value"
        assert f"Test Author {uid}" in data["value"]


class TestHandleHistory:
    """Tests for handle_history function."""

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_model_not_found(self):
        """Test error when model is not found."""
        request = create_mock_request()
        result = await handle_history(
            "nonexistent_model",
            {"id": 1},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_id_required(self):
        """Test error when id parameter is missing."""
        request = create_mock_request()
        result = await handle_history(
            "author",
            {},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "id parameter is required" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_object_not_found(self):
        """Test error when object with given id doesn't exist."""
        request = create_mock_request()
        result = await handle_history(
            "author",
            {"id": 99999},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_empty_history(self):
        """Test fetching history for object with no log entries."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_history(
            "author",
            {"id": author.pk},
            request,
        )
        data = json.loads(result[0].text)
        assert data["model"] == "author"
        assert data["object_id"] == author.pk
        assert data["count"] == 0
        assert data["history"] == []

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_history_with_entries(self):
        """Test fetching history with log entries."""
        uid = unique_id()
        user = await create_user(f"testuser_{uid}", f"test_{uid}@example.com", "testpass")
        author = await create_author(f"Test Author {uid}", f"author_{uid}@example.com")

        # Create log entries
        content_type = await get_content_type(Author)
        await create_log_entry(user, content_type, str(author.pk), str(author), ADDITION, "Created via test")

        request = create_mock_request()
        result = await handle_history(
            "author",
            {"id": author.pk},
            request,
        )
        data = json.loads(result[0].text)
        assert data["count"] == 1
        assert len(data["history"]) == 1
        assert data["history"][0]["action"] == "created"
        assert data["history"][0]["user"] == f"testuser_{uid}"

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_history_limit(self):
        """Test limit parameter for history entries."""
        uid = unique_id()
        user = await create_user(f"testuser_{uid}", f"test_{uid}@example.com", "testpass")
        author = await create_author(f"Test Author {uid}", f"author_{uid}@example.com")

        content_type = await get_content_type(Author)
        for i in range(5):
            await create_log_entry(user, content_type, str(author.pk), str(author), CHANGE, f"Change {i}")

        request = create_mock_request()
        result = await handle_history(
            "author",
            {"id": author.pk, "limit": 2},
            request,
        )
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["history"]) == 2


class TestHandleAutocomplete:
    """Tests for handle_autocomplete function."""

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_model_not_found(self):
        """Test error when model is not found."""
        request = create_mock_request()
        result = await handle_autocomplete(
            "nonexistent_model",
            {},
            request,
        )
        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Test autocomplete with no matching results."""
        request = create_mock_request()
        result = await handle_autocomplete(
            "author",
            {"term": "nonexistent_xyz_term"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["model"] == "author"
        assert data["term"] == "nonexistent_xyz_term"
        assert data["count"] == 0
        assert data["results"] == []

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_autocomplete_no_term(self):
        """Test autocomplete without search term returns all."""
        uid = unique_id()
        author1 = await create_author(f"Alice {uid}", f"alice_{uid}@example.com")
        author2 = await create_author(f"Bob {uid}", f"bob_{uid}@example.com")
        request = create_mock_request()
        result = await handle_autocomplete(
            "author",
            {},
            request,
        )
        data = json.loads(result[0].text)
        assert data["term"] == ""
        # Should return results (may include other test data)
        assert data["count"] >= 2

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_autocomplete_with_term(self):
        """Test autocomplete with search term filters results."""
        uid = unique_id()
        author1 = await create_author(f"Alice {uid}", f"alice_{uid}@example.com")
        author2 = await create_author(f"Bob {uid}", f"bob_{uid}@example.com")
        request = create_mock_request()
        result = await handle_autocomplete(
            "author",
            {"term": f"Alice {uid}"},
            request,
        )
        data = json.loads(result[0].text)
        assert data["term"] == f"Alice {uid}"
        assert data["count"] == 1
        assert data["results"][0]["text"] == f"Alice {uid}"

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_autocomplete_limit(self):
        """Test limit parameter."""
        uid = unique_id()
        for i in range(5):
            await create_author(f"TestAuthor{i} {uid}", f"testauthor{i}_{uid}@example.com")
        request = create_mock_request()
        result = await handle_autocomplete(
            "author",
            {"term": uid, "limit": 2},
            request,
        )
        data = json.loads(result[0].text)
        assert data["count"] == 2
        assert len(data["results"]) == 2

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_autocomplete_result_format(self):
        """Test that results have correct format with id and text."""
        uid = unique_id()
        author = await create_author(f"Test Author {uid}", f"test_{uid}@example.com")
        request = create_mock_request()
        result = await handle_autocomplete(
            "author",
            {"term": uid},
            request,
        )
        data = json.loads(result[0].text)
        assert data["count"] >= 1
        result_item = data["results"][0]
        assert "id" in result_item
        assert "text" in result_item
        assert isinstance(result_item["id"], int)
        assert isinstance(result_item["text"], str)
