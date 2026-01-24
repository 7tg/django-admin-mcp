"""
MCP protocol types for content and tool definitions.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from django_admin_mcp.protocol.jsonrpc import JsonRpcResponse

# =============================================================================
# Content Types
# =============================================================================


class TextContent(BaseModel):
    """Text content type for MCP responses."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content type for MCP responses."""

    type: Literal["image"] = "image"
    data: str
    mimeType: str


Content = TextContent | ImageContent


# =============================================================================
# Tool Definitions
# =============================================================================


class Tool(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class ToolResult(BaseModel):
    """Result of an MCP tool call."""

    content: list[Content]
    isError: bool = False


# =============================================================================
# Initialize Request/Response
# =============================================================================


class ClientInfo(BaseModel):
    """Client information sent during initialization."""

    name: str
    version: str


class InitializeParams(BaseModel):
    """Parameters for initialize request."""

    protocolVersion: str
    clientInfo: ClientInfo
    capabilities: dict[str, Any] = Field(default_factory=dict)


class ServerInfo(BaseModel):
    """Server information returned during initialization."""

    name: str
    version: str


class ServerCapabilities(BaseModel):
    """Server capabilities."""

    tools: dict[str, Any] = Field(default_factory=dict)


class InitializeResult(BaseModel):
    """Result of MCP initialization."""

    protocolVersion: str
    serverInfo: ServerInfo
    capabilities: ServerCapabilities


class InitializeResponse(JsonRpcResponse):
    """MCP initialize response."""

    result: InitializeResult  # type: ignore[assignment]


# =============================================================================
# Notifications
# =============================================================================


class NotificationsInitializedResponse(JsonRpcResponse):
    """Response to notifications/initialized."""

    result: dict[str, Any] = Field(default_factory=dict)  # type: ignore[assignment]


# =============================================================================
# Tools List Request/Response
# =============================================================================


class ToolsListRequest(BaseModel):
    """Request to list available MCP tools."""

    method: Literal["tools/list"]


class ToolsListResult(BaseModel):
    """Result of tools/list request."""

    tools: list[Tool]


class ToolsListResponse(JsonRpcResponse):
    """Response to tools/list request."""

    result: ToolsListResult  # type: ignore[assignment]


# =============================================================================
# Tools Call Request/Response
# =============================================================================


class ToolsCallParams(BaseModel):
    """Parameters for tools/call request."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolsCallRequest(BaseModel):
    """Request to call a specific MCP tool."""

    method: Literal["tools/call"]
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolsCallResult(BaseModel):
    """Result of tools/call request."""

    content: list[TextContent]


class ToolsCallResponse(JsonRpcResponse):
    """Response to tools/call request."""

    result: ToolsCallResult  # type: ignore[assignment]
