"""
Tests for django_admin_mcp.handlers.base utilities.
"""

import json
import logging
import uuid
from datetime import datetime

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError
from django.http import HttpRequest

from django_admin_mcp.handlers import (
    check_permission,
    create_mock_request,
    get_exposed_models,
    get_model_admin,
    get_model_name,
    json_response,
    serialize_instance,
)
from django_admin_mcp.handlers.base import MCPRequest, safe_error_message, sanitize_pydantic_errors
from django_admin_mcp.protocol.types import TextContent
from tests.models import Article, Author


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


class TestJsonResponse:
    """Tests for json_response function."""

    def test_returns_text_content_list(self):
        """Test that json_response returns a list of TextContent."""
        result = json_response({"key": "value"})
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)

    def test_serializes_dict_to_json(self):
        """Test that json_response properly serializes data."""
        data = {"name": "test", "count": 42}
        result = json_response(data)
        assert json.loads(result[0].text) == data

    def test_handles_non_serializable_with_default_str(self):
        """Test that json_response handles non-serializable types via default=str."""

        data = {"created_at": datetime(2024, 1, 15, 10, 30, 0)}
        result = json_response(data)
        parsed = json.loads(result[0].text)
        assert "2024-01-15" in parsed["created_at"]


@pytest.mark.django_db
class TestGetModelAdmin:
    """Tests for get_model_admin function."""

    def test_finds_registered_model(self):
        """Test finding a model registered in admin."""
        model, model_admin = get_model_admin("author")
        assert model is not None
        assert model is Author
        assert model_admin is not None

    def test_returns_none_for_unregistered_model(self):
        """Test that unregistered model returns (None, None)."""
        model, model_admin = get_model_admin("nonexistent_model")
        assert model is None
        assert model_admin is None


@pytest.mark.django_db
class TestCreateMockRequest:
    """Tests for create_mock_request function."""

    def test_returns_http_request(self):
        """Test that create_mock_request returns HttpRequest."""
        request = create_mock_request()
        assert isinstance(request, HttpRequest)

    def test_default_user_is_none(self):
        """Test that default user is None (for backwards compat with no-auth API)."""
        request = create_mock_request()
        assert request.user is None

    def test_accepts_user_parameter(self):
        """Test that user parameter is properly set."""
        uid = unique_id()
        user = User.objects.create_user(
            username=f"testuser_{uid}",
            email=f"test_{uid}@example.com",
            password="testpass",
        )
        request = create_mock_request(user)
        assert request.user == user
        assert request.user.username == f"testuser_{uid}"

    def test_request_has_required_attributes(self):
        """Test that MCPRequest has all required attributes for permission checks."""
        request = create_mock_request()
        # Verify it's an MCPRequest instance
        assert isinstance(request, MCPRequest)
        # Verify all required attributes exist
        assert hasattr(request, "user")
        assert hasattr(request, "method")
        assert hasattr(request, "path")
        assert hasattr(request, "META")
        assert hasattr(request, "GET")
        assert hasattr(request, "POST")
        # Verify default values
        assert request.method == "GET"
        assert request.path == "/"
        assert isinstance(request.META, dict)
        assert isinstance(request.GET, dict)
        assert isinstance(request.POST, dict)


@pytest.mark.django_db
class TestCheckPermission:
    """Tests for check_permission function."""

    def test_returns_true_when_no_model_admin(self):
        """Test that None model_admin returns True."""
        request = create_mock_request()
        assert check_permission(request, None, "view") is True

    def test_returns_true_for_unknown_action(self):
        """Test that unknown action returns True."""
        request = create_mock_request()
        _, model_admin = get_model_admin("author")
        assert check_permission(request, model_admin, "unknown_action") is True

    def test_view_permission_with_superuser(self):
        """Test view permission with superuser."""
        uid = unique_id()
        user = User.objects.create_superuser(
            username=f"admin_view_{uid}",
            email=f"admin_view_{uid}@example.com",
            password="admin",
        )
        request = create_mock_request(user)
        _, model_admin = get_model_admin("author")
        assert check_permission(request, model_admin, "view") is True

    def test_view_permission_with_anonymous_user(self):
        """Test view permission with anonymous user."""
        request = create_mock_request(AnonymousUser())  # Explicit anonymous user
        _, model_admin = get_model_admin("author")
        # Anonymous user should not have view permission
        result = check_permission(request, model_admin, "view")
        # Django admin by default denies anonymous users
        assert result is False


@pytest.mark.django_db
class TestGetExposedModels:
    """Tests for get_exposed_models function."""

    def test_returns_list(self):
        """Test that get_exposed_models returns a list."""
        result = get_exposed_models()
        assert isinstance(result, list)

    def test_returns_tuples_of_name_and_admin(self):
        """Test that result contains tuples of (model_name, model_admin)."""
        result = get_exposed_models()
        if result:  # At least one exposed model should exist
            name, admin = result[0]
            assert isinstance(name, str)
            assert admin is not None

    def test_includes_author_model(self):
        """Test that Author model with mcp_expose=True is included."""
        result = get_exposed_models()
        model_names = [name for name, _ in result]
        assert "author" in model_names


@pytest.mark.django_db
class TestSerializeInstance:
    """Tests for serialize_instance function."""

    def test_serializes_simple_model(self):
        """Test serializing a simple model instance."""
        uid = unique_id()
        author = Author.objects.create(name=f"Test Author {uid}", email=f"test_{uid}@example.com")
        result = serialize_instance(author)
        assert isinstance(result, dict)
        assert result["name"] == f"Test Author {uid}"
        assert result["email"] == f"test_{uid}@example.com"

    def test_serializes_model_with_foreign_key(self):
        """Test serializing model with FK relationship."""
        uid = unique_id()
        author = Author.objects.create(name=f"FK Author {uid}", email=f"fk_{uid}@example.com", bio="Test bio")
        article = Article.objects.create(title="Test Article", content="Test content", author=author)
        result = serialize_instance(article)
        assert isinstance(result, dict)
        assert result["title"] == "Test Article"
        # FK should be serialized (either as ID or string)
        assert "author" in result


@pytest.mark.django_db
class TestGetModelName:
    """Tests for get_model_name function."""

    def test_returns_lowercase_name(self):
        """Test that get_model_name returns lowercase model name."""
        result = get_model_name(Author)
        assert result == "author"


class TestSafeErrorMessage:
    """Tests for safe_error_message function."""

    def test_integrity_error_returns_generic_message(self):
        exc = IntegrityError('duplicate key value violates unique constraint "auth_user_username_key"')
        result = safe_error_message(exc)
        assert result == "Data integrity error: a constraint was violated"
        assert "auth_user" not in result
        assert "username" not in result

    def test_field_error_returns_generic_message(self):
        exc = FieldError("Cannot resolve keyword 'foo' into field. Choices are: id, name, email")
        result = safe_error_message(exc)
        assert result == "Invalid field in request"
        assert "foo" not in result
        assert "Choices" not in result

    def test_operational_error_returns_generic_message(self):
        exc = OperationalError(
            'could not connect to server: Connection refused\n\tIs the server running on host "10.0.0.1"'
        )
        result = safe_error_message(exc)
        assert result == "A database error occurred"
        assert "10.0.0.1" not in result

    def test_validation_error_returns_generic_message(self):
        exc = DjangoValidationError("This field is required.")
        result = safe_error_message(exc)
        assert result == "Validation error"

    def test_value_error_returns_generic_message(self):
        exc = ValueError("invalid literal for int() with base 10: 'abc'")
        result = safe_error_message(exc)
        assert result == "Invalid input data"
        assert "int()" not in result

    def test_type_error_returns_generic_message(self):
        exc = TypeError("expected str, got NoneType")
        result = safe_error_message(exc)
        assert result == "Invalid input data"
        assert "NoneType" not in result

    def test_unknown_exception_returns_generic_message(self):
        exc = RuntimeError("something unexpected at /app/secret/path.py:42")
        result = safe_error_message(exc)
        assert result == "An internal error occurred"
        assert "/app/secret" not in result

    def test_logs_real_exception(self, caplog):
        with caplog.at_level(logging.ERROR, logger="django_admin_mcp"):
            exc = RuntimeError("detailed internal info")
            safe_error_message(exc)

        assert "detailed internal info" in caplog.text


class TestSanitizePydanticErrors:
    """Tests for sanitize_pydantic_errors function."""

    def test_strips_input_and_ctx_fields(self):
        raw_errors = [
            {
                "type": "string_type",
                "loc": ("body", "name"),
                "msg": "Input should be a valid string",
                "input": {"secret": "value"},
                "ctx": {"error": "internal detail"},
                "url": "https://errors.pydantic.dev/...",
            }
        ]
        result = sanitize_pydantic_errors(raw_errors)
        assert len(result) == 1
        assert result[0] == {
            "field": "body.name",
            "message": "Input should be a valid string",
        }
        assert "input" not in str(result)
        assert "ctx" not in str(result)
        assert "url" not in str(result)

    def test_handles_empty_errors(self):
        result = sanitize_pydantic_errors([])
        assert result == []

    def test_handles_missing_fields(self):
        raw_errors = [{"msg": "some error"}]
        result = sanitize_pydantic_errors(raw_errors)
        assert result == [{"field": "", "message": "some error"}]
