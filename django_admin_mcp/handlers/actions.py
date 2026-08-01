"""
Action handlers for django-admin-mcp.

This module provides handlers for admin actions and bulk operations
extracted from the mixin module.
"""

import base64
import re
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from pydantic import TypeAdapter

from django_admin_mcp.handlers.base import (
    format_form_errors,
    get_admin_form_class,
    json_response,
    normalize_fk_fields,
    safe_error_message,
)
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model
from django_admin_mcp.protocol.types import TextContent

_FILENAME_RE = re.compile(
    r"""filename\*?=(?:UTF-8'')?["']?([^";\n]+)["']?""",
    re.IGNORECASE,
)

_TEXT_CONTENT_TYPE_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
)

_TEXT_CONTENT_TYPE_EXACT = frozenset({"text/csv", "text/tsv", "application/csv"})

# Default cap for buffering download bodies into MCP JSON (override via settings).
_DEFAULT_MAX_ACTION_FILE_BYTES = 5 * 1024 * 1024


class ActionFileTooLargeError(ValueError):
    """Raised when an action file response exceeds MCP_ACTION_MAX_FILE_BYTES."""


def _max_action_file_bytes() -> int:
    from django.conf import settings  # noqa: PLC0415

    return int(getattr(settings, "MCP_ACTION_MAX_FILE_BYTES", _DEFAULT_MAX_ACTION_FILE_BYTES))


def _filename_from_content_disposition(disposition: str) -> str | None:
    """Parse a filename from a Content-Disposition header value."""
    if not disposition:
        return None
    match = _FILENAME_RE.search(disposition)
    if not match:
        return None
    return match.group(1).strip().strip("\"'")


def _is_text_content_type(content_type: str) -> bool:
    """Return True when content should be returned as UTF-8 text to MCP clients."""
    lowered = (content_type or "").split(";")[0].strip().lower()
    if any(lowered.startswith(prefix) for prefix in _TEXT_CONTENT_TYPE_PREFIXES):
        return True
    return lowered in _TEXT_CONTENT_TYPE_EXACT


def _ensure_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, memoryview):
        return chunk.tobytes()
    if isinstance(chunk, bytes):
        return chunk
    return bytes(chunk)


def _http_response_body(response: HttpResponse | StreamingHttpResponse) -> bytes:
    """Read the full body from an HttpResponse or StreamingHttpResponse.

    Raises ActionFileTooLargeError if the body exceeds MCP_ACTION_MAX_FILE_BYTES.
    """
    max_bytes = _max_action_file_bytes()
    streaming_content = getattr(response, "streaming_content", None)
    if streaming_content is not None:
        chunks: list[bytes] = []
        total = 0
        for chunk in streaming_content:
            data = _ensure_bytes(chunk)
            total += len(data)
            if total > max_bytes:
                raise ActionFileTooLargeError(
                    f"Action file response exceeds MCP_ACTION_MAX_FILE_BYTES ({max_bytes} bytes)"
                )
            chunks.append(data)
        return b"".join(chunks)

    content = _ensure_bytes(response.content)
    if len(content) > max_bytes:
        raise ActionFileTooLargeError(
            f"Action file response exceeds MCP_ACTION_MAX_FILE_BYTES ({max_bytes} bytes)"
        )
    return content


def _response_header(response: HttpResponse | StreamingHttpResponse, name: str) -> str:
    """Read a response header across Django HttpResponse variants."""
    value = response.get(name, "") or ""
    if value:
        return value
    headers = getattr(response, "headers", None)
    if headers is not None:
        return headers.get(name, "") or ""
    return ""


def serialize_action_result(result: Any) -> Any:
    """
    Serialize an admin action return value for MCP JSON responses.

    Download actions typically return ``HttpResponse`` / ``StreamingHttpResponse``.
    Those are converted to a structured file payload (UTF-8 text or base64) with
    metadata. Other values fall back to ``str(result)``; ``None`` stays ``None``.
    """
    if result is None:
        return None

    if isinstance(result, (HttpResponse, StreamingHttpResponse)):
        disposition = _response_header(result, "Content-Disposition")
        content_type = (
            _response_header(result, "Content-Type")
            or getattr(result, "content_type", None)
            or "application/octet-stream"
        )
        body = _http_response_body(result)
        filename = _filename_from_content_disposition(disposition) or "download"
        payload: dict[str, Any] = {
            "type": "file",
            "content_type": content_type,
            "filename": filename,
            "size": len(body),
            "status_code": getattr(result, "status_code", 200),
        }
        if disposition:
            payload["content_disposition"] = disposition

        if _is_text_content_type(content_type):
            try:
                payload["encoding"] = "utf-8"
                payload["content"] = body.decode("utf-8")
                return payload
            except UnicodeDecodeError:
                pass

        payload["encoding"] = "base64"
        payload["content"] = base64.b64encode(body).decode("ascii")
        return payload

    return str(result)


def _get_admin_actions(model_admin, request):
    """Get resolved actions dict from ModelAdmin, handling missing user.

    Uses Django's get_actions() which resolves string-referenced methods,
    includes globally-registered actions, and filters by permissions.
    When request.user is None, temporarily sets AnonymousUser to satisfy
    Django's permission filtering.
    """
    user = getattr(request, "user", None)
    if user is None:
        from django.contrib.auth.models import AnonymousUser  # noqa: PLC0415

        request.user = AnonymousUser()
        try:
            return model_admin.get_actions(request)
        finally:
            request.user = None
    return model_admin.get_actions(request)


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


@require_registered_model
@require_permission("view")
async def handle_actions(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
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
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing available actions.
    """
    try:
        actions_info = []

        if model_admin:
            actions_dict = _get_admin_actions(model_admin, request)
            for name, (_func, name, description) in actions_dict.items():
                actions_info.append({"name": name, "description": str(description)})

        return json_response(
            {
                "model": model_name,
                "count": len(actions_info),
                "actions": actions_info,
            }
        )
    except (LookupError, AttributeError, TypeError) as e:
        return json_response({"error": safe_error_message(e)})


@require_registered_model
@require_permission("change")
async def handle_action(
    model_name: str,
    arguments: dict[str, Any],
    request: HttpRequest,
    *,
    model,
    model_admin,
) -> list[TextContent]:
    """
    Execute an admin action on selected objects.

    Args:
        model_name: The name of the model to execute action on.
        arguments: Dictionary containing:
            - action: str action name
            - ids: list of primary keys to act on
        request: HttpRequest with user for permission checking and action execution.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing action result.
    """
    try:
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

            # Handle built-in delete_selected directly (it renders HTML in Django)
            if action_name == "delete_selected":
                deleted_count = queryset.count()
                queryset.delete()
                return {
                    "success": True,
                    "action": action_name,
                    "affected_count": deleted_count,
                    "message": f"Deleted {deleted_count} {model._meta.verbose_name_plural}",
                }

            # Look up custom action via Django's get_actions
            if model_admin:
                actions_dict = _get_admin_actions(model_admin, request)
                if action_name in actions_dict:
                    func, name, description = actions_dict[action_name]
                    result = func(model_admin, request, queryset)
                    try:
                        serialized = serialize_action_result(result)
                    except ActionFileTooLargeError as e:
                        return {"error": str(e)}
                    return {
                        "success": True,
                        "action": action_name,
                        "affected_count": count,
                        "message": f"Executed {action_name} on {count} objects",
                        "result": serialized,
                    }

            return {"error": f"Action '{action_name}' not found"}

        result = await execute_action()
        return json_response(result)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})


def _get_bulk_user(request):
    """Extract authenticated user from request for audit logging."""
    user = request.user if hasattr(request, "user") else None
    if user and not user.is_authenticated:
        user = None
    return user


def _bulk_response(operation, items, results):
    """Build standardized bulk operation response."""
    return json_response(
        {
            "operation": operation,
            "total_items": len(items),
            "success_count": len(results["success"]),
            "error_count": len(results["errors"]),
            "results": results,
        }
    )


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
        form_class = get_admin_form_class(model, model_admin, request, obj=None)

        for i, item_data in enumerate(items):
            try:
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

                with transaction.atomic():
                    obj = form.save()
                    _log_action(user=user, obj=obj, action_flag=ADDITION, change_message="Bulk created via MCP")
                results["success"].append({"index": i, "id": obj.pk, "created": True})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("create", items, results)


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
        from django.forms.models import model_to_dict  # noqa: PLC0415

        items = arguments.get("items", [])
        user = _get_bulk_user(request)
        results: dict[str, list] = {"success": [], "errors": []}
        data_adapter = TypeAdapter(dict[str, Any])

        for i, item in enumerate(items):
            try:
                obj_id = item.get("id")
                data = item.get("data", {})
                if not obj_id:
                    results["errors"].append({"index": i, "error": "id is required for update"})
                    continue

                obj = model.objects.get(pk=obj_id)

                normalized_data = normalize_fk_fields(model, data)
                form_class = get_admin_form_class(model, model_admin, request, obj=obj)

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

                with transaction.atomic():
                    obj = form.save()
                    serialized_data = data_adapter.dump_json(data, fallback=str).decode()
                    max_length = 500
                    if len(serialized_data) > max_length:
                        serialized_data = serialized_data[:max_length] + '... (truncated)"'
                    _log_action(
                        user=user,
                        obj=obj,
                        action_flag=CHANGE,
                        change_message=f"Bulk updated via MCP: {serialized_data}",
                    )
                results["success"].append({"index": i, "id": obj_id, "updated": True})
            except model.DoesNotExist:
                results["errors"].append({"index": i, "error": f"Object with id {obj_id} not found"})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("update", items, results)


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
        ids = items if isinstance(items, list) else []

        for i, obj_id in enumerate(ids):
            try:
                obj = model.objects.get(pk=obj_id)
                with transaction.atomic():
                    _log_action(user=user, obj=obj, action_flag=DELETION, change_message="Bulk deleted via MCP")
                    obj.delete()
                results["success"].append({"index": i, "id": obj_id, "deleted": True})
            except model.DoesNotExist:
                results["errors"].append({"index": i, "error": f"Object with id {obj_id} not found"})
            except Exception as e:
                results["errors"].append({"index": i, "error": safe_error_message(e)})

        return items, results

    items, results = await execute()
    return _bulk_response("delete", items, results)


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

    return await handler(model_name, arguments, request)
