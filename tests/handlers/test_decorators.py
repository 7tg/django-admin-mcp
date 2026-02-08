"""
Tests for django_admin_mcp.handlers.decorators module.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers.base import create_mock_request
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid):
    return User.objects.create_superuser(
        username=f"admin_{uid}",
        email=f"admin_{uid}@example.com",
        password="admin",
    )


@sync_to_async
def create_regular_user(uid):
    return User.objects.create_user(
        username=f"user_{uid}",
        email=f"user_{uid}@example.com",
        password="password",
    )


@require_registered_model
async def dummy_handler(model_name, arguments, request, *, model, model_admin):
    """Test handler that returns the injected model info."""
    return {"model_name": model_name, "model": model, "model_admin": model_admin}


@require_registered_model
@require_permission("view")
async def view_handler(model_name, arguments, request, *, model, model_admin):
    """Test handler requiring view permission."""
    return {"success": True, "model_name": model_name}


@require_registered_model
@require_permission("delete")
async def delete_handler(model_name, arguments, request, *, model, model_admin):
    """Test handler requiring delete permission."""
    return {"success": True, "model_name": model_name}


@pytest.mark.django_db
class TestRequireRegisteredModel:
    """Tests for require_registered_model decorator."""

    @pytest.mark.asyncio
    async def test_returns_error_for_unregistered_model(self):
        """Decorator returns a JSON error when model is not registered."""
        result = await dummy_handler("nonexistent_model", {}, create_mock_request())
        parsed = json.loads(result[0].text)
        assert parsed == {"error": "Model nonexistent_model not registered"}

    @pytest.mark.asyncio
    async def test_injects_model_and_model_admin_for_registered_model(self):
        """Decorator resolves and injects model/model_admin for a registered model."""
        result = await dummy_handler("author", {}, create_mock_request())
        assert result["model"] is not None
        assert result["model"].__name__ == "Author"
        assert result["model_admin"] is not None

    @pytest.mark.asyncio
    async def test_passes_through_arguments(self):
        """Decorator passes model_name, arguments, and request to the wrapped function."""
        args = {"key": "value"}
        result = await dummy_handler("author", args, create_mock_request())
        assert result["model_name"] == "author"

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self):
        """Decorator preserves the wrapped function's name and docstring."""
        assert dummy_handler.__name__ == "dummy_handler"
        assert "Test handler" in dummy_handler.__doc__


@pytest.mark.django_db(transaction=True)
class TestRequirePermission:
    """Tests for require_permission decorator."""

    @pytest.mark.asyncio
    async def test_allows_superuser(self):
        """Superuser passes any permission check."""
        user = await create_superuser(unique_id())
        request = create_mock_request(user)
        result = await view_handler("author", {}, request)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_denies_user_without_permission(self):
        """User without required permission gets denied."""
        user = await create_regular_user(unique_id())
        request = create_mock_request(user)
        result = await delete_handler("author", {}, request)
        parsed = json.loads(result[0].text)
        assert parsed["error"] == "Permission denied: cannot delete author"
        assert parsed["code"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_error_format_includes_action_and_model(self):
        """Permission error message includes the action and model name."""
        user = await create_regular_user(unique_id())
        request = create_mock_request(user)
        result = await view_handler("author", {}, request)
        parsed = json.loads(result[0].text)
        assert "view" in parsed["error"]
        assert "author" in parsed["error"]

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self):
        """Decorator preserves the wrapped function's name and docstring."""
        assert view_handler.__name__ == "view_handler"
        assert "view permission" in view_handler.__doc__

    @pytest.mark.asyncio
    async def test_stacks_with_require_registered_model(self):
        """Permission decorator works correctly when stacked with model decorator."""
        user = await create_superuser(unique_id())
        request = create_mock_request(user)
        # Unregistered model - should get model error, not permission error
        result = await view_handler("nonexistent", {}, request)
        parsed = json.loads(result[0].text)
        assert "not registered" in parsed["error"]
