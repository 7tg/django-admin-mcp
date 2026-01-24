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
    # Initialize types
    ClientInfo,
    # Content types
    Content,
    ImageContent,
    InitializeParams,
    InitializeResponse,
    InitializeResult,
    # Notification types
    NotificationsInitializedResponse,
    ServerCapabilities,
    ServerInfo,
    TextContent,
    # Tool types
    Tool,
    ToolResult,
    # Tools call types
    ToolsCallParams,
    ToolsCallRequest,
    ToolsCallResponse,
    ToolsCallResult,
    # Tools list types
    ToolsListRequest,
    ToolsListResponse,
    ToolsListResult,
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
    # Initialize types
    "ClientInfo",
    "InitializeParams",
    "InitializeResponse",
    "InitializeResult",
    "ServerCapabilities",
    "ServerInfo",
    # Notification types
    "NotificationsInitializedResponse",
    # Tools list types
    "ToolsListRequest",
    "ToolsListResponse",
    "ToolsListResult",
    # Tools call types
    "ToolsCallParams",
    "ToolsCallRequest",
    "ToolsCallResponse",
    "ToolsCallResult",
]
