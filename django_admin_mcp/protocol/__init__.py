"""
MCP protocol types module.

This module provides Pydantic models for the MCP (Model Context Protocol)
including JSON-RPC message types, content types, and error codes.
"""

from django_admin_mcp.protocol.errors import MCPErrorCode
from django_admin_mcp.protocol.jsonrpc import (
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)
from django_admin_mcp.protocol.types import (
    Content,
    ImageContent,
    TextContent,
    Tool,
    ToolResult,
    ToolsCallRequest,
    ToolsListRequest,
)

__all__ = [
    # Error codes
    "MCPErrorCode",
    # JSON-RPC types
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    # Content types
    "Content",
    "ImageContent",
    "TextContent",
    # Tool types
    "Tool",
    "ToolResult",
    # MCP request types
    "ToolsCallRequest",
    "ToolsListRequest",
]
