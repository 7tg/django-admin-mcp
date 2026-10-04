"""
Bulk create/update/delete handlers for django-admin-mcp.

Each item is validated and saved through the same admin pipeline as the
single-object CRUD handlers, with per-item error reporting.
"""

from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    OperationDenied,
    _log_action,
    _serialize_data_for_log,
    attach_messages,
    get_admin_queryset,
    is_missing_id,
    json_response,
    require_deletable,
    require_object_permission,
    safe_error_message,
)
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model
from django_admin_mcp.handlers.write import WriteRejected, save_through_admin
from django_admin_mcp.protocol.types import TextContent


def _get_bulk_user(request):
    """Extract authenticated user from request for audit logging."""
    user = request.user if hasattr(request, "user") else None
    if user and not user.is_authenticated:
        user = None
    return user


def _bulk_response(operation, items, results, request, model_admin):
    """
    Build standardized bulk operation response.

    Messages the admin queued with message_user() while the items were
    processed ride along under "messages", unless the admin opts out with
    mcp_return_messages = False (issues #118, #119).
    """
    data = {
        "operation": operation,
        "total_items": len(items),
        "success_count": len(results["success"]),
        "error_count": len(results["errors"]),
        "results": results,
    }
    return json_response(attach_messages(data, request, model_admin))


@require_registered_model
@require_permission("add")
async def handle_bulk_create(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """Bulk create operations with form validation."""

    @sync_to_async
    def execute():
        from django.contrib.admin.models import ADDITION  # noqa: PLC0415

        items = arguments.get("items", [])
        user = _get_bulk_user(request)
        results: dict[str, list] = {"success": [], "errors": []}

        for i, item_data in enumerate(items):
            try:
                with transaction.atomic():
                    # Same admin pipeline as handle_create: save_model() and
                    # save_related() (issues #95, #118)
                    obj, _ = save_through_admin(model, model_admin, request, item_data)
                    _log_action(user=user, obj=obj, action_flag=ADDITION, change_message="Bulk created via MCP")
                results["success"].append({"index": i, "id": obj.pk, "created": True})
            except WriteRejected as e:
                results["errors"].append({"index": i, **e.payload})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("create", items, results, request, model_admin)


@require_registered_model
@require_permission("change")
async def handle_bulk_update(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """Bulk update operations with form validation."""

    @sync_to_async
    def execute():
        from django.contrib.admin.models import CHANGE  # noqa: PLC0415

        items = arguments.get("items", [])
        user = _get_bulk_user(request)
        results: dict[str, list] = {"success": [], "errors": []}

        for i, item in enumerate(items):
            try:
                obj_id = item.get("id")
                data = item.get("data", {})
                if is_missing_id(obj_id):
                    results["errors"].append({"index": i, "error": "id is required for update"})
                    continue

                # An item is {id, data}; anything else would be ignored, so
                # it is refused (inlines are not available in bulk)
                stray = sorted(set(item) - {"id", "data"})
                if stray:
                    results["errors"].append({"index": i, "error": f"Invalid item key: {stray[0]}"})
                    continue

                # Scoped to the admin queryset (issue #88)
                obj = get_admin_queryset(model, model_admin, request).get(pk=obj_id)
                require_object_permission(request, model_admin, "change", obj, model_name)

                with transaction.atomic():
                    # Same admin pipeline and guards as handle_update:
                    # save_model() and save_related() (issues #95, #118).
                    # Fields the caller did not send keep the instance's
                    # values (issue #114)
                    obj, _ = save_through_admin(model, model_admin, request, data, obj=obj)
                    # Same redacting serializer as the single-update path (issue #104)
                    data_json = _serialize_data_for_log(data, model_admin=model_admin)
                    _log_action(
                        user=user,
                        obj=obj,
                        action_flag=CHANGE,
                        change_message=f"Bulk updated via MCP: {data_json}",
                    )
                results["success"].append({"index": i, "id": obj_id, "updated": True})
            except model.DoesNotExist:
                results["errors"].append({"index": i, "error": f"Object with id {obj_id} not found"})
            except (OperationDenied, WriteRejected) as e:
                results["errors"].append({"index": i, **e.payload})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("update", items, results, request, model_admin)


@require_registered_model
@require_permission("delete")
async def handle_bulk_delete(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """Bulk delete operations."""

    @sync_to_async
    def execute():
        from django.contrib.admin.models import DELETION  # noqa: PLC0415

        items = arguments.get("items", [])
        user = _get_bulk_user(request)
        results: dict[str, list] = {"success": [], "errors": []}

        for i, obj_id in enumerate(items):
            try:
                # Scoped to the admin queryset (issue #88)
                obj = get_admin_queryset(model, model_admin, request).get(pk=obj_id)
                require_deletable(request, model_admin, [obj], model_name)
                with transaction.atomic():
                    _log_action(user=user, obj=obj, action_flag=DELETION, change_message="Bulk deleted via MCP")
                    # Same admin pipeline as handle_delete: delete_model() when
                    # a ModelAdmin is available (issue #95)
                    if model_admin is not None:
                        model_admin.delete_model(request, obj)
                    else:
                        obj.delete()
                results["success"].append({"index": i, "id": obj_id, "deleted": True})
            except model.DoesNotExist:
                results["errors"].append({"index": i, "error": f"Object with id {obj_id} not found"})
            except OperationDenied as e:
                results["errors"].append({"index": i, **e.payload})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("delete", items, results, request, model_admin)


@require_registered_model
async def handle_bulk(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """
    Bulk create/update/delete operations dispatcher.

    Routes to handle_bulk_create, handle_bulk_update, or handle_bulk_delete
    based on the operation argument.

    Args:
        model_name: The name of the model to perform bulk operations on.
        arguments: Dictionary containing:
            - operation: 'create' | 'update' | 'delete'
            - items: list of dicts (data for create/update, or ids for delete)
        request: HttpRequest with user for permission checking.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing operation results.
    """
    operation = arguments.get("operation")

    if not operation:
        return json_response({"error": "operation parameter is required"})

    handlers = {
        "create": handle_bulk_create,
        "update": handle_bulk_update,
        "delete": handle_bulk_delete,
    }

    handler = handlers.get(operation)
    if not handler:
        return json_response({"error": "operation must be 'create', 'update', or 'delete'"})

    # A non-list items must be an explicit error, not a success-shaped no-op
    # (issue #110)
    if not isinstance(arguments.get("items"), list):
        return json_response({"error": "items must be a list"})

    return await handler(model_name, arguments, request)
