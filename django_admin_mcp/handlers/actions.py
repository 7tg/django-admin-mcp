"""
Action handlers for django-admin-mcp.

This module provides handlers for admin actions and bulk operations
extracted from the mixin module.
"""

import json
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.admin import actions as admin_module_actions
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    async_check_permission,
    format_form_errors,
    get_admin_form_class,
    get_model_admin,
    json_response,
    normalize_fk_fields,
)
from django_admin_mcp.protocol.types import TextContent


def _get_action_info(action) -> dict[str, Any]:
    """
    Extract information about a ModelAdmin action.

    Args:
        action: A ModelAdmin action (callable or string).

    Returns:
        Dictionary with 'name' and 'description' keys.
    """
    if callable(action):
        name = getattr(action, "__name__", str(action))
        description = getattr(action, "short_description", name.replace("_", " ").title())
        return {"name": name, "description": str(description)}
    return {"name": str(action), "description": str(action)}


def _permission_error(operation: str, model_name: str) -> list[TextContent]:
    """
    Return a permission denied error response.

    Args:
        operation: The operation that was denied.
        model_name: The model name the operation was attempted on.

    Returns:
        List containing a TextContent with error JSON.
    """
    return json_response(
        {
            "error": f"Permission denied: cannot {operation} {model_name}",
            "code": "permission_denied",
        }
    )


def _log_action(user, obj, action_flag: int, change_message: str = ""):
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

    # Deferred import: Django models require app registry to be ready
    from django.contrib.admin.models import LogEntry  # noqa: PLC0415
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    content_type = ContentType.objects.get_for_model(obj)

    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=content_type.pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=action_flag,
        change_message=change_message,
    )


async def handle_actions(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    List available admin actions for a model.

    Returns list of actions with:
    - name (function name)
    - description (short_description attribute)

    Args:
        model_name: The name of the model to list actions for.
        arguments: Dictionary of arguments (currently unused).
        request: HttpRequest with user for permission checking.

    Returns:
        List of TextContent with JSON response containing available actions.
    """
    try:
        model, model_admin = get_model_admin(model_name)

        if model is None:
            return json_response({"error": f"Model {model_name} not registered"})

        # Check view permission
        if not await async_check_permission(request, model_admin, "view"):
            return _permission_error("view", model_name)

        actions_info = []

        if model_admin:
            # Get actions from admin
            admin_actions = getattr(model_admin, "actions", []) or []

            for action in admin_actions:
                action_info = _get_action_info(action)
                actions_info.append(action_info)

            # Add built-in delete_selected if not disabled
            if admin_actions is not None:  # None means actions are disabled
                # Check if delete_selected is available
                if hasattr(admin_module_actions, "delete_selected"):
                    actions_info.append(
                        {
                            "name": "delete_selected",
                            "description": "Delete selected items",
                        }
                    )

        return json_response(
            {
                "model": model_name,
                "count": len(actions_info),
                "actions": actions_info,
            }
        )
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_action(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Execute an admin action on selected objects.

    Args:
        model_name: The name of the model to execute action on.
        arguments: Dictionary containing:
            - action: str action name
            - ids: list of primary keys to act on
        request: HttpRequest with user for permission checking and action execution.

    Returns:
        List of TextContent with JSON response containing action result.
    """
    try:
        model, model_admin = get_model_admin(model_name)

        if model is None:
            return json_response({"error": f"Model {model_name} not registered"})

        # Check change permission (actions typically modify data)
        if not await async_check_permission(request, model_admin, "change"):
            return _permission_error("change", model_name)

        action_name = arguments.get("action")
        ids = arguments.get("ids", [])

        if not action_name:
            return json_response({"error": "action parameter is required"})

        if not ids:
            return json_response({"error": "ids parameter is required"})

        @sync_to_async
        def execute_action():
            queryset = model.objects.filter(pk__in=ids)
            count = queryset.count()

            if count == 0:
                return {"error": "No objects found with the provided IDs"}

            # Handle built-in delete_selected
            if action_name == "delete_selected":
                deleted_count = queryset.count()
                queryset.delete()
                return {
                    "success": True,
                    "action": action_name,
                    "affected_count": deleted_count,
                    "message": f"Deleted {deleted_count} {model._meta.verbose_name_plural}",
                }

            # Find custom action in admin
            if model_admin:
                admin_actions = getattr(model_admin, "actions", []) or []
                for action in admin_actions:
                    if callable(action) and getattr(action, "__name__", "") == action_name:
                        # Execute the action
                        result = action(model_admin, request, queryset)
                        return {
                            "success": True,
                            "action": action_name,
                            "affected_count": count,
                            "message": f"Executed {action_name} on {count} objects",
                            "result": str(result) if result else None,
                        }

            return {"error": f"Action '{action_name}' not found"}

        result = await execute_action()
        return json_response(result)
    except Exception as e:
        return json_response({"error": str(e)})


async def handle_bulk(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
) -> list[TextContent]:
    """
    Bulk create/update/delete operations with form validation.

    Uses Django admin's form system for validation when ModelAdmin is available.
    Falls back to auto-generated ModelForm otherwise.

    Args:
        model_name: The name of the model to perform bulk operations on.
        arguments: Dictionary containing:
            - operation: 'create' | 'update' | 'delete'
            - items: list of dicts (data for create/update, or ids for delete)
        request: HttpRequest with user for permission checking.

    Returns:
        List of TextContent with JSON response containing operation results.
    """
    try:
        model, model_admin = get_model_admin(model_name)

        if model is None:
            return json_response({"error": f"Model {model_name} not registered"})

        operation = arguments.get("operation")
        items = arguments.get("items", [])

        if not operation:
            return json_response({"error": "operation parameter is required"})

        if operation not in ["create", "update", "delete"]:
            return json_response({"error": "operation must be 'create', 'update', or 'delete'"})

        # Check permission for the bulk operation
        permission_map = {
            "create": "add",
            "update": "change",
            "delete": "delete",
        }
        required_permission = permission_map.get(operation)
        if required_permission and not await async_check_permission(request, model_admin, required_permission):
            return _permission_error(required_permission, model_name)

        user = request.user if hasattr(request, "user") else None
        # Don't use AnonymousUser for logging
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def execute_bulk():
            # Deferred import: Django models require app registry to be ready
            from django.contrib.admin.models import ADDITION, CHANGE, DELETION  # noqa: PLC0415
            from django.forms.models import model_to_dict  # noqa: PLC0415

            results = {"success": [], "errors": []}

            if operation == "create":
                # Get form class for create operations
                form_class = get_admin_form_class(model, model_admin, request, obj=None)

                for i, item_data in enumerate(items):
                    try:
                        # Normalize FK field names
                        normalized_data = normalize_fk_fields(model, item_data)
                        form = form_class(data=normalized_data)
                        if not form.is_valid():
                            results["errors"].append(
                                {
                                    "index": i,
                                    "error": "Validation failed",
                                    "validation_errors": format_form_errors(form.errors),
                                }
                            )
                            continue

                        obj = form.save()
                        _log_action(
                            user=user,
                            obj=obj,
                            action_flag=ADDITION,
                            change_message="Bulk created via MCP",
                        )
                        results["success"].append({"index": i, "id": obj.pk, "created": True})
                    except Exception as e:
                        results["errors"].append({"index": i, "error": str(e)})

            elif operation == "update":
                for i, item in enumerate(items):
                    try:
                        obj_id = item.get("id")
                        data = item.get("data", {})
                        if not obj_id:
                            results["errors"].append({"index": i, "error": "id is required for update"})
                            continue

                        obj = model.objects.get(pk=obj_id)

                        # Normalize FK field names
                        normalized_data = normalize_fk_fields(model, data)

                        # Get form class for this instance
                        form_class = get_admin_form_class(model, model_admin, request, obj=obj)

                        # Merge existing data with updates
                        existing_data = model_to_dict(obj)
                        merged_data = {**existing_data, **normalized_data}

                        form = form_class(data=merged_data, instance=obj)
                        if not form.is_valid():
                            results["errors"].append(
                                {
                                    "index": i,
                                    "error": "Validation failed",
                                    "validation_errors": format_form_errors(form.errors),
                                }
                            )
                            continue

                        obj = form.save()
                        _log_action(
                            user=user,
                            obj=obj,
                            action_flag=CHANGE,
                            change_message=f"Bulk updated via MCP: {json.dumps(data, default=str)}",
                        )
                        results["success"].append({"index": i, "id": obj_id, "updated": True})
                    except model.DoesNotExist:
                        results["errors"].append(
                            {
                                "index": i,
                                "error": f"Object with id {obj_id} not found",
                            }
                        )
                    except Exception as e:
                        results["errors"].append({"index": i, "error": str(e)})

            elif operation == "delete":
                ids = items if isinstance(items, list) else []
                for i, obj_id in enumerate(ids):
                    try:
                        obj = model.objects.get(pk=obj_id)
                        _log_action(
                            user=user,
                            obj=obj,
                            action_flag=DELETION,
                            change_message="Bulk deleted via MCP",
                        )
                        obj.delete()
                        results["success"].append({"index": i, "id": obj_id, "deleted": True})
                    except model.DoesNotExist:
                        results["errors"].append(
                            {
                                "index": i,
                                "error": f"Object with id {obj_id} not found",
                            }
                        )
                    except Exception as e:
                        results["errors"].append({"index": i, "error": str(e)})

            return {
                "operation": operation,
                "total_items": len(items),
                "success_count": len(results["success"]),
                "error_count": len(results["errors"]),
                "results": results,
            }

        result = await execute_bulk()
        return json_response(result)
    except Exception as e:
        return json_response({"error": str(e)})
