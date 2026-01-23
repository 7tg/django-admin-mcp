"""
Base handler utilities for django-admin-mcp.

This module provides shared utilities extracted from the mixin module
for use across handler implementations.
"""

import json
from typing import Any

from django.contrib.admin.sites import site
from django.db import models
from django.forms.models import model_to_dict
from django.http import HttpRequest

from ..protocol.types import TextContent


def json_response(data: dict) -> list[TextContent]:
    """
    Wrap response data in TextContent list.

    Args:
        data: Dictionary to serialize as JSON response.

    Returns:
        List containing a single TextContent with JSON-serialized data.
    """
    return [TextContent(text=json.dumps(data, default=str))]


def get_model_admin(model_name: str) -> tuple[type[models.Model] | None, Any | None]:
    """
    Find ModelAdmin by model name.

    First checks MCPAdminMixin._registered_models (for runtime registrations),
    then falls back to admin.site._registry (for @admin.register() decorated classes).

    Args:
        model_name: The lowercase model name to search for.

    Returns:
        Tuple of (Model, ModelAdmin) if found, or (None, None) if not found.
    """
    # First check MCPAdminMixin's registry (populated at runtime when admins are instantiated)
    # Use late import to avoid circular dependency
    from ..mixin import MCPAdminMixin

    if model_name in MCPAdminMixin._registered_models:
        info = MCPAdminMixin._registered_models[model_name]
        return info["model"], info.get("admin")

    # Fall back to Django admin site registry
    for model, model_admin in site._registry.items():
        if model._meta.model_name == model_name:
            return model, model_admin

    return None, None


def create_mock_request(user=None) -> HttpRequest:
    """
    Create a mock request object for permission checking.

    Args:
        user: Django User instance or None (defaults to AnonymousUser).

    Returns:
        HttpRequest with user set.
    """
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = user if user else AnonymousUser()
    return request


def check_permission(request: HttpRequest, model_admin: Any, action: str) -> bool:
    """
    Check Django admin permission for action.

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    if model_admin is None:
        return True  # No admin = no permission restrictions

    # If user is not authenticated (AnonymousUser or None), permissions are not enforced
    # This maintains backwards compatibility for API tokens without users
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return True

    permission_methods = {
        "view": "has_view_permission",
        "add": "has_add_permission",
        "change": "has_change_permission",
        "delete": "has_delete_permission",
    }

    method_name = permission_methods.get(action)
    if not method_name:
        return True  # Unknown action = allow by default

    permission_method = getattr(model_admin, method_name, None)
    if permission_method and callable(permission_method):
        return permission_method(request)

    return True


def get_exposed_models() -> list[tuple[str, Any]]:
    """
    Get all models with mcp_expose=True attribute on their ModelAdmin.

    Searches through admin.site._registry for ModelAdmin classes
    that have the mcp_expose attribute set to True.

    Returns:
        List of (model_name, model_admin) tuples for exposed models.
    """
    exposed = []
    for model, model_admin in site._registry.items():
        if getattr(model_admin, "mcp_expose", False):
            model_name = model._meta.model_name
            exposed.append((model_name, model_admin))
    return exposed


def serialize_instance(instance: models.Model, model_admin: Any = None) -> dict:
    """
    Serialize a Django model instance to dict.

    Handles related fields by converting them to string representations,
    and uses json.dumps with default=str to handle datetime and other
    non-JSON-serializable types.

    Args:
        instance: The Django model instance to serialize.
        model_admin: Optional ModelAdmin (reserved for future use).

    Returns:
        Dictionary representation of the model instance.
    """
    obj_dict = model_to_dict(instance)

    # Convert non-serializable fields
    serialized = {}
    for key, value in obj_dict.items():
        if isinstance(value, models.Model):
            # Related object - convert to string
            serialized[key] = str(value)
        else:
            serialized[key] = value

    return serialized


def get_model_name(model: type[models.Model]) -> str:
    """
    Get lowercase model name from model class.

    Args:
        model: Django model class.

    Returns:
        The lowercase model name from model._meta.model_name.
    """
    return model._meta.model_name
