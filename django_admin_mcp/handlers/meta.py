"""
Metadata operation handlers for django-admin-mcp.

This module provides handlers for model metadata and discovery operations:
- handle_describe: Get model schema and admin configuration
- handle_find_models: Discover MCP-exposed models
"""

from typing import Any

from django.db import models
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    async_check_permission,
    json_response,
)
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model
from django_admin_mcp.protocol.types import TextContent


def _get_field_metadata(field) -> dict[str, Any]:
    """
    Extract comprehensive metadata from a Django model field.

    Args:
        field: A Django model field instance.

    Returns:
        Dictionary containing field metadata including:
        - name, type, verbose_name
        - required status
        - max_length, help_text, choices (if applicable)
        - relationship info (related_model, on_delete)
        - primary_key, unique, editable flags
    """
    metadata = {
        "name": field.name,
        "type": getattr(field, "get_internal_type", lambda: "Unknown")(),
        "verbose_name": str(getattr(field, "verbose_name", field.name)),
    }

    # Required status
    null_allowed = getattr(field, "null", False)
    blank_allowed = getattr(field, "blank", False)
    has_default = getattr(field, "has_default", lambda: False)()
    metadata["required"] = not null_allowed and not blank_allowed and not has_default

    # Common field attributes
    if hasattr(field, "max_length") and field.max_length:
        metadata["max_length"] = field.max_length

    if hasattr(field, "help_text") and field.help_text:
        metadata["help_text"] = str(field.help_text)

    if hasattr(field, "choices") and field.choices:
        metadata["choices"] = [{"value": choice[0], "label": str(choice[1])} for choice in field.choices]

    if hasattr(field, "default") and field.default is not models.fields.NOT_PROVIDED:
        # Handle callable defaults
        default_val = field.default
        if callable(default_val):
            metadata["has_default"] = True
        else:
            metadata["default"] = default_val

    # Relationship info
    if hasattr(field, "related_model") and field.related_model:
        metadata["related_model"] = field.related_model._meta.model_name
        metadata["related_app"] = field.related_model._meta.app_label

    if hasattr(field, "remote_field") and field.remote_field:
        if hasattr(field.remote_field, "on_delete"):
            metadata["on_delete"] = field.remote_field.on_delete.__name__

    # Primary key
    if getattr(field, "primary_key", False):
        metadata["primary_key"] = True

    # Unique
    if getattr(field, "unique", False):
        metadata["unique"] = True

    # Editable
    if hasattr(field, "editable"):
        metadata["editable"] = field.editable

    return metadata


def _model_matches_query(query: str | None, model_name: str, verbose_name: str) -> bool:
    """
    Check if a model matches the search query.

    Args:
        query: Search query string (case-insensitive).
        model_name: The model's internal name.
        verbose_name: The model's verbose/display name.

    Returns:
        True if query is empty or matches model_name/verbose_name.
    """
    if not query:
        return True
    query_lower = query.lower()
    return query_lower in model_name.lower() or query_lower in verbose_name.lower()


@require_registered_model
@require_permission("view")
async def handle_describe(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """
    Get model metadata/schema.

    Returns information about:
    - Model fields (name, type, required, choices)
    - Relationships (foreign keys, many-to-many)
    - Admin configuration (list_display, search_fields, etc.)
    - Available inlines

    Args:
        model_name: The name of the model to describe.
        arguments: Handler arguments (currently unused for describe).
        request: HttpRequest for permission checking.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List containing TextContent with JSON-serialized model metadata.
    """
    try:
        # Collect field metadata
        fields = []
        relationships = []

        for field in model._meta.get_fields():
            field_meta = _get_field_metadata(field)

            # Categorize as regular field or relationship
            if field_meta.get("related_model"):
                relationships.append(field_meta)
            elif hasattr(field, "get_internal_type"):
                fields.append(field_meta)

        # Collect admin configuration
        admin_config = {}
        if model_admin:
            admin_config["list_display"] = list(getattr(model_admin, "list_display", []))
            admin_config["list_filter"] = list(getattr(model_admin, "list_filter", []))
            admin_config["search_fields"] = list(getattr(model_admin, "search_fields", []))
            admin_config["ordering"] = list(getattr(model_admin, "ordering", []))
            admin_config["readonly_fields"] = list(getattr(model_admin, "readonly_fields", []))

            # Get fieldsets if defined
            fieldsets = getattr(model_admin, "fieldsets", None)
            if fieldsets:
                admin_config["fieldsets"] = [
                    {
                        "name": fs[0] or "General",
                        "fields": list(fs[1].get("fields", [])),
                        "classes": list(fs[1].get("classes", [])),
                    }
                    for fs in fieldsets
                ]

            # Get date_hierarchy if defined
            date_hierarchy = getattr(model_admin, "date_hierarchy", None)
            if date_hierarchy:
                admin_config["date_hierarchy"] = date_hierarchy

            # Get inlines info
            inlines = getattr(model_admin, "inlines", [])
            if inlines:
                admin_config["inlines"] = [
                    {
                        "model": inline.model._meta.model_name,
                        "fk_name": getattr(inline, "fk_name", None),
                    }
                    for inline in inlines
                    if hasattr(inline, "model")
                ]

        result = {
            "model_name": model_name,
            "verbose_name": str(model._meta.verbose_name),
            "verbose_name_plural": str(model._meta.verbose_name_plural),
            "app_label": model._meta.app_label,
            "fields": fields,
            "relationships": relationships,
            "admin_config": admin_config,
        }

        return json_response(result)
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_find_models(
    model_name: str,  # Not used, but kept for consistent handler signature
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Discover available MCP-exposed models.

    Searches through Django admin registry for models with mcp_expose=True.

    Arguments:
        query: optional str to filter model names (case-insensitive)

    Args:
        model_name: Unused (kept for consistent handler signature).
        arguments: Handler arguments containing optional 'query' filter.
        request: HttpRequest for permission checking.

    Returns:
        List containing TextContent with JSON-serialized models info:
        - count: Number of matching models
        - models: List of model info dicts with:
            - model_name, verbose_name, verbose_name_plural
            - app_label, tools_exposed
    """
    try:
        from django_admin_mcp.mixin import MCPAdminMixin  # noqa: PLC0415

        query = arguments.get("query", "")

        # Collect candidate models from MCPAdminMixin registry
        candidates = []
        for model_name_lower, info in MCPAdminMixin._registered_models.items():
            model = info["model"]
            model_admin = info.get("admin")
            verbose_name = str(model._meta.verbose_name)
            verbose_name_plural = str(model._meta.verbose_name_plural)

            # Filter by query if provided
            if not _model_matches_query(query, model_name_lower, verbose_name):
                continue

            candidates.append(
                {
                    "model_admin": model_admin,
                    "model_name": model_name_lower,
                    "verbose_name": verbose_name,
                    "verbose_name_plural": verbose_name_plural,
                    "app_label": model._meta.app_label,
                    "tools_exposed": True,
                }
            )

        # Filter by user permissions (async operation)
        models_info = []
        for candidate in candidates:
            if await async_check_permission(request, candidate["model_admin"], "view"):
                # Remove model_admin before adding to response
                models_info.append(
                    {
                        "model_name": candidate["model_name"],
                        "verbose_name": candidate["verbose_name"],
                        "verbose_name_plural": candidate["verbose_name_plural"],
                        "app_label": candidate["app_label"],
                        "tools_exposed": candidate["tools_exposed"],
                    }
                )

        return json_response(
            {
                "count": len(models_info),
                "models": models_info,
            }
        )
    except Exception as e:
        return json_response({"error": str(e)})
