"""
Handlers module for django-admin-mcp.

This module provides handler utilities and base functionality
for processing MCP tool requests.
"""

from django_admin_mcp.handlers.actions import (
    handle_action,
    handle_actions,
    handle_bulk,
)
from django_admin_mcp.handlers.base import (
    async_check_permission,
    check_permission,
    create_mock_request,
    format_form_errors,
    get_admin_form_class,
    get_exposed_models,
    get_model_admin,
    get_model_name,
    json_response,
    normalize_fk_fields,
    serialize_instance,
)
from django_admin_mcp.handlers.crud import (
    handle_create,
    handle_delete,
    handle_get,
    handle_list,
    handle_update,
)
from django_admin_mcp.handlers.meta import (
    handle_describe,
    handle_find_models,
)
from django_admin_mcp.handlers.relations import (
    handle_autocomplete,
    handle_history,
    handle_related,
)

__all__ = [
    # Base utilities
    "async_check_permission",
    "check_permission",
    "create_mock_request",
    "format_form_errors",
    "get_admin_form_class",
    "get_exposed_models",
    "get_model_admin",
    "get_model_name",
    "json_response",
    "normalize_fk_fields",
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
    # Meta handlers
    "handle_describe",
    "handle_find_models",
    # Relations handlers
    "handle_autocomplete",
    "handle_history",
    "handle_related",
]
