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

__all__ = [
    "check_permission",
    "create_mock_request",
    "get_exposed_models",
    "get_model_admin",
    "get_model_name",
    "json_response",
    "serialize_instance",
]
