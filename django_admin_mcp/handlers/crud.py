"""
CRUD operation handlers for django-admin-mcp.

This module provides async handler functions for Create, Read, Update,
Delete operations extracted from the mixin module.
"""

import json
from typing import Any

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import Q
from django.http import HttpRequest

from .base import (
    async_check_permission,
    get_model_admin,
    json_response,
    serialize_instance,
)
from ..protocol.types import TextContent


def _build_filter_query(model: type[models.Model], filters: dict[str, Any]) -> Q:
    """
    Build a Q object from filter parameters.

    Supports lookups:
    - field: exact match (default)
    - field__icontains: case-insensitive contains
    - field__gte: greater than or equal
    - field__lte: less than or equal
    - field__in: value in list
    - field__isnull: is null check

    Args:
        model: The Django model class.
        filters: Dictionary of field:value filter criteria.

    Returns:
        Q object for filtering queryset.
    """
    q = Q()
    valid_fields = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}

    for key, value in filters.items():
        # Extract field name from lookup (e.g., "name__icontains" -> "name")
        field_name = key.split("__")[0]
        if field_name not in valid_fields:
            continue  # Skip invalid fields

        q &= Q(**{key: value})
    return q


def _build_search_query(
    model: type[models.Model], search_fields: list[str], search_term: str
) -> Q:
    """
    Build a Q object for searching across multiple fields.

    Args:
        model: The Django model class.
        search_fields: List of field names to search.
        search_term: The search term to match.

    Returns:
        Q object for search filtering.
    """
    if not search_term or not search_fields:
        return Q()

    q = Q()
    for field in search_fields:
        # Use icontains for text search
        lookup = f"{field}__icontains"
        q |= Q(**{lookup: search_term})
    return q


def _get_valid_ordering_fields(model: type[models.Model]) -> set:
    """
    Get the set of valid field names for ordering.

    Args:
        model: The Django model class.

    Returns:
        Set of valid field names including descending order variants.
    """
    valid_fields = set()
    for field in model._meta.get_fields():
        if hasattr(field, "name"):
            valid_fields.add(field.name)
            valid_fields.add(f"-{field.name}")  # Allow descending order
    return valid_fields


def _get_inline_data(obj: models.Model, admin: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Get inline related objects for a model instance.

    Args:
        obj: The parent model instance.
        admin: The ModelAdmin instance with inline definitions.

    Returns:
        Dictionary mapping inline model names to list of serialized instances.
    """
    inlines_data = {}

    if not admin:
        return inlines_data

    inlines = getattr(admin, "inlines", [])
    for inline_class in inlines:
        if not hasattr(inline_class, "model"):
            continue

        inline_model = inline_class.model
        fk_name = getattr(inline_class, "fk_name", None)

        # Find the FK field that points to our parent model
        fk_field = None
        for field in inline_model._meta.get_fields():
            if hasattr(field, "related_model") and field.related_model == type(obj):
                if fk_name is None or field.name == fk_name:
                    fk_field = field
                    break

        if fk_field:
            # Get related objects
            related_name = fk_field.name
            filter_kwargs = {related_name: obj}
            related_objects = inline_model.objects.filter(**filter_kwargs)
            inlines_data[inline_model._meta.model_name] = [
                serialize_instance(related_obj) for related_obj in related_objects
            ]

    return inlines_data


def _update_inlines(
    obj: models.Model, admin: Any, inlines_data: dict[str, list]
) -> dict[str, Any]:
    """
    Update inline related objects for a model instance.

    Args:
        obj: The parent model instance.
        admin: The ModelAdmin instance with inline definitions.
        inlines_data: Dictionary of inline updates per model.

    Returns:
        Results dictionary with created, updated, deleted, and errors lists.
    """
    results = {"created": [], "updated": [], "deleted": [], "errors": []}

    if not admin or not inlines_data:
        return results

    inlines = getattr(admin, "inlines", [])
    for inline_class in inlines:
        if not hasattr(inline_class, "model"):
            continue

        inline_model = inline_class.model
        inline_model_name = inline_model._meta.model_name

        if inline_model_name not in inlines_data:
            continue

        # Find the FK field
        fk_field = None
        for field in inline_model._meta.get_fields():
            if hasattr(field, "related_model") and field.related_model == type(obj):
                fk_field = field
                break

        if not fk_field:
            continue

        inline_items = inlines_data[inline_model_name]
        for item in inline_items:
            try:
                item_id = item.get("id")
                item_data = item.get("data", item)
                delete = item.get("_delete", False)

                if delete and item_id:
                    # Delete existing inline
                    inline_model.objects.filter(pk=item_id).delete()
                    results["deleted"].append({"model": inline_model_name, "id": item_id})
                elif item_id:
                    # Update existing inline
                    inline_obj = inline_model.objects.get(pk=item_id)
                    for key, value in item_data.items():
                        if key not in ["id", "_delete"]:
                            setattr(inline_obj, key, value)
                    inline_obj.save()
                    results["updated"].append({"model": inline_model_name, "id": item_id})
                else:
                    # Create new inline
                    item_data[fk_field.name] = obj
                    new_obj = inline_model.objects.create(
                        **{
                            k: v
                            for k, v in item_data.items()
                            if k not in ["id", "_delete"]
                        }
                    )
                    results["created"].append(
                        {"model": inline_model_name, "id": new_obj.pk}
                    )
            except Exception as e:
                results["errors"].append(
                    {
                        "model": inline_model_name,
                        "id": item.get("id"),
                        "error": str(e),
                    }
                )

    return results


def _log_action(user: Any, obj: models.Model, action_flag: int, change_message: str = "") -> None:
    """
    Log an action to Django's admin LogEntry.

    Args:
        user: The Django User who performed the action.
        obj: The model instance that was affected.
        action_flag: ADDITION (1), CHANGE (2), or DELETION (3).
        change_message: Description of the change.
    """
    if user is None:
        return  # Can't log without a user

    from django.contrib.admin.models import LogEntry
    from django.contrib.contenttypes.models import ContentType

    content_type = ContentType.objects.get_for_model(obj)

    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=content_type.pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=action_flag,
        change_message=change_message,
    )


async def handle_list(
    model_name: str, arguments: dict[str, Any], request: HttpRequest
) -> list[TextContent]:
    """
    List model instances with filtering, search, ordering.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - limit: int (default 100) - Maximum items to return
            - offset: int (default 0) - Number of items to skip
            - filters: dict of field:value filter criteria
            - search: str search term
            - order_by: list of field names (prefix with - for descending)
        request: HttpRequest with user for permission checking.

    Returns:
        List of TextContent with JSON response containing count, total_count, results.
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    # Check view permission
    if not await async_check_permission(request, model_admin, "view"):
        return json_response({
            "error": f"Permission denied: cannot view {model_name}",
            "code": "permission_denied",
        })

    try:
        limit = arguments.get("limit", 100)
        offset = arguments.get("offset", 0)
        filters = arguments.get("filters", {})
        search = arguments.get("search", "")
        order_by = arguments.get("order_by", [])

        # Get search fields from admin or use empty list
        search_fields = getattr(model_admin, "search_fields", []) if model_admin else []

        # Get default ordering from admin or model
        default_ordering = []
        if model_admin and hasattr(model_admin, "ordering") and model_admin.ordering:
            default_ordering = list(model_admin.ordering)
        elif model._meta.ordering:
            default_ordering = list(model._meta.ordering)

        @sync_to_async
        def get_objects():
            queryset = model.objects.all()

            # Apply filters
            if filters:
                filter_q = _build_filter_query(model, filters)
                queryset = queryset.filter(filter_q)

            # Apply search
            if search and search_fields:
                search_q = _build_search_query(model, search_fields, search)
                queryset = queryset.filter(search_q)

            # Apply ordering
            ordering = order_by if order_by else default_ordering
            if ordering:
                # Validate ordering fields
                valid_ordering = _get_valid_ordering_fields(model)
                safe_ordering = [o for o in ordering if o in valid_ordering]
                if safe_ordering:
                    queryset = queryset.order_by(*safe_ordering)

            # Get total count before pagination
            total_count = queryset.count()

            # Apply pagination
            queryset = queryset[offset : offset + limit]
            return total_count, [serialize_instance(obj) for obj in queryset]

        total_count, results = await get_objects()

        return [
            TextContent(
                text=json.dumps(
                    {
                        "count": len(results),
                        "total_count": total_count,
                        "results": results,
                    },
                    indent=2,
                    default=str,
                ),
            )
        ]
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_get(
    model_name: str, arguments: dict[str, Any], request: HttpRequest
) -> list[TextContent]:
    """
    Get single model instance by id.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - id: int or str (primary key) - Required
            - include_inlines: bool (default False) - Include inline related objects
            - include_related: bool (default False) - Include reverse FK/M2M objects
        request: HttpRequest with user for permission checking.

    Returns:
        List of TextContent with JSON response containing the object data.
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    # Check view permission
    if not await async_check_permission(request, model_admin, "view"):
        return json_response({
            "error": f"Permission denied: cannot view {model_name}",
            "code": "permission_denied",
        })

    try:
        obj_id = arguments.get("id")
        include_inlines = arguments.get("include_inlines", False)
        include_related = arguments.get("include_related", False)

        if not obj_id:
            return json_response({"error": "id parameter is required"})

        @sync_to_async
        def get_object():
            obj = model.objects.get(pk=obj_id)
            result = serialize_instance(obj, model_admin)

            # Include inlines if requested
            if include_inlines and model_admin:
                result["_inlines"] = _get_inline_data(obj, model_admin)

            # Include related objects if requested
            if include_related:
                related_data = {}
                for field in model._meta.get_fields():
                    if hasattr(field, "related_model") and field.related_model:
                        if hasattr(field, "one_to_many") or hasattr(field, "one_to_one"):
                            # Reverse relation
                            accessor_name = field.get_accessor_name()
                            if hasattr(obj, accessor_name):
                                related_manager = getattr(obj, accessor_name)
                                if hasattr(related_manager, "all"):
                                    related_data[accessor_name] = [
                                        serialize_instance(r)
                                        for r in related_manager.all()[:10]  # Limit to 10
                                    ]
                if related_data:
                    result["_related"] = related_data

            return result

        obj_dict = await get_object()

        return [TextContent(text=json.dumps(obj_dict, indent=2, default=str))]
    except model.DoesNotExist:
        return json_response({"error": f"{model_name} not found"})
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_create(
    model_name: str, arguments: dict[str, Any], request: HttpRequest
) -> list[TextContent]:
    """
    Create new model instance.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - data: dict of field:value pairs for the new instance
        request: HttpRequest with user for permission checking and logging.

    Returns:
        List of TextContent with JSON response containing success, id, and object.
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    # Check add permission
    if not await async_check_permission(request, model_admin, "add"):
        return json_response({
            "error": f"Permission denied: cannot add {model_name}",
            "code": "permission_denied",
        })

    try:
        data = arguments.get("data", {})
        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def create_object():
            from django.contrib.admin.models import ADDITION

            obj = model.objects.create(**data)

            # Log the action
            _log_action(
                user=user,
                obj=obj,
                action_flag=ADDITION,
                change_message=f"Created via MCP: {json.dumps(data, default=str)}",
            )

            return obj.pk, serialize_instance(obj, model_admin)

        obj_id, obj_dict = await create_object()

        return [
            TextContent(
                text=json.dumps(
                    {"success": True, "id": obj_id, "object": obj_dict},
                    indent=2,
                    default=str,
                ),
            )
        ]
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_update(
    model_name: str, arguments: dict[str, Any], request: HttpRequest
) -> list[TextContent]:
    """
    Update model instance.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - id: int or str (primary key) - Required
            - data: dict of field:value pairs to update
            - inlines: optional dict for inline updates
        request: HttpRequest with user for permission checking and logging.

    Returns:
        List of TextContent with JSON response containing success and object.
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    # Check change permission
    if not await async_check_permission(request, model_admin, "change"):
        return json_response({
            "error": f"Permission denied: cannot change {model_name}",
            "code": "permission_denied",
        })

    try:
        obj_id = arguments.get("id")
        data = arguments.get("data", {})
        inlines_data = arguments.get("inlines", {})

        if not obj_id:
            return json_response({"error": "id parameter is required"})

        # Validate that only model fields are being updated (protect against mass assignment)
        valid_fields = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}
        for key in data.keys():
            if key not in valid_fields:
                return json_response({"error": f"Invalid field: {key}"})

        # Check for readonly_fields - prevent updating them
        if model_admin:
            readonly_fields = set(getattr(model_admin, "readonly_fields", []))
            readonly_attempted = set(data.keys()) & readonly_fields
            if readonly_attempted:
                return json_response({
                    "error": f"Cannot update readonly fields: {', '.join(readonly_attempted)}",
                    "readonly_fields": list(readonly_attempted),
                })

        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def update_object():
            from django.contrib.admin.models import CHANGE

            obj = model.objects.get(pk=obj_id)
            # Update only the specified fields
            for key, value in data.items():
                setattr(obj, key, value)
            obj.save()

            # Handle inlines if provided
            inlines_result = {}
            if inlines_data and model_admin:
                inlines_result = _update_inlines(obj, model_admin, inlines_data)

            # Log the action
            change_message = []
            if data:
                change_message.append(f"Changed via MCP: {json.dumps(data, default=str)}")
            if inlines_data:
                change_message.append(f"Updated inlines: {list(inlines_data.keys())}")
            _log_action(
                user=user,
                obj=obj,
                action_flag=CHANGE,
                change_message=(
                    " | ".join(change_message) if change_message else "Updated via MCP"
                ),
            )

            return serialize_instance(obj, model_admin), inlines_result

        obj_dict, inlines_result = await update_object()

        response = {"success": True, "object": obj_dict}
        if inlines_result and any(inlines_result.values()):
            response["inlines"] = inlines_result

        return [TextContent(text=json.dumps(response, indent=2, default=str))]
    except model.DoesNotExist:
        return json_response({"error": f"{model_name} not found"})
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_delete(
    model_name: str, arguments: dict[str, Any], request: HttpRequest
) -> list[TextContent]:
    """
    Delete model instance.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - id: int or str (primary key) - Required
        request: HttpRequest with user for permission checking and logging.

    Returns:
        List of TextContent with JSON response containing success and message.
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    # Check delete permission
    if not await async_check_permission(request, model_admin, "delete"):
        return json_response({
            "error": f"Permission denied: cannot delete {model_name}",
            "code": "permission_denied",
        })

    try:
        obj_id = arguments.get("id")

        if not obj_id:
            return json_response({"error": "id parameter is required"})

        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def delete_object():
            from django.contrib.admin.models import DELETION

            obj = model.objects.get(pk=obj_id)
            obj_repr = str(obj)

            # Log the action BEFORE deleting (so we still have the object)
            _log_action(
                user=user,
                obj=obj,
                action_flag=DELETION,
                change_message="Deleted via MCP",
            )

            obj.delete()
            return obj_repr

        await delete_object()

        return json_response({
            "success": True,
            "message": f"{model_name} deleted successfully",
        })
    except model.DoesNotExist:
        return json_response({"error": f"{model_name} not found"})
    except Exception as e:
        return json_response({"error": str(e)})
