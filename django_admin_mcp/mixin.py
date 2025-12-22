"""
MCP Admin Mixin for Django models

This mixin enables MCP (Model Context Protocol) functionality for Django admin classes.
When added to a ModelAdmin class, it exposes the model's CRUD operations through MCP tools.
"""

import json
from typing import Any, Dict, List, Optional, Type
from django.contrib import admin
from django.db import models
from django.forms.models import model_to_dict
from mcp.server import Server
from mcp.types import Tool, TextContent


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
            'model': model,
            'admin': model_admin_instance
        }
        
        server = cls.get_mcp_server()
        
        # Register list tool
        @server.call_tool()
        async def handle_list_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle list tool calls."""
            if name == f"list_{model_name}":
                return await cls._handle_list(model, arguments)
            return []
        
        # Register get tool
        @server.call_tool()
        async def handle_get_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle get tool calls."""
            if name == f"get_{model_name}":
                return await cls._handle_get(model, arguments)
            return []
        
        # Register create tool
        @server.call_tool()
        async def handle_create_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle create tool calls."""
            if name == f"create_{model_name}":
                return await cls._handle_create(model, arguments)
            return []
        
        # Register update tool
        @server.call_tool()
        async def handle_update_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle update tool calls."""
            if name == f"update_{model_name}":
                return await cls._handle_update(model, arguments)
            return []
        
        # Register delete tool
        @server.call_tool()
        async def handle_delete_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle delete tool calls."""
            if name == f"delete_{model_name}":
                return await cls._handle_delete(model, arguments)
            return []
    
    @classmethod
    async def _handle_list(cls, model: Type[models.Model], arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle list operation for a model."""
        try:
            limit = arguments.get('limit', 100)
            offset = arguments.get('offset', 0)
            
            queryset = model.objects.all()[offset:offset + limit]
            results = []
            
            for obj in queryset:
                obj_dict = model_to_dict(obj)
                # Convert non-serializable fields
                for key, value in obj_dict.items():
                    if isinstance(value, models.Model):
                        obj_dict[key] = str(value)
                results.append(obj_dict)
            
            return [TextContent(
                type="text",
                text=json.dumps({
                    'count': len(results),
                    'results': results
                }, indent=2, default=str)
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({'error': str(e)})
            )]
    
    @classmethod
    async def _handle_get(cls, model: Type[models.Model], arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle get operation for a model."""
        try:
            obj_id = arguments.get('id')
            if not obj_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({'error': 'id parameter is required'})
                )]
            
            obj = model.objects.get(pk=obj_id)
            obj_dict = model_to_dict(obj)
            
            # Convert non-serializable fields
            for key, value in obj_dict.items():
                if isinstance(value, models.Model):
                    obj_dict[key] = str(value)
            
            return [TextContent(
                type="text",
                text=json.dumps(obj_dict, indent=2, default=str)
            )]
        except model.DoesNotExist:
            return [TextContent(
                type="text",
                text=json.dumps({'error': f'{model._meta.model_name} not found'})
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({'error': str(e)})
            )]
    
    @classmethod
    async def _handle_create(cls, model: Type[models.Model], arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle create operation for a model."""
        try:
            data = arguments.get('data', {})
            obj = model.objects.create(**data)
            obj_dict = model_to_dict(obj)
            
            # Convert non-serializable fields
            for key, value in obj_dict.items():
                if isinstance(value, models.Model):
                    obj_dict[key] = str(value)
            
            return [TextContent(
                type="text",
                text=json.dumps({
                    'success': True,
                    'id': obj.pk,
                    'object': obj_dict
                }, indent=2, default=str)
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({'error': str(e)})
            )]
    
    @classmethod
    async def _handle_update(cls, model: Type[models.Model], arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle update operation for a model."""
        try:
            obj_id = arguments.get('id')
            data = arguments.get('data', {})
            
            if not obj_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({'error': 'id parameter is required'})
                )]
            
            obj = model.objects.get(pk=obj_id)
            for key, value in data.items():
                setattr(obj, key, value)
            obj.save()
            
            obj_dict = model_to_dict(obj)
            
            # Convert non-serializable fields
            for key, value in obj_dict.items():
                if isinstance(value, models.Model):
                    obj_dict[key] = str(value)
            
            return [TextContent(
                type="text",
                text=json.dumps({
                    'success': True,
                    'object': obj_dict
                }, indent=2, default=str)
            )]
        except model.DoesNotExist:
            return [TextContent(
                type="text",
                text=json.dumps({'error': f'{model._meta.model_name} not found'})
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({'error': str(e)})
            )]
    
    @classmethod
    async def _handle_delete(cls, model: Type[models.Model], arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle delete operation for a model."""
        try:
            obj_id = arguments.get('id')
            
            if not obj_id:
                return [TextContent(
                    type="text",
                    text=json.dumps({'error': 'id parameter is required'})
                )]
            
            obj = model.objects.get(pk=obj_id)
            obj.delete()
            
            return [TextContent(
                type="text",
                text=json.dumps({
                    'success': True,
                    'message': f'{model._meta.model_name} deleted successfully'
                })
            )]
        except model.DoesNotExist:
            return [TextContent(
                type="text",
                text=json.dumps({'error': f'{model._meta.model_name} not found'})
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({'error': str(e)})
            )]
    
    @classmethod
    def get_mcp_tools(cls, model: Type[models.Model]) -> List[Tool]:
        """Get the list of MCP tools for a model."""
        model_name = model._meta.model_name
        verbose_name = model._meta.verbose_name
        
        # Get field information for documentation
        fields = []
        for field in model._meta.get_fields():
            if hasattr(field, 'get_internal_type'):
                fields.append({
                    'name': field.name,
                    'type': field.get_internal_type(),
                    'required': not field.blank if hasattr(field, 'blank') else False
                })
        
        fields_doc = '\n'.join([
            f"  - {f['name']} ({f['type']}){' [required]' if f['required'] else ''}"
            for f in fields
        ])
        
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
                            "default": 100
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Number of items to skip (default: 0)",
                            "default": 0
                        }
                    }
                }
            ),
            Tool(
                name=f"get_{model_name}",
                description=f"Get a specific {verbose_name} by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}"
                        }
                    },
                    "required": ["id"]
                }
            ),
            Tool(
                name=f"create_{model_name}",
                description=f"Create a new {verbose_name}\n\nFields:\n{fields_doc}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "object",
                            "description": f"The data for the new {verbose_name}"
                        }
                    },
                    "required": ["data"]
                }
            ),
            Tool(
                name=f"update_{model_name}",
                description=f"Update an existing {verbose_name}\n\nFields:\n{fields_doc}",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name}"
                        },
                        "data": {
                            "type": "object",
                            "description": "The fields to update"
                        }
                    },
                    "required": ["id", "data"]
                }
            ),
            Tool(
                name=f"delete_{model_name}",
                description=f"Delete a {verbose_name} by ID",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": ["integer", "string"],
                            "description": f"The ID of the {verbose_name} to delete"
                        }
                    },
                    "required": ["id"]
                }
            )
        ]
    
    def __init__(self, *args, **kwargs):
        """Initialize the mixin and register MCP tools."""
        super().__init__(*args, **kwargs)
        # Register tools for this model
        self.__class__.register_model_tools(self)
