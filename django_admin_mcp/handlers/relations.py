"""
Relation and history handlers for django-admin-mcp.

This module provides async handlers for fetching related objects,
viewing change history, and providing autocomplete suggestions.
"""

from typing import Any

from asgiref.sync import sync_to_async
from django.db.models import Q
from django.http import HttpRequest

from django_admin_mcp.handlers.base import get_model_admin, json_response, serialize_instance
from django_admin_mcp.protocol.types import TextContent


async def handle_related(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Fetch related objects for a model instance.

    Supports ForeignKey, ManyToMany, and reverse relations.
    Use describe_<model> to discover available relations.

    Args:
        model_name: The lowercase model name.
        arguments: Dictionary containing:
            - id: int or str (primary key of the instance)
            - relation: str (field name of the relation to fetch)
            - limit: int (default 100, max items for many relations)
            - offset: int (default 0, pagination offset)
        request: HttpRequest with user set for permission checking.

    Returns:
        List of TextContent with JSON response containing:
        - For many relations: relation, type, count, total_count, results
        - For single relations: relation, type, result
        - For simple values: relation, type, value
        - For errors: error message
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    obj_id = arguments.get("id")
    relation = arguments.get("relation")
    limit = arguments.get("limit", 100)
    offset = arguments.get("offset", 0)

    if not obj_id:
        return json_response({"error": "id parameter is required"})

    if not relation:
        return json_response({"error": "relation parameter is required"})

    @sync_to_async
    def get_related():
        try:
            obj = model.objects.get(pk=obj_id)
        except (model.DoesNotExist, ValueError, TypeError):
            return {"error": f"{model_name} not found"}

        # Check if the relation exists
        if not hasattr(obj, relation):
            # Try to find in related fields
            for field in model._meta.get_fields():
                if hasattr(field, "get_accessor_name"):
                    if field.get_accessor_name() == relation:
                        break
            else:
                return {"error": f"Relation '{relation}' not found on model"}

        related_attr = getattr(obj, relation)

        # Handle different relation types
        if hasattr(related_attr, "all"):
            # Many relation (ManyToMany, reverse FK)
            queryset = related_attr.all()
            total_count = queryset.count()
            related_objects = queryset[offset : offset + limit]
            return {
                "relation": relation,
                "type": "many",
                "count": len(related_objects),
                "total_count": total_count,
                "results": [serialize_instance(r) for r in related_objects],
            }
        elif hasattr(related_attr, "_meta"):
            # Single relation (FK, OneToOne)
            return {
                "relation": relation,
                "type": "single",
                "result": serialize_instance(related_attr),
            }
        else:
            # It's a simple field value
            return {
                "relation": relation,
                "type": "value",
                "value": str(related_attr),
            }

    result = await get_related()
    return json_response(result)


async def handle_history(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Get change history for a model instance from Django's LogEntry.

    Returns LogEntry records showing who made what changes and when.

    Args:
        model_name: The lowercase model name.
        arguments: Dictionary containing:
            - id: int or str (primary key of the instance)
            - limit: int (default 50, max history entries to return)
        request: HttpRequest with user set for permission checking.

    Returns:
        List of TextContent with JSON response containing:
        - model: model name
        - object_id: the instance ID
        - current_repr: string representation of the instance
        - count: number of history entries returned
        - history: list of history entries with action, time, user, etc.
        - For errors: error message
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    obj_id = arguments.get("id")
    limit = arguments.get("limit", 50)

    if not obj_id:
        return json_response({"error": "id parameter is required"})

    @sync_to_async
    def get_history():
        from django.contrib.admin.models import (
            ADDITION,
            CHANGE,
            DELETION,
            LogEntry,
        )
        from django.contrib.contenttypes.models import ContentType

        # Verify the object exists
        try:
            obj = model.objects.get(pk=obj_id)
        except (model.DoesNotExist, ValueError, TypeError):
            return {"error": f"{model_name} not found"}

        # Get content type for this model
        content_type = ContentType.objects.get_for_model(model)

        # Get log entries for this object
        log_entries = LogEntry.objects.filter(
            content_type=content_type,
            object_id=str(obj_id),
        ).order_by("-action_time")[:limit]

        action_names = {
            ADDITION: "created",
            CHANGE: "changed",
            DELETION: "deleted",
        }

        history = []
        for entry in log_entries:
            history.append(
                {
                    "action": action_names.get(entry.action_flag, "unknown"),
                    "action_flag": entry.action_flag,
                    "action_time": entry.action_time.isoformat(),
                    "user": entry.user.username if entry.user else None,
                    "user_id": entry.user_id,
                    "change_message": entry.change_message,
                    "object_repr": entry.object_repr,
                }
            )

        return {
            "model": model._meta.model_name,
            "object_id": obj_id,
            "current_repr": str(obj),
            "count": len(history),
            "history": history,
        }

    result = await get_history()
    return json_response(result)


async def handle_autocomplete(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Search for autocomplete suggestions.

    Useful for populating FK/M2M field widgets. Uses search_fields
    from the ModelAdmin if available, otherwise searches CharField
    and TextField fields.

    Args:
        model_name: The lowercase model name.
        arguments: Dictionary containing:
            - term: str (search term to match)
            - limit: int (default 10, max suggestions to return)
        request: HttpRequest with user set for permission checking.

    Returns:
        List of TextContent with JSON response containing:
        - model: model name
        - term: the search term used
        - count: number of results
        - results: list of {id, text} objects for autocomplete
        - For errors: error message
    """
    model, model_admin = get_model_admin(model_name)

    if model is None:
        return json_response({"error": f"Model '{model_name}' not found"})

    term = arguments.get("term", "")
    limit = arguments.get("limit", 10)

    @sync_to_async
    def search_autocomplete():
        queryset = model.objects.all()

        # Use admin's search_fields if available
        search_fields = []
        if model_admin:
            search_fields = list(getattr(model_admin, "search_fields", []))

        # If no search_fields, try to find text fields to search
        if not search_fields:
            for field in model._meta.get_fields():
                if hasattr(field, "get_internal_type"):
                    if field.get_internal_type() in ("CharField", "TextField"):
                        search_fields.append(field.name)
                        if len(search_fields) >= 3:  # Limit to 3 fields
                            break

        # Apply search if term provided
        if term and search_fields:
            q = Q()
            for field in search_fields:
                q |= Q(**{f"{field}__icontains": term})
            queryset = queryset.filter(q)

        # Apply ordering if admin has it
        if model_admin:
            ordering = getattr(model_admin, "ordering", None)
            if ordering:
                queryset = queryset.order_by(*ordering)

        # Limit results
        results = queryset[:limit]

        # Return simplified format suitable for autocomplete
        autocomplete_results = []
        for obj in results:
            autocomplete_results.append(
                {
                    "id": obj.pk,
                    "text": str(obj),
                }
            )

        return {
            "model": model_name,
            "term": term,
            "count": len(autocomplete_results),
            "results": autocomplete_results,
        }

    try:
        result = await search_autocomplete()
        return json_response(result)
    except Exception as e:
        return json_response({"error": str(e)})
