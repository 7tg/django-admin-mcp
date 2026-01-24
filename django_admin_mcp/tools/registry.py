"""
Tool registry for django-admin-mcp.

This module provides tool registration, schema generation, and routing
for MCP tool calls.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from django.db import models
from django.http import HttpRequest

from django_admin_mcp.handlers import (
    get_exposed_models,
    handle_action,
    handle_actions,
    handle_autocomplete,
    handle_bulk,
    handle_create,
    handle_delete,
    handle_describe,
    handle_find_models,
    handle_get,
    handle_history,
    handle_list,
    handle_related,
    handle_update,
    json_response,
)
from django_admin_mcp.protocol.types import TextContent, Tool

# Type alias for handler functions
HandlerFunc = Callable[
    [str, dict[str, Any], HttpRequest],
    Awaitable[list[TextContent]],
]

# Handler registry mapping operation names to handler functions
HANDLERS: dict[str, HandlerFunc] = {
    "list": handle_list,
    "get": handle_get,
    "create": handle_create,
    "update": handle_update,
    "delete": handle_delete,
    "describe": handle_describe,
    "actions": handle_actions,
    "action": handle_action,
    "bulk": handle_bulk,
    "related": handle_related,
    "history": handle_history,
    "autocomplete": handle_autocomplete,
}


async def call_tool(name: str, arguments: dict[str, Any], request: HttpRequest) -> list[TextContent]:
    """
    Route tool call to appropriate handler.

    Parses the tool name to extract operation and model name,
    then dispatches to the registered handler.

    Args:
        name: Tool name (e.g., 'list_article', 'create_author', 'find_models').
        arguments: Tool arguments dictionary.
        request: HttpRequest with user set for permission checking.

    Returns:
        List of TextContent with the operation result.
    """
    # Handle the find_models tool specially (no model name)
    if name == "find_models":
        return await handle_find_models("", arguments, request)

    # Parse tool name: operation_modelname
    parts = name.split("_", 1)
    if len(parts) != 2:
        return json_response({"error": "Invalid tool name format"})

    operation, model_name = parts

    # Find handler for operation
    handler = HANDLERS.get(operation)
    if not handler:
        return json_response({"error": f"Unknown operation: {operation}"})

    return await handler(model_name, arguments, request)


def _get_field_info(model: type[models.Model]) -> list[dict[str, Any]]:
    """
    Get field information for a model.

    Args:
        model: Django model class.

    Returns:
        List of field info dictionaries with name, type, and required status.
    """
    fields = []
    for field in model._meta.get_fields():
        if hasattr(field, "get_internal_type"):
            null_allowed = getattr(field, "null", False)
            blank_allowed = getattr(field, "blank", False)
            has_default = getattr(field, "has_default", lambda: False)()
            required = not null_allowed and not blank_allowed and not has_default

            fields.append(
                {
                    "name": field.name,
                    "type": field.get_internal_type(),
                    "required": required,
                }
            )
    return fields


def _format_fields_doc(fields: list[dict[str, Any]]) -> str:
    """Format field info list as documentation string."""
    return "\n".join([f"  - {f['name']} ({f['type']}){' [required]' if f['required'] else ''}" for f in fields])


def get_model_tools(model: type[models.Model]) -> list[Tool]:
    """
    Generate Tool definitions for a single model.

    Creates tools for all standard operations: list, get, create, update,
    delete, describe, actions, action, bulk, related, history, autocomplete.

    Args:
        model: Django model class.

    Returns:
        List of Tool definitions for the model.
    """
    model_name = model._meta.model_name
    verbose_name = model._meta.verbose_name

    fields = _get_field_info(model)
    fields_doc = _format_fields_doc(fields)

    return [
        Tool(
            name=f"list_{model_name}",
            description=(
                f"List {verbose_name} instances with filtering, searching, "
                f"ordering, and pagination.\n\n"
                f"Filter lookups: field (exact), field__icontains, field__gte, "
                f"field__lte, field__in, field__isnull\n\n"
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
                            "Fields to order by. Prefix with '-' for descending (e.g., ['-created_at', 'title'])"
                        ),
                    },
                },
            },
        ),
        Tool(
            name=f"get_{model_name}",
            description=(f"Get a specific {verbose_name} by ID with optional inline and related data."),
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
            description=(f"Update an existing {verbose_name} with optional inline updates.\n\nFields:\n{fields_doc}"),
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


def get_find_models_tool() -> Tool:
    """
    Get the find_models tool for discovering available models.

    Returns:
        Tool definition for find_models.
    """
    return Tool(
        name="find_models",
        description=(
            "Discover available Django models registered with MCP. Use this to find which models have tools available."
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


def get_tools() -> list[Tool]:
    """
    Generate Tool definitions for all exposed models.

    Discovers all ModelAdmin classes with mcp_expose=True and
    generates tool definitions for each.

    Returns:
        List of all Tool definitions including find_models and
        per-model operation tools.
    """
    tools = [get_find_models_tool()]

    for _model_name, model_admin in get_exposed_models():
        model = model_admin.model
        tools.extend(get_model_tools(model))

    return tools
