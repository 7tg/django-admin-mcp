"""
Tests for database error handling in django_admin_mcp handlers.

These tests verify that database exceptions (IntegrityError, OperationalError, ValidationError)
are properly caught and return user-friendly error messages.
"""

import json
import uuid
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


def unique_username():
    """Generate a unique username for tests."""
    return f"testuser_{uuid.uuid4().hex[:8]}"


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
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
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

        result = await handle_create("author", arguments, request)

        data = json.loads(result[0].text)
        assert "error" in data
        # The unique constraint will be caught either during form validation
        # or during save, depending on the database backend
        # Both should result in a proper error message
        assert data.get("code") in ["validation_error", "duplicate_entry"]

    async def test_create_with_foreign_key_violation(self):
        """Test that creating with invalid foreign key is caught during validation."""
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
        request = create_mock_request(user)

        # Try to create article with non-existent author (should fail validation)
        arguments = {
            "data": {
                "title": "Test Article",
                "content": "Content",
                "author": 99999,  # Non-existent author
            }
        }

        result = await handle_create("article", arguments, request)

        data = json.loads(result[0].text)
        assert "error" in data
        # Foreign key validation typically happens at form level
        assert "validation" in data["error"].lower() or "not found" in data["error"].lower()


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUpdateErrorHandling:
    """Tests for error handling in handle_update."""

    async def test_update_with_duplicate_unique_field(self):
        """Test that updating to duplicate unique field returns proper error."""
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
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

        result = await handle_update("author", arguments, request)

        data = json.loads(result[0].text)
        assert "error" in data
        # The unique constraint will be caught either during form validation or save
        assert data.get("code") in ["validation_error", "duplicate_entry"]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDeleteErrorHandling:
    """Tests for error handling in handle_delete."""

    async def test_delete_successful(self):
        """Test that deleting without constraints succeeds."""
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
        request = create_mock_request(user)

        # Create author without articles
        author = await Author.objects.acreate(name=f"Test {uuid.uuid4().hex[:8]}", email=f"test_{uuid.uuid4().hex[:8]}@example.com")

        # Try to delete author
        arguments = {"id": author.pk}

        result = await handle_delete("author", arguments, request)

        data = json.loads(result[0].text)
        assert data.get("success") is True


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkErrorHandling:
    """Tests for error handling in handle_bulk operations."""

    async def test_bulk_create_successful(self):
        """Test bulk create with successful operations."""
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
        request = create_mock_request(user)

        arguments = {
            "operation": "create",
            "items": [
                {"name": f"Author {uuid.uuid4().hex[:8]}", "email": f"author1_{uuid.uuid4().hex[:8]}@example.com"},
                {"name": f"Author {uuid.uuid4().hex[:8]}", "email": f"author2_{uuid.uuid4().hex[:8]}@example.com"},
            ]
        }

        result = await handle_bulk("author", arguments, request)

        data = json.loads(result[0].text)
        assert data["success_count"] >= 2
        assert data["error_count"] == 0

    async def test_bulk_delete_successful(self):
        """Test bulk delete with successful operations."""
        user = await User.objects.acreate(username=unique_username(), is_superuser=True)
        request = create_mock_request(user)

        # Create authors
        author1 = await Author.objects.acreate(name=f"Author {uuid.uuid4().hex[:8]}", email=f"author1_{uuid.uuid4().hex[:8]}@example.com")
        author2 = await Author.objects.acreate(name=f"Author {uuid.uuid4().hex[:8]}", email=f"author2_{uuid.uuid4().hex[:8]}@example.com")

        arguments = {
            "operation": "delete",
            "items": [author1.pk, author2.pk],
        }

        result = await handle_bulk("author", arguments, request)

        data = json.loads(result[0].text)
        assert data["success_count"] >= 2
