"""
MCP Admin Mixin for Django models

This mixin enables MCP (Model Context Protocol) functionality for Django admin classes.
When added to a ModelAdmin class, it exposes the model's CRUD operations through MCP tools.
"""

import json
from typing import Any, Dict, List, Type

from asgiref.sync import sync_to_async
from django.db import models
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
    async def handle_tool_call(
        cls, name: str, arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Central handler for all tool calls."""
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

        # Route to appropriate handler
        if operation == "list":
            return await cls._handle_list(model, arguments)
        elif operation == "get":
            return await cls._handle_get(model, arguments)
        elif operation == "create":
            return await cls._handle_create(model, arguments)
        elif operation == "update":
            return await cls._handle_update(model, arguments)
        elif operation == "delete":
            return await cls._handle_delete(model, arguments)
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
    async def _handle_list(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle list operation for a model."""
        try:
            limit = arguments.get("limit", 100)
            offset = arguments.get("offset", 0)

            @sync_to_async
            def get_objects():
                queryset = model.objects.all()[offset : offset + limit]
                return [
                    cls._serialize_model_instance(model_to_dict(obj))
                    for obj in queryset
                ]

            results = await get_objects()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"count": len(results), "results": results},
                        indent=2,
                        default=str,
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    @classmethod
    async def _handle_get(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle get operation for a model."""
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
            def get_object():
                obj = model.objects.get(pk=obj_id)
                return cls._serialize_model_instance(model_to_dict(obj))

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
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle create operation for a model."""
        try:
            data = arguments.get("data", {})

            @sync_to_async
            def create_object():
                obj = model.objects.create(**data)
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
    async def _handle_update(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle update operation for a model."""
        try:
            obj_id = arguments.get("id")
            data = arguments.get("data", {})

            if not obj_id:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": "id parameter is required"}),
                    )
                ]

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

            @sync_to_async
            def update_object():
                obj = model.objects.get(pk=obj_id)
                # Update only the specified fields
                for key, value in data.items():
                    setattr(obj, key, value)
                obj.save()
                return cls._serialize_model_instance(model_to_dict(obj))

            obj_dict = await update_object()

            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": True, "object": obj_dict}, indent=2, default=str
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
    async def _handle_delete(
        cls, model: Type[models.Model], arguments: Dict[str, Any]
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
                obj = model.objects.get(pk=obj_id)
                obj.delete()

            await delete_object()

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
    async def _handle_find_models(
        cls, arguments: Dict[str, Any]
    ) -> List[TextContent]:
        """Handle find_models operation to discover available models."""
        try:
            query = arguments.get("query", "").lower()
            
            models_info = []
            for model_name, model_info in cls._registered_models.items():
                model = model_info["model"]
                admin = model_info["admin"]
                verbose_name = str(model._meta.verbose_name)
                verbose_name_plural = str(model._meta.verbose_name_plural)
                
                # Filter by query if provided
                if query and query not in model_name.lower() and query not in verbose_name.lower():
                    continue
                
                # Check if model has tools exposed
                has_tools_exposed = getattr(admin, 'mcp_expose', False)
                
                models_info.append({
                    "model_name": model_name,
                    "verbose_name": verbose_name,
                    "verbose_name_plural": verbose_name_plural,
                    "app_label": model._meta.app_label,
                    "tools_exposed": has_tools_exposed,
                })
            
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
                description=f"List all {verbose_name} instances with optional pagination",
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
                    },
                },
            ),
            Tool(
                name=f"get_{model_name}",
                description=f"Get a specific {verbose_name} by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}",
                        }
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
                description=f"Update an existing {verbose_name}\n\nFields:\n{fields_doc}",
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
                    },
                    "required": ["id", "data"],
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
        ]

    @classmethod
    def get_find_models_tool(cls) -> Tool:
        """Get the find_models tool for discovering available models."""
        return Tool(
            name="find_models",
            description="Discover available Django models registered with MCP. Use this to find which models have tools available.",
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
