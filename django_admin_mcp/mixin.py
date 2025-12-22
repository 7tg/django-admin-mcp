"""
MCP Admin Mixin for Django models

This mixin enables MCP (Model Context Protocol) functionality for Django admin classes.
When added to a ModelAdmin class, it exposes the model's CRUD operations through MCP tools.
"""

import json
from typing import Any, Dict, List, Optional, Type

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import Q
from django.forms.models import model_to_dict
from mcp.server import Server
from mcp.types import TextContent, Tool


class MCPAdminMixin:
    """
    Mixin for Django ModelAdmin classes to enable MCP functionality.

    Usage:
        from django.contrib import admin
        from django_admin_mcp import MCPAdminMixin
        from .models import MyModel

        @admin.register(MyModel)
        class MyModelAdmin(MCPAdminMixin, admin.ModelAdmin):
            pass

    This will automatically register MCP tools for:
    - list_<model_name>: List all instances
    - get_<model_name>: Get a specific instance by ID
    - create_<model_name>: Create a new instance
    - update_<model_name>: Update an existing instance
    - delete_<model_name>: Delete an instance
    """

    # Class-level registry to track registered models
    _mcp_server = None
    _registered_models = {}

    @classmethod
    def get_mcp_server(cls) -> Server:
        """Get or create the MCP server instance."""
        if cls._mcp_server is None:
            cls._mcp_server = Server("django-admin-mcp")
        return cls._mcp_server

    @classmethod
    def register_model_tools(cls, model_admin_instance):
        """Register MCP tools for a model admin instance."""
        model = model_admin_instance.model
        model_name = model._meta.model_name

        # Skip if already registered
        if model_name in cls._registered_models:
            return

        cls._registered_models[model_name] = {
            "model": model,
            "admin": model_admin_instance,
        }

    @classmethod
    def _create_mock_request(cls, user=None):
        """Create a mock request object for permission checking."""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user if user else AnonymousUser()
        return request

    @classmethod
    async def _check_permission_async(cls, admin, user, permission_type: str) -> bool:
        """
        Check if user has permission for the given operation (async version).

        Args:
            admin: The ModelAdmin instance
            user: Django User or None
            permission_type: One of 'view', 'add', 'change', 'delete'

        Returns:
            True if permission granted, False otherwise
        """
        if not admin:
            return True  # No admin = no permission restrictions

        # If no user is provided, permissions are not enforced
        # (backwards compatibility for tokens without users)
        if user is None:
            return True

        @sync_to_async
        def check_permission():
            request = cls._create_mock_request(user)

            permission_methods = {
                "view": "has_view_permission",
                "add": "has_add_permission",
                "change": "has_change_permission",
                "delete": "has_delete_permission",
            }

            method_name = permission_methods.get(permission_type)
            if not method_name:
                return True

            permission_method = getattr(admin, method_name, None)
            if permission_method and callable(permission_method):
                return permission_method(request)

            return True

        return await check_permission()

    @classmethod
    def _check_permission(cls, admin, user, permission_type: str) -> bool:
        """
        Check if user has permission for the given operation (sync version).

        Args:
            admin: The ModelAdmin instance
            user: Django User or None
            permission_type: One of 'view', 'add', 'change', 'delete'

        Returns:
            True if permission granted, False otherwise
        """
        if not admin:
            return True  # No admin = no permission restrictions

        # If no user is provided, permissions are not enforced
        # (backwards compatibility for tokens without users)
        if user is None:
            return True

        request = cls._create_mock_request(user)

        permission_methods = {
            "view": "has_view_permission",
            "add": "has_add_permission",
            "change": "has_change_permission",
            "delete": "has_delete_permission",
        }

        method_name = permission_methods.get(permission_type)
        if not method_name:
            return True

        permission_method = getattr(admin, method_name, None)
        if permission_method and callable(permission_method):
            return permission_method(request)

        return True

    @classmethod
    def _permission_error(cls, operation: str, model_name: str) -> List[TextContent]:
        """Return a permission denied error."""
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Permission denied: cannot {operation} {model_name}",
                    "code": "permission_denied"
                }),
            )
        ]

    @classmethod
    def _log_action(
        cls,
        user,
        obj,
        action_flag: int,
        change_message: str = "",
    ):
        """
        Log an action to Django's admin LogEntry.

        Args:
            user: The Django User who performed the action
            obj: The model instance that was affected
            action_flag: ADDITION (1), CHANGE (2), or DELETION (3)
            change_message: Description of the change
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

    @classmethod
    async def handle_tool_call(
        cls, name: str, arguments: Dict[str, Any], user=None
    ) -> List[TextContent]:
        """
        Central handler for all tool calls.

        Args:
            name: Tool name (e.g., 'list_article', 'create_author')
            arguments: Tool arguments
            user: Django User for permission checking (optional)
        """
        # Handle the find_models tool specially
        if name == "find_models":
            return await cls._handle_find_models(arguments)

        # Parse the tool name to get operation and model
        parts = name.split("_", 1)
        if len(parts) != 2:
            return [
                TextContent(
                    type="text", text=json.dumps({"error": "Invalid tool name format"})
                )
            ]

        operation = parts[0]
        model_name = parts[1]

        # Get the model from registry
        if model_name not in cls._registered_models:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Model {model_name} not registered"}),
                )
            ]

        model = cls._registered_models[model_name]["model"]

        # Get admin instance for operations that need it
        admin = cls._registered_models[model_name].get("admin")

        # Permission mapping for operations
        permission_map = {
            "list": "view",
            "get": "view",
            "create": "add",
            "update": "change",
            "delete": "delete",
            "describe": "view",
            "actions": "view",
            "action": "change",  # Actions typically modify data
            "bulk": None,  # Checked per-operation inside handler
            "related": "view",
        }

        # Check permission for the operation
        required_permission = permission_map.get(operation)
        if required_permission and not await cls._check_permission_async(admin, user, required_permission):
            return cls._permission_error(required_permission, model_name)

        # Route to appropriate handler
        if operation == "list":
            return await cls._handle_list(model, arguments)
        elif operation == "get":
            return await cls._handle_get(model, arguments)
        elif operation == "create":
            return await cls._handle_create(model, arguments, user)
        elif operation == "update":
            return await cls._handle_update(model, arguments, user)
        elif operation == "delete":
            return await cls._handle_delete(model, arguments, user)
        elif operation == "describe":
            return await cls._handle_describe(model, admin, arguments)
        elif operation == "actions":
            return await cls._handle_list_actions(model, admin, arguments)
        elif operation == "action":
            return await cls._handle_action(model, admin, arguments, user)
        elif operation == "bulk":
            return await cls._handle_bulk(model, arguments, admin, user)
        elif operation == "related":
            return await cls._handle_related(model, arguments)
        elif operation == "history":
            return await cls._handle_history(model, arguments)
        elif operation == "autocomplete":
            return await cls._handle_autocomplete(model, arguments)
        else:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown operation: {operation}"}),
                )
            ]

    @classmethod
    def _serialize_model_instance(cls, obj_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serialize a model instance dictionary by converting non-serializable fields.

        Args:
            obj_dict: Dictionary representation of a model instance

        Returns:
            Serialized dictionary with all values converted to JSON-serializable types
        """
        serialized = {}
        for key, value in obj_dict.items():
            if isinstance(value, models.Model):
                serialized[key] = str(value)
            else:
                serialized[key] = value
        return serialized

    @classmethod
    def _get_admin_for_model(cls, model_name: str) -> Optional[Any]:
        """Get the admin instance for a model."""
        if model_name in cls._registered_models:
            return cls._registered_models[model_name].get("admin")
        return None

    @classmethod
    def _build_filter_query(
        cls, model: Type[models.Model], filters: Dict[str, Any]
    ) -> Q:
        """
        Build a Q object from filter parameters.

        Supports lookups:
        - field: exact match (default)
        - field__icontains: case-insensitive contains
        - field__gte: greater than or equal
        - field__lte: less than or equal
        - field__in: value in list
        - field__isnull: is null check
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

    @classmethod
    def _build_search_query(
        cls, model: Type[models.Model], search_fields: List[str], search_term: str
    ) -> Q:
        """Build a Q object for searching across multiple fields."""
        if not search_term or not search_fields:
            return Q()

        q = Q()
        for field in search_fields:
            # Use icontains for text search
            lookup = f"{field}__icontains"
            q |= Q(**{lookup: search_term})
        return q

    @classmethod
    def _get_valid_ordering_fields(cls, model: Type[models.Model]) -> set:
        """Get the set of valid field names for ordering."""
        valid_fields = set()
        for field in model._meta.get_fields():
            if hasattr(field, "name"):
                valid_fields.add(field.name)
                valid_fields.add(f"-{field.name}")  # Allow descending order
        return valid_fields

    @classmethod
    async def _handle_list(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle list operation for a model with filtering, searching, and ordering."""
        try:
            limit = arguments.get("limit", 100)
            offset = arguments.get("offset", 0)
            filters = arguments.get("filters", {})
            search = arguments.get("search", "")
            order_by = arguments.get("order_by", [])

            # Get admin instance for search_fields and default ordering
            model_name = model._meta.model_name
            admin = cls._get_admin_for_model(model_name)

            # Get search fields from admin or use empty list
            search_fields = getattr(admin, "search_fields", []) if admin else []

            # Get default ordering from admin or model
            default_ordering = []
            if admin and hasattr(admin, "ordering") and admin.ordering:
                default_ordering = list(admin.ordering)
            elif model._meta.ordering:
                default_ordering = list(model._meta.ordering)

            @sync_to_async
            def get_objects():
                queryset = model.objects.all()

                # Apply filters
                if filters:
                    filter_q = cls._build_filter_query(model, filters)
                    queryset = queryset.filter(filter_q)

                # Apply search
                if search and search_fields:
                    search_q = cls._build_search_query(model, search_fields, search)
                    queryset = queryset.filter(search_q)

                # Apply ordering
                ordering = order_by if order_by else default_ordering
                if ordering:
                    # Validate ordering fields
                    valid_ordering = cls._get_valid_ordering_fields(model)
                    safe_ordering = [o for o in ordering if o in valid_ordering]
                    if safe_ordering:
                        queryset = queryset.order_by(*safe_ordering)

                # Get total count before pagination
                total_count = queryset.count()

                # Apply pagination
                queryset = queryset[offset : offset + limit]
                return total_count, [
                    cls._serialize_model_instance(model_to_dict(obj))
                    for obj in queryset
                ]

            total_count, results = await get_objects()

            return [
                TextContent(
                    type="text",
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
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def _get_inline_data(cls, obj, admin) -> Dict[str, List[Dict[str, Any]]]:
        """Get inline related objects for a model instance."""
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
                    cls._serialize_model_instance(model_to_dict(related_obj))
                    for related_obj in related_objects
                ]

        return inlines_data

    @classmethod
    async def _handle_get(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle get operation for a model with optional inline and related data."""
        try:
            obj_id = arguments.get("id")
            include_inlines = arguments.get("include_inlines", False)
            include_related = arguments.get("include_related", False)

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

            # Get admin for inline support
            model_name = model._meta.model_name
            admin = cls._get_admin_for_model(model_name)

            @sync_to_async
            def get_object():
                obj = model.objects.get(pk=obj_id)
                result = cls._serialize_model_instance(model_to_dict(obj))

                # Include inlines if requested
                if include_inlines and admin:
                    result["_inlines"] = cls._get_inline_data(obj, admin)

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
                                            cls._serialize_model_instance(model_to_dict(r))
                                            for r in related_manager.all()[:10]  # Limit to 10
                                        ]
                    if related_data:
                        result["_related"] = related_data

                return result

            obj_dict = await get_object()

            return [
                TextContent(
                    type="text", text=json.dumps(obj_dict, indent=2, default=str)
                )
            ]
        except model.DoesNotExist:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"{model._meta.model_name} not found"}),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_create(
        cls, model: Type[models.Model], arguments: Dict[str, Any], user=None
    ) -> List[TextContent]:
        """Handle create operation for a model."""
        try:
            data = arguments.get("data", {})

            @sync_to_async
            def create_object():
                from django.contrib.admin.models import ADDITION

                obj = model.objects.create(**data)

                # Log the action
                cls._log_action(
                    user=user,
                    obj=obj,
                    action_flag=ADDITION,
                    change_message=f"Created via MCP: {json.dumps(data, default=str)}",
                )

                return obj.pk, cls._serialize_model_instance(model_to_dict(obj))

            obj_id, obj_dict = await create_object()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": True, "id": obj_id, "object": obj_dict},
                        indent=2,
                        default=str,
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def _update_inlines(cls, obj, admin, inlines_data: Dict[str, List]) -> Dict[str, Any]:
        """Update inline related objects for a model instance."""
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
                        new_obj = inline_model.objects.create(**{
                            k: v for k, v in item_data.items()
                            if k not in ["id", "_delete"]
                        })
                        results["created"].append({"model": inline_model_name, "id": new_obj.pk})
                except Exception as e:
                    results["errors"].append({
                        "model": inline_model_name,
                        "id": item.get("id"),
                        "error": str(e)
                    })

        return results

    @classmethod
    async def _handle_update(
        cls, model: Type[models.Model], arguments: Dict[str, Any], user=None
    ) -> List[TextContent]:
        """Handle update operation for a model with optional inline updates."""
        try:
            obj_id = arguments.get("id")
            data = arguments.get("data", {})
            inlines_data = arguments.get("inlines", {})

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

            # Get admin for inline support and readonly fields
            model_name = model._meta.model_name
            admin = cls._get_admin_for_model(model_name)

            # Validate that only model fields are being updated (protect against mass assignment)
            valid_fields = {
                f.name for f in model._meta.get_fields() if hasattr(f, "name")
            }
            for key in data.keys():
                if key not in valid_fields:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps({"error": f"Invalid field: {key}"}),
                        )
                    ]

            # Check for readonly_fields - prevent updating them
            if admin:
                readonly_fields = set(getattr(admin, "readonly_fields", []))
                readonly_attempted = set(data.keys()) & readonly_fields
                if readonly_attempted:
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps({
                                "error": f"Cannot update readonly fields: {', '.join(readonly_attempted)}",
                                "readonly_fields": list(readonly_attempted),
                            }),
                        )
                    ]

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
                if inlines_data and admin:
                    inlines_result = cls._update_inlines(obj, admin, inlines_data)

                # Log the action
                change_message = []
                if data:
                    change_message.append(f"Changed via MCP: {json.dumps(data, default=str)}")
                if inlines_data:
                    change_message.append(f"Updated inlines: {list(inlines_data.keys())}")
                cls._log_action(
                    user=user,
                    obj=obj,
                    action_flag=CHANGE,
                    change_message=" | ".join(change_message) if change_message else "Updated via MCP",
                )

                return cls._serialize_model_instance(model_to_dict(obj)), inlines_result

            obj_dict, inlines_result = await update_object()

            response = {"success": True, "object": obj_dict}
            if inlines_result and any(inlines_result.values()):
                response["inlines"] = inlines_result

            return [
                TextContent(
                    type="text",
                    text=json.dumps(response, indent=2, default=str),
                )
            ]
        except model.DoesNotExist:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"{model._meta.model_name} not found"}),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_delete(
        cls, model: Type[models.Model], arguments: Dict[str, Any], user=None
    ) -> List[TextContent]:
        """Handle delete operation for a model."""
        try:
            obj_id = arguments.get("id")

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

            @sync_to_async
            def delete_object():
                from django.contrib.admin.models import DELETION

                obj = model.objects.get(pk=obj_id)
                obj_repr = str(obj)

                # Log the action BEFORE deleting (so we still have the object)
                cls._log_action(
                    user=user,
                    obj=obj,
                    action_flag=DELETION,
                    change_message=f"Deleted via MCP",
                )

                obj.delete()
                return obj_repr

            obj_repr = await delete_object()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": True,
                            "message": f"{model._meta.model_name} deleted successfully",
                        }
                    ),
                )
            ]
        except model.DoesNotExist:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"{model._meta.model_name} not found"}),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def _model_matches_query(
        cls, query: str, model_name: str, verbose_name: str
    ) -> bool:
        """Check if a model matches the search query."""
        if not query:
            return True
        query_lower = query.lower()
        return query_lower in model_name.lower() or query_lower in verbose_name.lower()

    @classmethod
    async def _handle_find_models(cls, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle find_models operation to discover available models."""
        try:
            query = arguments.get("query", "")

            models_info = []
            for model_name, model_info in cls._registered_models.items():
                model = model_info["model"]
                admin = model_info["admin"]
                verbose_name = str(model._meta.verbose_name)
                verbose_name_plural = str(model._meta.verbose_name_plural)

                # Filter by query if provided
                if not cls._model_matches_query(query, model_name, verbose_name):
                    continue

                # Check if model has tools exposed
                has_tools_exposed = getattr(admin, "mcp_expose", False)

                models_info.append(
                    {
                        "model_name": model_name,
                        "verbose_name": verbose_name,
                        "verbose_name_plural": verbose_name_plural,
                        "app_label": model._meta.app_label,
                        "tools_exposed": has_tools_exposed,
                    }
                )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "count": len(models_info),
                            "models": models_info,
                        },
                        indent=2,
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def _get_field_metadata(cls, field) -> Dict[str, Any]:
        """Extract comprehensive metadata from a Django model field."""
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
            metadata["choices"] = [
                {"value": choice[0], "label": str(choice[1])}
                for choice in field.choices
            ]

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

    @classmethod
    async def _handle_describe(
        cls, model: Type[models.Model], admin: Any, arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle describe operation to get model metadata."""
        try:
            model_name = model._meta.model_name

            # Collect field metadata
            fields = []
            relationships = []

            for field in model._meta.get_fields():
                field_meta = cls._get_field_metadata(field)

                # Categorize as regular field or relationship
                if field_meta.get("related_model"):
                    relationships.append(field_meta)
                elif hasattr(field, "get_internal_type"):
                    fields.append(field_meta)

            # Collect admin configuration
            admin_config = {}
            if admin:
                admin_config["list_display"] = list(getattr(admin, "list_display", []))
                admin_config["list_filter"] = list(getattr(admin, "list_filter", []))
                admin_config["search_fields"] = list(getattr(admin, "search_fields", []))
                admin_config["ordering"] = list(getattr(admin, "ordering", []))
                admin_config["readonly_fields"] = list(
                    getattr(admin, "readonly_fields", [])
                )

                # Get fieldsets if defined
                fieldsets = getattr(admin, "fieldsets", None)
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
                date_hierarchy = getattr(admin, "date_hierarchy", None)
                if date_hierarchy:
                    admin_config["date_hierarchy"] = date_hierarchy

                # Get inlines info
                inlines = getattr(admin, "inlines", [])
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

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def _get_action_info(cls, action) -> Dict[str, Any]:
        """Extract information about a ModelAdmin action."""
        if callable(action):
            name = getattr(action, "__name__", str(action))
            description = getattr(
                action, "short_description", name.replace("_", " ").title()
            )
            return {"name": name, "description": str(description)}
        return {"name": str(action), "description": str(action)}

    @classmethod
    async def _handle_list_actions(
        cls, model: Type[models.Model], admin: Any, arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle list_actions operation to discover available actions."""
        try:
            actions_info = []

            if admin:
                # Get actions from admin
                admin_actions = getattr(admin, "actions", []) or []

                for action in admin_actions:
                    action_info = cls._get_action_info(action)
                    actions_info.append(action_info)

                # Add built-in delete_selected if not disabled
                if admin_actions is not None:  # None means actions are disabled
                    # Check if delete_selected is available
                    from django.contrib.admin import actions as admin_module_actions

                    if hasattr(admin_module_actions, "delete_selected"):
                        actions_info.append(
                            {
                                "name": "delete_selected",
                                "description": "Delete selected items",
                            }
                        )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "model": model._meta.model_name,
                            "count": len(actions_info),
                            "actions": actions_info,
                        },
                        indent=2,
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_action(
        cls, model: Type[models.Model], admin: Any, arguments: Dict[str, Any], user=None
    ) -> List[TextContent]:
        """Handle action execution on selected objects."""
        try:
            action_name = arguments.get("action")
            ids = arguments.get("ids", [])

            if not action_name:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "action parameter is required"}),
                    )
                ]

            if not ids:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "ids parameter is required"}),
                    )
                ]

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
                if admin:
                    admin_actions = getattr(admin, "actions", []) or []
                    for action in admin_actions:
                        if callable(action) and getattr(action, "__name__", "") == action_name:
                            # Create a mock request with user for the action
                            request = cls._create_mock_request(user)

                            # Execute the action
                            result = action(admin, request, queryset)
                            return {
                                "success": True,
                                "action": action_name,
                                "affected_count": count,
                                "message": f"Executed {action_name} on {count} objects",
                                "result": str(result) if result else None,
                            }

                return {"error": f"Action '{action_name}' not found"}

            result = await execute_action()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_bulk(
        cls, model: Type[models.Model], arguments: Dict[str, Any], admin=None, user=None
    ) -> List[TextContent]:
        """Handle bulk operations: create, update, delete."""
        try:
            operation = arguments.get("operation")
            items = arguments.get("items", [])

            if not operation:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "operation parameter is required"}),
                    )
                ]

            if operation not in ["create", "update", "delete"]:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": "operation must be 'create', 'update', or 'delete'"}
                        ),
                    )
                ]

            # Check permission for the bulk operation
            permission_map = {
                "create": "add",
                "update": "change",
                "delete": "delete",
            }
            required_permission = permission_map.get(operation)
            if required_permission and not await cls._check_permission_async(admin, user, required_permission):
                model_name = model._meta.model_name
                return cls._permission_error(required_permission, model_name)

            @sync_to_async
            def execute_bulk():
                from django.contrib.admin.models import ADDITION, CHANGE, DELETION

                results = {"success": [], "errors": []}

                if operation == "create":
                    for i, item_data in enumerate(items):
                        try:
                            obj = model.objects.create(**item_data)
                            cls._log_action(
                                user=user,
                                obj=obj,
                                action_flag=ADDITION,
                                change_message=f"Bulk created via MCP",
                            )
                            results["success"].append(
                                {"index": i, "id": obj.pk, "created": True}
                            )
                        except Exception as e:
                            results["errors"].append({"index": i, "error": str(e)})

                elif operation == "update":
                    for i, item in enumerate(items):
                        try:
                            obj_id = item.get("id")
                            data = item.get("data", {})
                            if not obj_id:
                                results["errors"].append(
                                    {"index": i, "error": "id is required for update"}
                                )
                                continue

                            obj = model.objects.get(pk=obj_id)
                            for key, value in data.items():
                                setattr(obj, key, value)
                            obj.save()
                            cls._log_action(
                                user=user,
                                obj=obj,
                                action_flag=CHANGE,
                                change_message=f"Bulk updated via MCP: {json.dumps(data, default=str)}",
                            )
                            results["success"].append(
                                {"index": i, "id": obj_id, "updated": True}
                            )
                        except model.DoesNotExist:
                            results["errors"].append(
                                {"index": i, "error": f"Object with id {obj_id} not found"}
                            )
                        except Exception as e:
                            results["errors"].append({"index": i, "error": str(e)})

                elif operation == "delete":
                    ids = items if isinstance(items, list) else []
                    for i, obj_id in enumerate(ids):
                        try:
                            obj = model.objects.get(pk=obj_id)
                            cls._log_action(
                                user=user,
                                obj=obj,
                                action_flag=DELETION,
                                change_message=f"Bulk deleted via MCP",
                            )
                            obj.delete()
                            results["success"].append(
                                {"index": i, "id": obj_id, "deleted": True}
                            )
                        except model.DoesNotExist:
                            results["errors"].append(
                                {"index": i, "error": f"Object with id {obj_id} not found"}
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

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_related(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle fetching related objects for a model instance."""
        try:
            obj_id = arguments.get("id")
            relation = arguments.get("relation")
            limit = arguments.get("limit", 100)
            offset = arguments.get("offset", 0)

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

            if not relation:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "relation parameter is required"}),
                    )
                ]

            @sync_to_async
            def get_related():
                obj = model.objects.get(pk=obj_id)

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
                        "results": [
                            cls._serialize_model_instance(model_to_dict(r))
                            for r in related_objects
                        ],
                    }
                elif hasattr(related_attr, "_meta"):
                    # Single relation (FK, OneToOne)
                    return {
                        "relation": relation,
                        "type": "single",
                        "result": cls._serialize_model_instance(model_to_dict(related_attr)),
                    }
                else:
                    # It's a simple field value
                    return {
                        "relation": relation,
                        "type": "value",
                        "value": str(related_attr),
                    }

            result = await get_related()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except model.DoesNotExist:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"{model._meta.model_name} not found"}),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_autocomplete(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle autocomplete search for a model (for FK/M2M field suggestions)."""
        try:
            term = arguments.get("term", "")
            limit = arguments.get("limit", 20)

            model_name = model._meta.model_name
            admin = cls._get_admin_for_model(model_name)

            @sync_to_async
            def search_autocomplete():
                queryset = model.objects.all()

                # Use admin's search_fields if available
                search_fields = []
                if admin:
                    search_fields = list(getattr(admin, "search_fields", []))

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
                    from django.db.models import Q

                    q = Q()
                    for field in search_fields:
                        q |= Q(**{f"{field}__icontains": term})
                    queryset = queryset.filter(q)

                # Apply ordering if admin has it
                if admin:
                    ordering = getattr(admin, "ordering", None)
                    if ordering:
                        queryset = queryset.order_by(*ordering)

                # Limit results
                results = queryset[:limit]

                # Return simplified format suitable for autocomplete
                autocomplete_results = []
                for obj in results:
                    autocomplete_results.append({
                        "id": obj.pk,
                        "text": str(obj),
                    })

                return {
                    "model": model_name,
                    "term": term,
                    "count": len(autocomplete_results),
                    "results": autocomplete_results,
                }

            result = await search_autocomplete()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_history(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle fetching LogEntry history for a model instance."""
        try:
            obj_id = arguments.get("id")
            limit = arguments.get("limit", 50)

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

            @sync_to_async
            def get_history():
                from django.contrib.admin.models import LogEntry, ADDITION, CHANGE, DELETION
                from django.contrib.contenttypes.models import ContentType

                # Verify the object exists
                obj = model.objects.get(pk=obj_id)

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
                    history.append({
                        "action": action_names.get(entry.action_flag, "unknown"),
                        "action_flag": entry.action_flag,
                        "action_time": entry.action_time.isoformat(),
                        "user": entry.user.username if entry.user else None,
                        "user_id": entry.user_id,
                        "change_message": entry.change_message,
                        "object_repr": entry.object_repr,
                    })

                return {
                    "model": model._meta.model_name,
                    "object_id": obj_id,
                    "current_repr": str(obj),
                    "count": len(history),
                    "history": history,
                }

            result = await get_history()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]
        except model.DoesNotExist:
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": f"{model._meta.model_name} not found"}),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    def get_mcp_tools(cls, model: Type[models.Model]) -> List[Tool]:
        """Get the list of MCP tools for a model."""
        model_name = model._meta.model_name
        verbose_name = model._meta.verbose_name

        # Get field information for documentation
        fields = []
        for field in model._meta.get_fields():
            if hasattr(field, "get_internal_type"):
                # A field is required if it's not nullable and not blank
                null_allowed = getattr(field, "null", False)
                blank_allowed = getattr(field, "blank", False)
                has_default = getattr(field, "has_default", lambda: False)()

                # Field is required if it doesn't allow null, doesn't allow blank, and has no default
                required = not null_allowed and not blank_allowed and not has_default

                fields.append(
                    {
                        "name": field.name,
                        "type": field.get_internal_type(),
                        "required": required,
                    }
                )

        fields_doc = "\n".join(
            [
                f"  - {f['name']} ({f['type']}){' [required]' if f['required'] else ''}"
                for f in fields
            ]
        )

        return [
            Tool(
                name=f"list_{model_name}",
                description=(
                    f"List {verbose_name} instances with filtering, searching, ordering, and pagination.\n\n"
                    f"Filter lookups: field (exact), field__icontains, field__gte, field__lte, field__in, field__isnull\n\n"
                    f"Available fields:\n{fields_doc}"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of items to return (default: 100)",
                            "default": 100,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of items to skip (default: 0)",
                            "default": 0,
                        },
                        "filters": {
                            "type": "object",
                            "description": (
                                "Filter criteria. Keys are field names with optional lookups "
                                "(e.g., {'status': 'published', 'created_at__gte': '2024-01-01'})"
                            ),
                        },
                        "search": {
                            "type": "string",
                            "description": "Search term to match against searchable fields",
                        },
                        "order_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Fields to order by. Prefix with '-' for descending "
                                "(e.g., ['-created_at', 'title'])"
                            ),
                        },
                    },
                },
            ),
            Tool(
                name=f"get_{model_name}",
                description=(
                    f"Get a specific {verbose_name} by ID with optional inline and related data."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}",
                        },
                        "include_inlines": {
                            "type": "boolean",
                            "description": "Include inline related objects (requires admin inlines)",
                            "default": False,
                        },
                        "include_related": {
                            "type": "boolean",
                            "description": "Include reverse FK/M2M related objects",
                            "default": False,
                        },
                    },
                    "required": ["id"],
                },
            ),
            Tool(
                name=f"create_{model_name}",
                description=f"Create a new {verbose_name}\n\nFields:\n{fields_doc}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": f"The data for the new {verbose_name}",
                        }
                    },
                    "required": ["data"],
                },
            ),
            Tool(
                name=f"update_{model_name}",
                description=(
                    f"Update an existing {verbose_name} with optional inline updates.\n\n"
                    f"Fields:\n{fields_doc}"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}",
                        },
                        "data": {
                            "type": "object",
                            "description": "The fields to update",
                        },
                        "inlines": {
                            "type": "object",
                            "description": (
                                "Inline updates: {model_name: [{id, data}, {data for new}, {id, _delete: true}]}"
                            ),
                        },
                    },
                    "required": ["id"],
                },
            ),
            Tool(
                name=f"delete_{model_name}",
                description=f"Delete a {verbose_name} by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name} to delete",
                        }
                    },
                    "required": ["id"],
                },
            ),
            Tool(
                name=f"describe_{model_name}",
                description=(
                    f"Get detailed metadata about the {verbose_name} model including "
                    f"field definitions, relationships, and admin configuration."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name=f"actions_{model_name}",
                description=(
                    f"List available admin actions for {verbose_name}. "
                    f"Returns action names and descriptions that can be executed via action_{model_name}."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name=f"action_{model_name}",
                description=(
                    f"Execute an admin action on selected {verbose_name} instances. "
                    f"Use actions_{model_name} to discover available actions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The name of the action to execute (e.g., 'delete_selected')",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": ["integer", "string"]},
                            "description": "List of IDs to apply the action to",
                        },
                    },
                    "required": ["action", "ids"],
                },
            ),
            Tool(
                name=f"bulk_{model_name}",
                description=(
                    f"Perform bulk operations on {verbose_name}: create, update, or delete multiple items.\n\n"
                    f"For 'create': items is a list of data objects\n"
                    f"For 'update': items is a list of {{id, data}} objects\n"
                    f"For 'delete': items is a list of IDs"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["create", "update", "delete"],
                            "description": "The bulk operation to perform",
                        },
                        "items": {
                            "type": "array",
                            "description": "Items to process (format depends on operation)",
                        },
                    },
                    "required": ["operation", "items"],
                },
            ),
            Tool(
                name=f"related_{model_name}",
                description=(
                    f"Fetch related objects for a {verbose_name} instance. "
                    f"Use describe_{model_name} to discover available relations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}",
                        },
                        "relation": {
                            "type": "string",
                            "description": "The name of the relation to fetch (e.g., 'articles' for reverse FK)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of related items to return (default: 100)",
                            "default": 100,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of items to skip (default: 0)",
                            "default": 0,
                        },
                    },
                    "required": ["id", "relation"],
                },
            ),
            Tool(
                name=f"history_{model_name}",
                description=(
                    f"Get the change history (LogEntry records) for a {verbose_name} instance. "
                    f"Shows who made what changes and when."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name} to get history for",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of history entries to return (default: 50)",
                            "default": 50,
                        },
                    },
                    "required": ["id"],
                },
            ),
            Tool(
                name=f"autocomplete_{model_name}",
                description=(
                    f"Search {verbose_name} instances for autocomplete suggestions. "
                    f"Useful for populating FK/M2M field widgets."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "term": {
                            "type": "string",
                            "description": "Search term to match against searchable fields",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of suggestions to return (default: 20)",
                            "default": 20,
                        },
                    },
                },
            ),
        ]

    @classmethod
    def get_find_models_tool(cls) -> Tool:
        """Get the find_models tool for discovering available models."""
        return Tool(
            name="find_models",
            description=(
                "Discover available Django models registered with MCP. "
                "Use this to find which models have tools available."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search query to filter models by name (case-insensitive)",
                    }
                },
            },
        )

    def __init__(self, *args, **kwargs):
        """Initialize the mixin and register MCP tools."""
        super().__init__(*args, **kwargs)
        # Register tools for this model
        self.__class__.register_model_tools(self)
