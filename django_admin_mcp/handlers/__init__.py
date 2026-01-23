"""
Handlers module for django-admin-mcp.

This module provides handler utilities and base functionality
for processing MCP tool requests.
"""

from django_admin_mcp.handlers.base import (
    check_permission,
    create_mock_request,
    get_exposed_models,
    get_model_admin,
    get_model_name,
    json_response,
    serialize_instance,
)
from django_admin_mcp.handlers.actions import (
    handle_action,
    handle_actions,
    handle_bulk,
)
from django_admin_mcp.handlers.crud import (
    handle_create,
    handle_delete,
    handle_get,
    handle_list,
    handle_update,
)

__all__ = [
    # Base utilities
    "check_permission",
    "create_mock_request",
    "get_exposed_models",
    "get_model_admin",
    "get_model_name",
    "json_response",
    "serialize_instance",
    # Action handlers
    "handle_action",
    "handle_actions",
    "handle_bulk",
    # CRUD handlers
    "handle_create",
    "handle_delete",
    "handle_get",
    "handle_list",
    "handle_update",
]
