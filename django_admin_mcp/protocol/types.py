"""
MCP protocol types for content and tool definitions.
"""

from typing import Any, Literal

from pydantic import BaseModel


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


class Tool(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class ToolResult(BaseModel):
    """Result of an MCP tool call."""

    content: list[Content]
    isError: bool = False


class ToolsListRequest(BaseModel):
    """Request to list available MCP tools."""

    method: Literal["tools/list"]


class ToolsCallRequest(BaseModel):
    """Request to call a specific MCP tool."""

    method: Literal["tools/call"]
    name: str
    arguments: dict[str, Any] = {}
