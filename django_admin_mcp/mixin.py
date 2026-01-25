"""
MCP Admin Mixin for Django models

This mixin enables MCP (Model Context Protocol) functionality for Django admin classes.
When added to a ModelAdmin class, it exposes the model's CRUD operations through MCP tools.
"""

from typing import Any

from django.db import models

from django_admin_mcp.handlers import create_mock_request
from django_admin_mcp.protocol.types import TextContent, Tool
from django_admin_mcp.tools import call_tool, get_find_models_tool, get_model_tools


class MCPAdminMixin:
    """
    Mixin for Django ModelAdmin classes to enable MCP functionality.

    Usage:
        from django.contrib import admin
        from django_admin_mcp import MCPAdminMixin
        from .models import MyModel

        @admin.register(MyModel)
        class MyModelAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True  # Enable MCP tools for this model
            mcp_exclude_fields = ['password', 'secret']  # Exclude sensitive fields

    This will automatically register MCP tools for:
    - list_<model_name>: List all instances
    - get_<model_name>: Get a specific instance by ID
    - create_<model_name>: Create a new instance
    - update_<model_name>: Update an existing instance
    - delete_<model_name>: Delete an instance

    Attributes:
        mcp_expose (bool): Set to True to expose direct MCP tools for this model.
            If False or not set, model is discoverable but no direct tools are created.
        mcp_fields (list[str] | None): List of field names to include in serialization.
            Takes precedence over Django admin's 'fields' attribute.
            If not set, falls back to 'fields' or includes all fields.
        mcp_exclude_fields (list[str] | None): List of field names to exclude from serialization.
            Takes precedence over Django admin's 'exclude' attribute.
            Use this to prevent sensitive data exposure (e.g., passwords, tokens).
            If not set, falls back to 'exclude' or excludes nothing.
    """

    # Type annotations for MCP-specific attributes (set by subclasses)
    mcp_expose: bool
    mcp_fields: list[str] | None
    mcp_exclude_fields: list[str] | None

    # Class-level registry to track registered models
    _registered_models: dict[str, dict[str, Any]] = {}

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
    async def handle_tool_call(cls, name: str, arguments: dict[str, Any], user=None) -> list[TextContent]:
        """
        Central handler for all tool calls.

        Delegates to the tools module for actual handling.

        Args:
            name: Tool name (e.g., 'list_article', 'create_author')
            arguments: Tool arguments
            user: Django User for permission checking (optional)

        Returns:
            List of TextContent with the operation result.
        """
        # Create a mock request with the user for permission checking
        request = create_mock_request(user)
        return await call_tool(name, arguments, request)

    @classmethod
    def get_mcp_tools(cls, model: type[models.Model]) -> list[Tool]:
        """
        Get the list of MCP tools for a model.

        Delegates to the tools module for tool generation.

        Args:
            model: Django model class.

        Returns:
            List of Tool definitions for the model.
        """
        return get_model_tools(model)

    @classmethod
    def get_find_models_tool(cls) -> Tool:
        """
        Get the find_models tool for discovering available models.

        Delegates to the tools module for tool generation.

        Returns:
            Tool definition for find_models.
        """
        return get_find_models_tool()

    def __init__(self, *args, **kwargs):
        """Initialize the mixin and register MCP tools."""
        super().__init__(*args, **kwargs)
        # Register tools for this model
        self.__class__.register_model_tools(self)
