"""
Tools module for django-admin-mcp.

This module provides tool registration, schema generation, and routing
for MCP tool calls.
"""

from django_admin_mcp.tools.registry import (
    HANDLERS,
    call_tool,
    get_find_models_tool,
    get_model_tools,
    get_tools,
)

__all__ = [
    "HANDLERS",
    "call_tool",
    "get_find_models_tool",
    "get_model_tools",
    "get_tools",
]
