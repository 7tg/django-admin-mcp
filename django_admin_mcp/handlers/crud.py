"""
CRUD operation handlers for django-admin-mcp.

This module provides async handler functions for Create, Read, Update,
Delete operations extracted from the mixin module.
"""

from typing import Any

from asgiref.sync import sync_to_async
from django.db import models, transaction
from django.db.models import Q
from django.http import HttpRequest
from pydantic import TypeAdapter

from django_admin_mcp.handlers.base import (
    OperationDenied,
    _log_action,
    _serialize_data_for_log,
    attach_messages,
    check_related_view_permission,
    get_admin_queryset,
    get_computed_entries,
    is_missing_id,
    json_response,
    require_deletable,
    require_object_permission,
    resolve_related_admin,
    safe_error_message,
    serialize_computed_fields,
    serialize_instance,
    validate_pagination,
)
from django_admin_mcp.handlers.decorators import require_permission, require_registered_model
from django_admin_mcp.handlers.filters import (  # noqa: F401  (re-exported for backwards compatibility)
    SAFE_FILTER_LOOKUPS,
    InvalidFilterError,
    _build_filter_query,
    _queryable_field_names,
    resolve_list_filters,
)
from django_admin_mcp.handlers.inlines import _get_inline_data
from django_admin_mcp.handlers.write import WriteRejected, save_through_admin
from django_admin_mcp.protocol.types import CreateResponse, ListResponse, TextContent, UpdateResponse


def _build_search_query(model: type[models.Model], search_fields: list[str], search_term: str) -> Q:
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
        # Strip admin operator prefixes (^, =, @) — this fallback only runs
        # without a ModelAdmin, where get_search_results is unavailable
        if field.startswith(("^", "=", "@")):
            field = field[1:]
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


@require_registered_model
@require_permission("view")
async def handle_list(
    model_name: str, arguments: dict[str, Any], request: HttpRequest, *, model, model_admin
) -> list[TextContent]:
    """
    List model instances with filtering, search, ordering.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - limit: int (default 100) - Maximum items to return
            - offset: int (default 0) - Number of items to skip
            - filters: dict of filter criteria: own fields, relation paths
              declared in the admin's list_filter / date_hierarchy, and
              SimpleListFilter parameter names (see handlers/filters.py)
            - search: str search term
            - order_by: list of field names (prefix with - for descending)
        request: HttpRequest with user for permission checking.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing count, total_count, results.
    """
    try:
        limit, offset, pagination_error = validate_pagination(arguments)
        if pagination_error:
            return json_response({"error": pagination_error})

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

        # Validate filters and caller-supplied ordering up front: rejected
        # parameters must produce an error response, never a success-shaped
        # unfiltered result (issue #111). Resolution runs in a sync context
        # because admin list filters may query the database for their choices.
        resolved_filters = None
        if filters:
            try:
                resolved_filters = await sync_to_async(resolve_list_filters)(model, filters, model_admin, request)
            except InvalidFilterError as e:
                return json_response({"error": str(e)})

        if order_by:
            # Caller-supplied ordering is limited to visible fields, like filters
            queryable = _queryable_field_names(model, model_admin)
            invalid_order = [o for o in order_by if not isinstance(o, str) or o.removeprefix("-") not in queryable]
            if invalid_order:
                names = ", ".join(f"'{o}'" for o in invalid_order)
                return json_response({"error": f"Invalid order_by — unknown fields: {names}"})

        @sync_to_async
        def get_objects():
            queryset = get_admin_queryset(model, model_admin, request)

            # Apply filters
            if resolved_filters is not None:
                queryset = resolved_filters.apply(queryset)

            # Apply search through the admin's own pipeline: it handles the
            # ^/=/@ operator prefixes, field__lookup forms, and custom
            # get_search_results overrides (issue #103)
            if search:
                if model_admin is not None:
                    queryset, may_have_duplicates = model_admin.get_search_results(request, queryset, search)
                    if may_have_duplicates:
                        queryset = queryset.distinct()
                elif search_fields:
                    queryset = queryset.filter(_build_search_query(model, search_fields, search))

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

            # Computed list_display columns ride along under "_computed" (issue #117)
            computed_entries = get_computed_entries(model_admin, "list_display", request)
            rows = []
            for obj in queryset:
                row = serialize_instance(obj, model_admin)
                computed = serialize_computed_fields(obj, model_admin, computed_entries)
                if computed:
                    row["_computed"] = computed
                rows.append(row)
            return total_count, rows

        total_count, results = await get_objects()

        response = ListResponse(
            count=len(results),
            total_count=total_count,
            results=results,
        )

        return [TextContent(text=response.model_dump_json(indent=2))]
    except Exception as e:
        return json_response({"error": safe_error_message(e)})


@require_registered_model
@require_permission("view")
async def handle_get(
    model_name: str, arguments: dict[str, Any], request: HttpRequest, *, model, model_admin
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
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing the object data.
    """
    try:
        obj_id = arguments.get("id")
        include_inlines = arguments.get("include_inlines", False)
        include_related = arguments.get("include_related", False)

        if is_missing_id(obj_id):
            return json_response({"error": "id parameter is required"})

        @sync_to_async
        def get_object():
            obj = get_admin_queryset(model, model_admin, request).get(pk=obj_id)
            require_object_permission(request, model_admin, "view", obj, model_name)
            result = serialize_instance(obj, model_admin)

            # Computed readonly_fields entries ride along under "_computed" (issue #117)
            computed = serialize_computed_fields(
                obj, model_admin, get_computed_entries(model_admin, "readonly_fields", request, obj)
            )
            if computed:
                result["_computed"] = computed

            # Include inlines if requested
            if include_inlines and model_admin:
                result["_inlines"] = _get_inline_data(obj, model_admin, request)

            # Include related objects if requested
            if include_related:
                related_data = {}
                for field in model._meta.get_fields():
                    if hasattr(field, "related_model") and field.related_model:
                        # Reverse relations only: forward FK/O2O fields define
                        # one_to_many/one_to_one as attributes too, so the
                        # values must be tested, and only auto-created
                        # non-concrete rels have get_accessor_name (issue #93)
                        if (field.one_to_many or field.one_to_one) and field.auto_created and not field.concrete:
                            accessor_name = field.get_accessor_name()
                            if hasattr(obj, accessor_name):
                                related_manager = getattr(obj, accessor_name)
                                if hasattr(related_manager, "all"):
                                    # Omit related models the user may not view,
                                    # and honor their admin queryset scope (issue #91)
                                    related_model = field.related_model
                                    related_admin = resolve_related_admin(related_model)
                                    if not check_related_view_permission(request, related_admin):
                                        continue
                                    related_qs = related_manager.all() & get_admin_queryset(
                                        related_model, related_admin, request
                                    )
                                    related_data[accessor_name] = [
                                        serialize_instance(r, related_admin)
                                        for r in related_qs[:10]  # Limit to 10
                                    ]
                if related_data:
                    result["_related"] = related_data

            return result

        obj_dict = await get_object()

        # Use Pydantic's JSON encoder for proper serialization
        adapter = TypeAdapter(dict[str, Any])
        return [TextContent(text=adapter.dump_json(obj_dict, indent=2).decode("utf-8"))]
    except model.DoesNotExist:  # type: ignore[attr-defined]
        return json_response({"error": f"{model_name} not found"})
    except OperationDenied as e:
        return json_response(e.payload)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})


@require_registered_model
@require_permission("add")
async def handle_create(
    model_name: str, arguments: dict[str, Any], request: HttpRequest, *, model, model_admin
) -> list[TextContent]:
    """
    Create new model instance with form validation.

    Runs the admin's own save pipeline (see ``handlers/write.py``): the
    ModelAdmin's form, ``save_model()``, then ``save_related()`` with the
    inline formsets. Falls back to an auto-generated ModelForm without a
    ModelAdmin.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - data: dict of field:value pairs for the new instance
            - inlines: optional dict of inline rows to create with it
        request: HttpRequest with user for permission checking and logging.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing:
        - On success: success, id, object, (optional) inlines
        - On validation error: error, code, validation_errors
        - On an inline error: error, code, inlines.errors; nothing is saved
    """
    try:
        data = arguments.get("data", {})
        inlines_data = arguments.get("inlines") or {}
        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def create_object():
            # Deferred import: Django models require app registry to be ready
            from django.contrib.admin.models import ADDITION  # noqa: PLC0415

            # Save, inline writes, and logging are one transaction
            with transaction.atomic():
                obj, inlines_result = save_through_admin(model, model_admin, request, data, inlines=inlines_data)

                # Log the action - use Pydantic for serialization (truncated for log size)
                change_message = [f"Created via MCP: {_serialize_data_for_log(data, model_admin=model_admin)}"]
                if inlines_data:
                    change_message.append(f"Created inlines: {list(inlines_data.keys())}")
                _log_action(
                    user=user,
                    obj=obj,
                    action_flag=ADDITION,
                    change_message=" | ".join(change_message),
                )

            return obj.pk, serialize_instance(obj, model_admin), inlines_result

        result_id, result_data, inlines_result = await create_object()

        response = CreateResponse(
            success=True,
            id=result_id,
            object=result_data,
            inlines=inlines_result if inlines_result and any(inlines_result.values()) else None,
        )

        return json_response(attach_messages(response.model_dump(), request, model_admin), indent=2)
    except WriteRejected as e:
        return json_response(e.payload)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})


@require_registered_model
@require_permission("change")
async def handle_update(
    model_name: str, arguments: dict[str, Any], request: HttpRequest, *, model, model_admin
) -> list[TextContent]:
    """
    Update model instance with form validation.

    Runs the admin's own save pipeline (see ``handlers/write.py``). Only the
    fields the caller sent change; inline operations are validated with the
    parent and saved in the same transaction.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - id: int or str (primary key) - Required
            - data: dict of field:value pairs to update
            - inlines: optional dict for inline updates
        request: HttpRequest with user for permission checking and logging.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing:
        - On success: success, object, (optional) inlines
        - On validation error: error, code, validation_errors
        - On an inline error: error, code, inlines.errors; nothing is saved
    """
    try:
        obj_id = arguments.get("id")
        data = arguments.get("data", {})
        inlines_data = arguments.get("inlines") or {}

        if is_missing_id(obj_id):
            return json_response({"error": "id parameter is required"})

        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def update_object():
            # Deferred import: Django models require app registry to be ready
            from django.contrib.admin.models import CHANGE  # noqa: PLC0415

            # Scope the lookup to the admin queryset so rows hidden from the
            # changelist can't be updated by pk (issue #88)
            obj = get_admin_queryset(model, model_admin, request).get(pk=obj_id)
            require_object_permission(request, model_admin, "change", obj, model_name)

            # Save, inline writes, and logging are one transaction
            with transaction.atomic():
                obj, inlines_result = save_through_admin(
                    model, model_admin, request, data, obj=obj, inlines=inlines_data
                )

                # Log the action - use Pydantic for serialization (truncated for log size)
                change_message = []
                if data:
                    data_json = _serialize_data_for_log(data, model_admin=model_admin)
                    change_message.append(f"Changed via MCP: {data_json}")
                if inlines_data:
                    change_message.append(f"Updated inlines: {list(inlines_data.keys())}")
                _log_action(
                    user=user,
                    obj=obj,
                    action_flag=CHANGE,
                    change_message=(" | ".join(change_message) if change_message else "Updated via MCP"),
                )

            return serialize_instance(obj, model_admin), inlines_result

        obj_dict, inlines_result = await update_object()

        response = UpdateResponse(
            success=True,
            object=obj_dict,
            inlines=inlines_result if inlines_result and any(inlines_result.values()) else None,
        )

        return json_response(attach_messages(response.model_dump(), request, model_admin), indent=2)
    except model.DoesNotExist:  # type: ignore[attr-defined]
        return json_response({"error": f"{model_name} not found"})
    except (OperationDenied, WriteRejected) as e:
        return json_response(e.payload)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})


@require_registered_model
@require_permission("delete")
async def handle_delete(
    model_name: str, arguments: dict[str, Any], request: HttpRequest, *, model, model_admin
) -> list[TextContent]:
    """
    Delete model instance.

    Args:
        model_name: The lowercase name of the model.
        arguments: Dictionary containing:
            - id: int or str (primary key) - Required
        request: HttpRequest with user for permission checking and logging.
        model: Resolved Django model class (injected by decorator).
        model_admin: Resolved ModelAdmin instance (injected by decorator).

    Returns:
        List of TextContent with JSON response containing success and message.
    """
    try:
        obj_id = arguments.get("id")

        if is_missing_id(obj_id):
            return json_response({"error": "id parameter is required"})

        user = getattr(request, "user", None)
        if user and not user.is_authenticated:
            user = None

        @sync_to_async
        def delete_object():
            # Deferred import: Django models require app registry to be ready
            from django.contrib.admin.models import DELETION  # noqa: PLC0415

            # Scope the lookup to the admin queryset so rows hidden from the
            # changelist can't be deleted by pk (issue #88)
            obj = get_admin_queryset(model, model_admin, request).get(pk=obj_id)
            # Object-level permission, plus the cascade/protection checks of
            # the admin's delete view
            require_deletable(request, model_admin, [obj], model_name)
            obj_repr = str(obj)

            # Wrap logging and deletion in transaction for atomicity
            with transaction.atomic():
                # Log the action BEFORE deleting (so we still have the object)
                _log_action(
                    user=user,
                    obj=obj,
                    action_flag=DELETION,
                    change_message="Deleted via MCP",
                )

                # Use ModelAdmin.delete_model() when available for the standard Django admin pipeline
                if model_admin is not None:
                    model_admin.delete_model(request, obj)
                else:
                    obj.delete()
            return obj_repr

        await delete_object()

        return json_response(
            attach_messages({"success": True, "message": f"{model_name} deleted successfully"}, request, model_admin)
        )
    except model.DoesNotExist:  # type: ignore[attr-defined]
        return json_response({"error": f"{model_name} not found"})
    except OperationDenied as e:
        return json_response(e.payload)
    except Exception as e:
        return json_response({"error": safe_error_message(e)})
