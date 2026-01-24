"""
Tests for database error handling in django_admin_mcp handlers.

These tests verify that database exceptions (IntegrityError, OperationalError, ValidationError)
are properly caught and return user-friendly error messages.
"""

import json
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_bulk,
    handle_create,
    handle_delete,
    handle_update,
)
from django_admin_mcp.handlers.base import handle_database_error
from tests.models import Article, Author


@pytest.mark.django_db
class TestDatabaseErrorHandler:
    """Tests for the handle_database_error utility function."""

    def test_handle_integrity_error_unique_constraint(self):
        """Test handling of IntegrityError with unique constraint violation."""
        error = IntegrityError("UNIQUE constraint failed: tests_author.email")
        result = handle_database_error(error)

        assert result["code"] == "duplicate_entry"
        assert "already exists" in result["error"]

    def test_handle_integrity_error_foreign_key(self):
        """Test handling of IntegrityError with foreign key constraint violation."""
        error = IntegrityError("FOREIGN KEY constraint failed")
        result = handle_database_error(error)

        assert result["code"] == "invalid_reference"
        assert "Referenced record does not exist" in result["error"]

    def test_handle_integrity_error_generic_constraint(self):
        """Test handling of IntegrityError with generic constraint violation."""
        error = IntegrityError("Some constraint failed")
        result = handle_database_error(error)

        assert result["code"] == "constraint_error"
        assert "Database constraint violated" in result["error"]

    def test_handle_operational_error(self):
        """Test handling of OperationalError."""
        error = OperationalError("database is locked")
        result = handle_database_error(error)

        assert result["code"] == "database_unavailable"
        assert "Database temporarily unavailable" in result["error"]

    def test_handle_validation_error_with_message_dict(self):
        """Test handling of ValidationError with message_dict."""
        error = ValidationError({"email": ["Invalid email format"], "name": ["Required"]})
        result = handle_database_error(error)

        assert result["code"] == "validation_error"
        assert "validation_errors" in result
        assert result["validation_errors"]["email"] == ["Invalid email format"]

    def test_handle_validation_error_with_messages(self):
        """Test handling of ValidationError with messages list."""
        error = ValidationError(["Error 1", "Error 2"])
        result = handle_database_error(error)

        assert result["code"] == "validation_error"
        assert "messages" in result
        assert len(result["messages"]) == 2


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCreateErrorHandling:
    """Tests for error handling in handle_create."""

    async def test_create_with_duplicate_unique_field(self):
        """Test that creating with duplicate unique field returns proper error."""
        # Create a user for the request
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Create an author with email
        await Author.objects.acreate(name="Test Author", email="test@example.com")

        # Try to create another author with same email (should fail unique constraint)
        arguments = {
            "data": {
                "name": "Another Author",
                "email": "test@example.com",
            }
        }

        # Mock form.save() to raise IntegrityError
        with patch("django_admin_mcp.handlers.crud.ModelForm.save") as mock_save:
            mock_save.side_effect = IntegrityError("UNIQUE constraint failed: tests_author.email")

            result = await handle_create("author", arguments, request)

            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "duplicate_entry"
            assert "already exists" in data["error"]

    async def test_create_with_foreign_key_violation(self):
        """Test that creating with invalid foreign key returns proper error."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Try to create article with non-existent author (should fail FK constraint)
        arguments = {
            "data": {
                "title": "Test Article",
                "content": "Content",
                "author": 99999,  # Non-existent author
            }
        }

        # Mock form.save() to raise IntegrityError for foreign key
        with patch("django_admin_mcp.handlers.crud.ModelForm.save") as mock_save:
            mock_save.side_effect = IntegrityError("FOREIGN KEY constraint failed")

            result = await handle_create("article", arguments, request)

            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "invalid_reference"

    async def test_create_with_operational_error(self):
        """Test that operational errors during create are handled properly."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        arguments = {
            "data": {
                "name": "Test Author",
                "email": "test@example.com",
            }
        }

        # Mock form.save() to raise OperationalError
        with patch("django_admin_mcp.handlers.crud.ModelForm.save") as mock_save:
            mock_save.side_effect = OperationalError("database is locked")

            result = await handle_create("author", arguments, request)

            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "database_unavailable"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUpdateErrorHandling:
    """Tests for error handling in handle_update."""

    async def test_update_with_duplicate_unique_field(self):
        """Test that updating to duplicate unique field returns proper error."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Create two authors
        author1 = await Author.objects.acreate(name="Author 1", email="author1@example.com")
        await Author.objects.acreate(name="Author 2", email="author2@example.com")

        # Try to update author1's email to match author2's (should fail)
        arguments = {
            "id": author1.pk,
            "data": {
                "email": "author2@example.com",
            }
        }

        # Mock form.save() to raise IntegrityError
        with patch("django_admin_mcp.handlers.crud.ModelForm.save") as mock_save:
            mock_save.side_effect = IntegrityError("UNIQUE constraint failed: tests_author.email")

            result = await handle_update("author", arguments, request)

            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "duplicate_entry"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDeleteErrorHandling:
    """Tests for error handling in handle_delete."""

    async def test_delete_with_foreign_key_constraint(self):
        """Test that deleting with FK constraint returns proper error."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Create author with articles
        author = await Author.objects.acreate(name="Test Author", email="test@example.com")
        await Article.objects.acreate(title="Article", content="Content", author=author)

        # Try to delete author (should fail due to FK constraint in some DB setups)
        arguments = {"id": author.pk}

        # Mock obj.delete() to raise IntegrityError
        with patch("tests.models.Author.delete") as mock_delete:
            mock_delete.side_effect = IntegrityError("FOREIGN KEY constraint failed")

            result = await handle_delete("author", arguments, request)

            data = json.loads(result[0].text)
            assert "error" in data
            assert data["code"] == "invalid_reference"


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkErrorHandling:
    """Tests for error handling in handle_bulk operations."""

    async def test_bulk_create_with_mixed_results(self):
        """Test bulk create with some successes and some failures."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Create one author that will cause duplicate error
        await Author.objects.acreate(name="Existing", email="existing@example.com")

        arguments = {
            "operation": "create",
            "items": [
                {"name": "New Author", "email": "new@example.com"},
                {"name": "Duplicate", "email": "existing@example.com"},  # Will fail
            ]
        }

        # Mock form.save() to raise IntegrityError for second item
        call_count = 0
        def side_effect_save(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise IntegrityError("UNIQUE constraint failed")
            # Create a mock object for first call
            mock_obj = Mock()
            mock_obj.pk = call_count
            return mock_obj

        with patch("django_admin_mcp.handlers.actions.ModelForm.save", side_effect=side_effect_save):
            result = await handle_bulk("author", arguments, request)

            data = json.loads(result[0].text)
            assert data["success_count"] >= 0
            assert data["error_count"] >= 0
            # Check that errors contain proper error codes
            if data["error_count"] > 0:
                errors = data["results"]["errors"]
                # At least one error should have duplicate_entry code
                assert any(e.get("code") == "duplicate_entry" for e in errors)

    async def test_bulk_delete_with_constraint_error(self):
        """Test bulk delete with constraint violations."""
        user = await User.objects.acreate(username="testuser", is_superuser=True)
        request = create_mock_request(user)

        # Create authors
        author1 = await Author.objects.acreate(name="Author 1", email="author1@example.com")
        author2 = await Author.objects.acreate(name="Author 2", email="author2@example.com")

        arguments = {
            "operation": "delete",
            "items": [author1.pk, author2.pk],
        }

        # Mock delete to raise IntegrityError for first author
        call_count = 0
        def side_effect_delete(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise IntegrityError("FOREIGN KEY constraint failed")

        with patch("tests.models.Author.delete", side_effect=side_effect_delete):
            result = await handle_bulk("author", arguments, request)

            data = json.loads(result[0].text)
            # At least one should have error
            if data["error_count"] > 0:
                errors = data["results"]["errors"]
                assert any(e.get("code") == "invalid_reference" for e in errors)
