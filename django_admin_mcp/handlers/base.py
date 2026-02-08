"""
Base handler utilities for django-admin-mcp.

This module provides shared utilities extracted from the mixin module
for use across handler implementations.
"""

from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.admin.sites import site
from django.db import models
from django.forms import ModelForm
from django.forms.models import model_to_dict, modelform_factory
from django.http import HttpRequest
from pydantic import TypeAdapter

from django_admin_mcp.protocol.types import TextContent

# Pydantic TypeAdapter for JSON serialization - reused across all json_response calls
_JSON_ADAPTER = TypeAdapter(dict[str, Any])


class MCPRequest(HttpRequest):
    """
    Lightweight request object for MCP permission checks.

    Provides the minimal HttpRequest interface needed for Django admin
    permission methods without using test utilities.
    """

    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.method = "GET"
        self.path = "/"
        self.META = {}
        self.GET = {}
        self.POST = {}


def json_response(data: dict) -> list[TextContent]:
    """
    Wrap response data in TextContent list.

    Args:
        data: Dictionary to serialize as JSON response.

    Returns:
        List containing a single TextContent with JSON-serialized data.
    """
    # Use Pydantic TypeAdapter for JSON serialization with better type safety
    json_bytes = _JSON_ADAPTER.dump_json(data, by_alias=True)
    return [TextContent(text=json_bytes.decode("utf-8"))]


def get_model_admin(model_name: str) -> tuple[type[models.Model] | None, Any | None]:
    """
    Find ModelAdmin by model name.

    Looks up the model in MCPAdminMixin._registered_models (populated at
    runtime when MCPAdminMixin-based admins are instantiated).

    Args:
        model_name: The lowercase model name to search for.

    Returns:
        Tuple of (Model, ModelAdmin) if found, or (None, None) if not found.
    """
    # First check MCPAdminMixin's registry (populated at runtime when admins are instantiated)
    # Late import to avoid circular dependency: mixin imports handlers, handlers need mixin
    from django_admin_mcp.mixin import MCPAdminMixin  # noqa: PLC0415

    if model_name in MCPAdminMixin._registered_models:
        info = MCPAdminMixin._registered_models[model_name]
        return info["model"], info.get("admin")

    return None, None


def create_mock_request(user=None) -> HttpRequest:
    """
    Create a mock request object for permission checking.

    Args:
        user: Django User instance or None.

    Returns:
        HttpRequest with user set (None if not provided).
    """
    return MCPRequest(user)


def check_permission(request: HttpRequest, model_admin: Any, action: str) -> bool:
    """
    Check Django admin permission for action (synchronous version).

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    if model_admin is None:
        return True  # No admin = no permission restrictions

    # If no user is set on request, skip permission checks (backwards compat)
    user = getattr(request, "user", None)
    if user is None:
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


async def async_check_permission(request: HttpRequest, model_admin: Any, action: str) -> bool:
    """
    Check Django admin permission for action (async version).

    Wraps the synchronous permission check to be safe in async context.

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    return await sync_to_async(check_permission)(request, model_admin, action)


def get_exposed_models() -> list[tuple[str, Any]]:
    """
    Get all models registered via MCPAdminMixin that have mcp_expose=True.

    Returns:
        List of (model_name, model_admin) tuples for exposed models.
    """
    from django_admin_mcp.mixin import MCPAdminMixin  # noqa: PLC0415

    return [
        (name, info.get("admin"))
        for name, info in MCPAdminMixin._registered_models.items()
        if getattr(info.get("admin"), "mcp_expose", False)
    ]


def serialize_instance(instance: models.Model, model_admin: Any = None) -> dict:
    """
    Serialize a Django model instance to dict with field filtering.

    Respects field visibility configuration from ModelAdmin:
    1. mcp_fields: MCP-specific list of fields to include (takes precedence)
    2. mcp_exclude_fields: MCP-specific list of fields to exclude (takes precedence)
    3. fields: Django admin's fields list (fallback if mcp_fields not set)
    4. exclude: Django admin's exclude list (fallback if mcp_exclude_fields not set)

    Field filtering prevents sensitive data exposure in MCP responses.

    Args:
        instance: The Django model instance to serialize.
        model_admin: Optional ModelAdmin with field configuration.

    Returns:
        Dictionary representation of the model instance with filtered fields.
    """
    # Determine which fields to include/exclude
    fields_to_include = None
    fields_to_exclude = None

    if model_admin is not None:
        # 1. Check for MCP-specific field configuration (takes precedence)
        if hasattr(model_admin, "mcp_fields") and model_admin.mcp_fields is not None:
            fields_to_include = model_admin.mcp_fields
        elif hasattr(model_admin, "fields") and model_admin.fields is not None:
            # 2. Fallback to Django admin's fields
            fields_to_include = model_admin.fields

        if hasattr(model_admin, "mcp_exclude_fields") and model_admin.mcp_exclude_fields is not None:
            fields_to_exclude = model_admin.mcp_exclude_fields
        elif hasattr(model_admin, "exclude") and model_admin.exclude is not None:
            # 2. Fallback to Django admin's exclude
            fields_to_exclude = model_admin.exclude

    # Use model_to_dict with fields/exclude parameters
    obj_dict = model_to_dict(instance, fields=fields_to_include, exclude=fields_to_exclude)

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
    # model_name is always a string for concrete models
    return model._meta.model_name or ""


def get_admin_form_class(
    model: type[models.Model],
    model_admin: Any,
    request: HttpRequest,
    obj: models.Model | None = None,
) -> type:
    """
    Get the form class to use for a model.

    Uses ModelAdmin's get_form() method if available, which respects
    the admin's form, fields, exclude, and readonly_fields attributes.
    Falls back to modelform_factory for auto-generated form.

    Args:
        model: The Django model class.
        model_admin: The ModelAdmin instance (may be None).
        request: HttpRequest for form customization.
        obj: Existing instance for update operations (None for create).

    Returns:
        Form class to use for validation.
    """
    if model_admin is not None:
        # Check if request.user is valid (has has_perm method)
        user = getattr(request, "user", None)
        if user is not None and hasattr(user, "has_perm"):
            try:
                return model_admin.get_form(request, obj=obj)
            except (AttributeError, TypeError):
                # Fall back if get_form fails
                pass

        # If ModelAdmin has a custom form class, use it directly
        form_class = getattr(model_admin, "form", None)
        if form_class is not None:
            if form_class is not ModelForm and issubclass(form_class, ModelForm):
                return form_class

    return modelform_factory(model, fields="__all__")


def normalize_fk_fields(model: type[models.Model], data: dict) -> dict:
    """
    Normalize foreign key field names for form compatibility.

    Converts field_id (database column names) to field (model field names)
    for foreign key fields, enabling backward compatibility with clients
    that use the _id suffix.

    Args:
        model: The Django model class.
        data: Dictionary of field:value pairs.

    Returns:
        New dictionary with normalized field names.
    """
    # Get FK field names and their db column names
    fk_fields = {}
    for field in model._meta.get_fields():
        if hasattr(field, "attname") and hasattr(field, "name"):
            # FK fields have attname like 'author_id' and name like 'author'
            if field.attname != field.name:
                fk_fields[field.attname] = field.name

    # Normalize the data
    normalized = {}
    for key, value in data.items():
        if key in fk_fields:
            # Convert field_id to field
            normalized[fk_fields[key]] = value
        else:
            normalized[key] = value

    return normalized


def format_form_errors(form_errors: dict) -> dict:
    """
    Format Django form errors into a structured JSON-serializable format.

    Args:
        form_errors: The form.errors dictionary (ErrorDict).

    Returns:
        Dictionary with:
        - errors: list of error dicts with 'field' and 'messages' keys
        - error_count: total number of errors
        - fields_with_errors: list of field names that have errors
    """
    errors_list = []
    for field, messages in form_errors.items():
        errors_list.append(
            {
                "field": field,
                "messages": [str(msg) for msg in messages],
            }
        )

    return {
        "errors": errors_list,
        "error_count": sum(len(e["messages"]) for e in errors_list),
        "fields_with_errors": list(form_errors.keys()),
    }


def check_inline_permission(
    inline_class: type,
    parent_admin: Any,
    request: HttpRequest,
    parent_obj: models.Model,
    action: str,
) -> bool:
    """
    Check permission for inline operations (synchronous version).

    Instantiates the inline class and calls its permission methods.
    Inline permission methods take the parent object as context.

    Args:
        inline_class: The inline class from parent_admin.inlines.
        parent_admin: The parent ModelAdmin instance.
        request: HttpRequest with user set.
        parent_obj: The parent model instance being edited.
        action: One of 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    if inline_class is None or parent_admin is None:
        return True

    # If no user is set on request, skip permission checks (backwards compat)
    user = getattr(request, "user", None)
    if user is None:
        return True

    permission_methods = {
        "add": "has_add_permission",
        "change": "has_change_permission",
        "delete": "has_delete_permission",
    }

    method_name = permission_methods.get(action)
    if not method_name:
        return True

    try:
        # Instantiate the inline class with parent model and admin site
        inline_instance = inline_class(parent_admin.model, site)
        permission_method = getattr(inline_instance, method_name, None)
        if permission_method and callable(permission_method):
            # Inline permission methods take (request, obj) where obj is parent
            return permission_method(request, parent_obj)
    except Exception:
        # If instantiation or permission check fails, deny access for safety
        return False

    return True
