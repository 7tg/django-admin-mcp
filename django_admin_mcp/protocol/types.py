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
