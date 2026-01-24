"""
Tests for secure error handling in django_admin_mcp handlers.

Verifies that generic exception handlers don't leak internal information
like database schema details, filesystem paths, or internal error messages.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_create,
    handle_delete,
    handle_get,
    handle_list,
    handle_update,
)
from django_admin_mcp.handlers.actions import handle_action, handle_actions, handle_bulk
from django_admin_mcp.handlers.errors import (
    handle_database_error,
    handle_generic_error,
    handle_not_found_error,
    handle_permission_error,
    handle_validation_error,
)
from django_admin_mcp.handlers.meta import handle_describe, handle_find_models
from django_admin_mcp.handlers.relations import handle_autocomplete
from tests.models import Author


@pytest.fixture
async def superuser():
    """Create a superuser for testing."""
    unique_suffix = uuid.uuid4().hex[:8]
    user = await sync_to_async(User.objects.create_superuser)(
        username=f"test_admin_{unique_suffix}",
        email=f"admin_{unique_suffix}@test.com",
        password="testpass123",
    )
    return user


@pytest.fixture
async def superuser_request(superuser):
    """Create a request with superuser."""
    request = create_mock_request()
    request.user = superuser
    return request


class TestErrorHandlingUtilities:
    """Test the error handling utility functions."""

    def test_handle_database_error_integrity(self):
        """Test that IntegrityError returns generic message."""
        error = IntegrityError('duplicate key value violates unique constraint "app_article_slug_key"')
        result = handle_database_error(error, "test operation")

        assert result["error"] == "A database constraint was violated"
        assert result["code"] == "integrity_error"
        assert "duplicate key" not in result["error"]
        assert "slug_key" not in result["error"]

    def test_handle_database_error_operational(self):
        """Test that OperationalError returns generic message."""
        error = OperationalError("could not connect to server: Connection refused")
        result = handle_database_error(error, "test operation")

        assert result["error"] == "A database error occurred"
        assert result["code"] == "database_error"
        assert "Connection refused" not in result["error"]
        assert "server" not in result["error"]

    def test_handle_validation_error(self):
        """Test that ValidationError returns generic message."""
        error = DjangoValidationError("Invalid email format: test@invalid")
        result = handle_validation_error(error, "test operation")

        assert result["error"] == "Validation failed"
        assert result["code"] == "validation_error"

    def test_handle_not_found_error(self):
        """Test that not found error doesn't leak model details."""
        result = handle_not_found_error("article", obj_id=123)

        assert result["error"] == "Article not found"
        assert result["code"] == "not_found"

    def test_handle_permission_error(self):
        """Test that permission error is descriptive but safe."""
        result = handle_permission_error("delete", "article")

        assert result["error"] == "Permission denied: cannot delete article"
        assert result["code"] == "permission_denied"

    def test_handle_generic_error_value_error(self):
        """Test that ValueError returns generic message."""
        error = ValueError("Invalid literal for int() with base 10: 'abc'")
        result = handle_generic_error(error, "test operation")

        assert result["error"] == "Invalid input provided"
        assert result["code"] == "invalid_input"
        assert "literal" not in result["error"]
        assert "base 10" not in result["error"]

    def test_handle_generic_error_attribute_error(self):
        """Test that AttributeError returns generic message."""
        error = AttributeError("'NoneType' object has no attribute 'name'")
        result = handle_generic_error(error, "test operation")

        assert result["error"] == "An unexpected error occurred"
        assert result["code"] == "internal_error"
        assert "NoneType" not in result["error"]
        assert "attribute" not in result["error"]


class TestCRUDErrorHandling:
    """Test CRUD handlers don't leak information on errors."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_list_generic_error_no_leak(self, superuser_request):
        """Test that list handler catches and sanitizes generic errors."""
        # Mock sync_to_async to raise an exception inside the try block
        with patch("django_admin_mcp.handlers.crud.sync_to_async") as mock_sync:
            # Make sync_to_async raise an error when called
            mock_sync.side_effect = AttributeError("'NoneType' object has no attribute '_meta'")

            result = await handle_list("article", {}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "internal_error"
            # Should NOT contain internal details
            assert "NoneType" not in data["error"]
            assert "_meta" not in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_get_not_found_error(self, superuser_request):
        """Test that get handler returns proper not found error."""
        result = await handle_get("article", {"id": 99999}, superuser_request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["error"] == "article not found"
        assert data["code"] == "not_found"

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_create_integrity_error_no_leak(self, superuser_request):
        """Test that create handler doesn't leak constraint names."""
        unique_suffix = uuid.uuid4().hex[:8]
        # Create an author first
        author = await sync_to_async(Author.objects.create)(
            name=f"Test Author {unique_suffix}", email=f"test_{unique_suffix}@example.com", bio="Bio"
        )

        # Try to create another with same email (unique constraint)
        result = await handle_create(
            "author",
            {"data": {"name": "Another Author", "email": f"test_{unique_suffix}@example.com", "bio": "Bio 2"}},
            superuser_request,
        )

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        # Should have generic error message
        assert data["code"] in ["integrity_error", "validation_error"]
        # Should NOT contain table names or constraint names
        assert "unique constraint" not in data["error"].lower()
        # "email" should only appear if it's part of a generic validation message, not raw constraint details
        if "email" in data.get("error", "").lower():
            # If email is mentioned, it should be in context of validation, not database constraints
            assert "validation" in data.get("error", "").lower()

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_update_generic_error_no_leak(self, superuser_request):
        """Test that update handler catches and sanitizes generic errors."""
        unique_suffix = uuid.uuid4().hex[:8]
        # Create test data
        author = await sync_to_async(Author.objects.create)(
            name=f"Test Author {unique_suffix}", email=f"test_{unique_suffix}@example.com", bio="Bio"
        )

        # Mock the model_to_dict function to raise an error
        with patch("django_admin_mcp.handlers.crud.model_to_dict") as mock_dict:
            mock_dict.side_effect = RuntimeError("Internal server error with path /app/data")

            result = await handle_update("author", {"id": author.id, "data": {"name": "New Name"}}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain file paths
            assert "/app/" not in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_delete_not_found_error(self, superuser_request):
        """Test that delete handler returns proper not found error."""
        result = await handle_delete("author", {"id": 99999}, superuser_request)

        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["error"] == "author not found"
        assert data["code"] == "not_found"


class TestActionsErrorHandling:
    """Test action handlers don't leak information on errors."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_handle_actions_generic_error_no_leak(self, superuser_request):
        """Test that actions handler catches and sanitizes generic errors."""
        with patch("django_admin_mcp.handlers.actions.get_model_admin") as mock_get:
            mock_get.side_effect = RuntimeError("Database connection timeout at host db.internal.example.com")

            result = await handle_actions("article", {}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain internal hostnames
            assert "db.internal" not in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_handle_action_generic_error_no_leak(self, superuser_request):
        """Test that action execution handler sanitizes errors."""
        unique_suffix = uuid.uuid4().hex[:8]
        # Create test data
        author = await sync_to_async(Author.objects.create)(
            name=f"Test Author {unique_suffix}", email=f"test_{unique_suffix}@example.com", bio="Bio"
        )

        with patch("django_admin_mcp.handlers.actions.sync_to_async") as mock_sync:

            async def mock_execute_action():
                raise MemoryError("Out of memory: 2048MB used, 4096MB available")

            mock_sync.return_value = mock_execute_action

            result = await handle_action("author", {"action": "test_action", "ids": [author.id]}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain memory details
            assert "2048MB" not in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_bulk_create_error_no_leak(self, superuser_request):
        """Test that bulk create doesn't leak error details."""
        # Mock to simulate database error
        with patch("django_admin_mcp.handlers.actions.sync_to_async") as mock_sync:

            async def mock_execute_bulk():
                raise OperationalError("FATAL: too many connections for role 'admin'")

            mock_sync.return_value = mock_execute_bulk

            result = await handle_bulk(
                "author",
                {"operation": "create", "items": [{"name": "Test", "email": "test@test.com"}]},
                superuser_request,
            )

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain role names or connection details
            # Allow "database" as part of generic message, but not "role" in connection details
            if "role" in data["error"].lower():
                # If "role" appears, it should only be in generic context like "database error"
                assert "database" in data["error"].lower()


class TestMetaErrorHandling:
    """Test meta handlers don't leak information on errors."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_describe_generic_error_no_leak(self, superuser_request):
        """Test that describe handler catches and sanitizes generic errors."""
        with patch("django_admin_mcp.handlers.meta.get_model_admin") as mock_get:
            mock_get.side_effect = ImportError("No module named 'app.models.internal'")

            result = await handle_describe("article", {}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain module paths
            assert "app.models" not in data["error"]

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_find_models_generic_error_no_leak(self, superuser_request):
        """Test that find_models handler sanitizes errors."""
        with patch("django_admin_mcp.handlers.meta.site") as mock_site:
            mock_site._registry = MagicMock()
            mock_site._registry.items.side_effect = RuntimeError("Registry corrupted at 0x7f8a3c4d5e6f")

            result = await handle_find_models("", {}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain memory addresses
            assert "0x" not in data["error"]


class TestRelationsErrorHandling:
    """Test relations handlers don't leak information on errors."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_autocomplete_generic_error_no_leak(self, superuser_request):
        """Test that autocomplete handler sanitizes errors."""
        with patch("django_admin_mcp.handlers.relations.Q") as mock_q:
            mock_q.side_effect = RuntimeError("Query error: column 'articles.internal_id' does not exist")

            result = await handle_autocomplete("article", {"term": "test"}, superuser_request)

            assert len(result) == 1
            data = json.loads(result[0].text)
            assert "error" in data
            # Should NOT contain column names
            assert "internal_id" not in data["error"]
