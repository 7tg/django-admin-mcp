"""
Server management utilities for django-admin-mcp

This module provides utilities to run and manage the MCP server.
"""

from mcp.server.stdio import stdio_server

from django_admin_mcp.mixin import MCPAdminMixin


async def run_mcp_server():
    """
    Run the MCP server for Django admin.

    This should be called after Django apps are loaded and admin classes are registered.

    Example:
        # In a management command or standalone script
        import asyncio
        from django_admin_mcp.server import run_mcp_server

        asyncio.run(run_mcp_server())
    """
    server = MCPAdminMixin.get_mcp_server()

    # Register list_tools handler
    @server.list_tools()
    async def list_tools():
        """List all available MCP tools for registered models."""
        tools = []
        
        # Always include the find_models tool
        tools.append(MCPAdminMixin.get_find_models_tool())
        
        # Only include model-specific tools if explicitly exposed
        for model_name, model_info in MCPAdminMixin._registered_models.items():
            model = model_info["model"]
            admin = model_info["admin"]
            
            # Check if admin class has mcp_expose attribute set to True
            if getattr(admin, 'mcp_expose', False):
                tools.extend(MCPAdminMixin.get_mcp_tools(model))
        
        return tools

    # Register the centralized call_tool handler
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Handle all tool calls through the centralized handler."""
        return await MCPAdminMixin.handle_tool_call(name, arguments)

    # Run the server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def get_registered_models():
    """
    Get a dictionary of all registered models.

    Returns:
        dict: A dictionary mapping model names to their model and admin instances.
    """
    return MCPAdminMixin._registered_models.copy()


def get_server():
    """
    Get the MCP server instance.

    Returns:
        Server: The MCP server instance.
    """
    return MCPAdminMixin.get_mcp_server()
