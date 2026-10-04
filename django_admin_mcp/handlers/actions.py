"""
Action handlers for django-admin-mcp.

This module provides handlers for admin actions and bulk operations
extracted from the mixin module.
"""

from collections.abc import Mapping
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.admin.utils import model_format_dict
from django.db import transaction
from django.http import HttpRequest, HttpResponse, QueryDict, StreamingHttpResponse

from django_admin_mcp.handlers.action_files import (
    ActionFileTooLargeError,
    _http_response_body,
    _response_header,
    serialize_action_result,
)
from django_admin_mcp.handlers.base import (
    OperationDenied,
    _log_action,
    attach_messages,
    get_admin_queryset,
    json_response,
    require_deletable,
    safe_error_message,
)
from django_admin_mcp.handlers.bulk import _get_bulk_user
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model
from django_admin_mcp.protocol.types import TextContent

# Truncation limit for intermediate confirmation page content in responses
_CONFIRMATION_PAGE_MAX_CHARS = 4000

# Changelist POST fields set from the validated call; confirmation_data must
# not override them (e.g. swapping in a selection outside the scoped queryset)
_RESERVED_ACTION_FIELDS = frozenset({"action", "index", "select_across", "_selected_action"})


def _prepare_action_request(
    request: HttpRequest,
    action_name: str,
    ids: list[Any],
    confirm: bool,
    confirmation_data: dict[str, Any],
) -> None:
    """
    Populate request.POST with Django's standard admin action fields.

    Actions written for the admin changelist read the selection and
    confirmation state from ``request.POST``. When ``confirm`` is set, the
    common confirmation markers (``post``, ``confirm``, ``apply``) and any
    ``confirmation_data`` fields are included so Django-style two-step
    actions execute instead of rendering their intermediate page.
    """
    post = QueryDict(mutable=True)
    post["action"] = action_name
    post["index"] = "0"
    post["select_across"] = "0"
    post.setlist("_selected_action", [str(pk) for pk in ids])
    if confirm:
        post["post"] = "yes"  # delete_selected-style marker
        post["confirm"] = "yes"
        post["apply"] = "yes"
        for key, value in confirmation_data.items():
            if key not in _RESERVED_ACTION_FIELDS:
                post[key] = str(value)
    post._mutable = False
    request.method = "POST"
    request.POST = post  # type: ignore[assignment]


def _is_html_response(result: Any) -> bool:
    """True when an action returned an HTML page (intermediate confirmation)."""
    if not isinstance(result, (HttpResponse, StreamingHttpResponse)):
        return False
    content_type = _response_header(result, "Content-Type") or getattr(result, "content_type", "") or ""
    return content_type.split(";")[0].strip().lower() == "text/html"


def _confirmation_response(result: Any, action_name: str) -> dict[str, Any]:
    """Build the requires_confirmation payload from an intermediate HTML page."""
    render = getattr(result, "render", None)
    if callable(render) and getattr(result, "is_rendered", True) is False:
        result = render()

    try:
        body = _http_response_body(result)
        content = body.decode(getattr(result, "charset", None) or "utf-8", errors="replace")
    except ActionFileTooLargeError:
        content = ""
    if len(content) > _CONFIRMATION_PAGE_MAX_CHARS:
        content = content[:_CONFIRMATION_PAGE_MAX_CHARS] + "..."

    return {
        "success": False,
        "requires_confirmation": True,
        "action": action_name,
        "message": (
            f"Action '{action_name}' requires confirmation. Call again with "
            "confirm=true (and optional confirmation_data for extra form fields) to execute."
        ),
        "confirmation_page": {"content_type": "text/html", "content": content},
    }


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


def _format_action_description(description: Any, format_dict: Mapping[str, Any]) -> str:
    """
    Interpolate an action description the way the admin changelist does.

    Django formats descriptions with ``model_format_dict(opts)``, which is
    what turns the built-in ``"Delete selected %(verbose_name_plural)s"``
    into ``"Delete selected articles"`` (issue #119). A description that is
    not a valid format string is returned unchanged rather than failing the
    whole listing.
    """
    text = str(description)
    try:
        return text % format_dict
    except (KeyError, TypeError, ValueError):
        return text


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
    - description (short_description attribute, formatted with the model's
      verbose names as in the admin changelist)

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
            format_dict = model_format_dict(model._meta)
            for name, (_func, name, description) in actions_dict.items():
                actions_info.append({"name": name, "description": _format_action_description(description, format_dict)})

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
        confirm = bool(arguments.get("confirm", False))
        confirmation_data = arguments.get("confirmation_data") or {}

        if not action_name:
            return json_response({"error": "action parameter is required"})

        if not ids:
            return json_response({"error": "ids parameter is required"})

        @sync_to_async
        def execute_action():
            # Check delete permission before any ID lookup to avoid leaking existence.
            # has_delete_permission requires request.user; requests without one fall
            # through to the decorator-level permission handling.
            if action_name == "delete_selected":
                user = getattr(request, "user", None)
                if model_admin is not None and user is not None and not model_admin.has_delete_permission(request):
                    return {
                        "error": f"Permission denied: cannot delete {model_name}",
                        "code": "permission_denied",
                    }

            # Scope selected rows to the admin queryset (proxy filters, soft-delete, etc.)
            queryset = get_admin_queryset(model, model_admin, request).filter(pk__in=ids)
            count = queryset.count()

            if count == 0:
                return {"error": "No objects found with the provided IDs"}

            # Handle built-in delete_selected directly (it renders HTML in Django).
            # Mirror the changelist pipeline: LogEntry per object and the
            # admin's delete_queryset() hook (issue #95)
            if action_name == "delete_selected":
                from django.contrib.admin.models import DELETION  # noqa: PLC0415

                deleted_count = count
                user = _get_bulk_user(request)
                # Same refusals as Django's delete_selected: object-level
                # permission, undeletable cascades, protected objects
                require_deletable(request, model_admin, queryset, model_name)
                with transaction.atomic():
                    for obj in queryset:
                        _log_action(user=user, obj=obj, action_flag=DELETION, change_message="Deleted via MCP")
                    if model_admin is not None:
                        model_admin.delete_queryset(request, queryset)
                    else:
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
                    # Provide Django's standard action POST fields so two-step
                    # confirmation actions work over MCP (issue #63)
                    _prepare_action_request(request, action_name, ids, confirm, confirmation_data)
                    result = func(model_admin, request, queryset)
                    if _is_html_response(result):
                        # Intermediate confirmation page — report the two-step flow
                        return _confirmation_response(result, action_name)
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
        # Actions often report their outcome only via message_user() (issue #119)
        return json_response(attach_messages(result, request, model_admin))
    except OperationDenied as e:
        return json_response(e.payload)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})
