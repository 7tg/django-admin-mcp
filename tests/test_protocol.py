"""
Tests for django_admin_mcp.protocol module.
"""

import pytest
from pydantic import ValidationError

from django_admin_mcp.protocol import (
    MCPErrorCode,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    TextContent,
    ImageContent,
    Tool,
    ToolResult,
)


class TestMCPErrorCode:
    """Test suite for MCPErrorCode constants."""

    def test_parse_error_value(self):
        """Test PARSE_ERROR has correct value."""
        assert MCPErrorCode.PARSE_ERROR == -32700

    def test_invalid_request_value(self):
        """Test INVALID_REQUEST has correct value."""
        assert MCPErrorCode.INVALID_REQUEST == -32600

    def test_method_not_found_value(self):
        """Test METHOD_NOT_FOUND has correct value."""
        assert MCPErrorCode.METHOD_NOT_FOUND == -32601

    def test_invalid_params_value(self):
        """Test INVALID_PARAMS has correct value."""
        assert MCPErrorCode.INVALID_PARAMS == -32602

    def test_internal_error_value(self):
        """Test INTERNAL_ERROR has correct value."""
        assert MCPErrorCode.INTERNAL_ERROR == -32603


class TestTextContent:
    """Test suite for TextContent model."""

    def test_create_text_content(self):
        """Test creating TextContent with required fields."""
        content = TextContent(text="Hello, world!")
        assert content.type == "text"
        assert content.text == "Hello, world!"

    def test_type_is_literal(self):
        """Test that type field defaults to 'text'."""
        content = TextContent(text="Test")
        assert content.type == "text"

    def test_text_content_serialization(self):
        """Test TextContent serializes correctly."""
        content = TextContent(text="Test message")
        data = content.model_dump()
        assert data == {"type": "text", "text": "Test message"}

    def test_text_content_from_dict(self):
        """Test TextContent can be created from dict."""
        content = TextContent.model_validate({"text": "From dict"})
        assert content.text == "From dict"
        assert content.type == "text"


class TestImageContent:
    """Test suite for ImageContent model."""

    def test_create_image_content(self):
        """Test creating ImageContent with required fields."""
        content = ImageContent(data="base64data", mimeType="image/png")
        assert content.type == "image"
        assert content.data == "base64data"
        assert content.mimeType == "image/png"

    def test_type_is_literal(self):
        """Test that type field defaults to 'image'."""
        content = ImageContent(data="data", mimeType="image/jpeg")
        assert content.type == "image"

    def test_image_content_serialization(self):
        """Test ImageContent serializes correctly."""
        content = ImageContent(data="abc123", mimeType="image/gif")
        data = content.model_dump()
        assert data == {"type": "image", "data": "abc123", "mimeType": "image/gif"}

    def test_image_content_from_dict(self):
        """Test ImageContent can be created from dict."""
        content = ImageContent.model_validate(
            {"data": "base64", "mimeType": "image/webp"}
        )
        assert content.data == "base64"
        assert content.mimeType == "image/webp"

    def test_image_content_missing_fields(self):
        """Test ImageContent raises error for missing required fields."""
        with pytest.raises(ValidationError):
            ImageContent(data="data")  # missing mimeType
        with pytest.raises(ValidationError):
            ImageContent(mimeType="image/png")  # missing data


class TestTool:
    """Test suite for Tool model."""

    def test_create_tool(self):
        """Test creating Tool with required fields."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object", "properties": {}},
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.inputSchema == {"type": "object", "properties": {}}

    def test_tool_serialization(self):
        """Test Tool serializes correctly."""
        tool = Tool(
            name="my_tool",
            description="Does something",
            inputSchema={"type": "object"},
        )
        data = tool.model_dump()
        assert data == {
            "name": "my_tool",
            "description": "Does something",
            "inputSchema": {"type": "object"},
        }

    def test_tool_from_dict(self):
        """Test Tool can be created from dict."""
        tool = Tool.model_validate(
            {
                "name": "dict_tool",
                "description": "From dict",
                "inputSchema": {"type": "object", "required": ["id"]},
            }
        )
        assert tool.name == "dict_tool"
        assert tool.inputSchema["required"] == ["id"]

    def test_tool_missing_fields(self):
        """Test Tool raises error for missing required fields."""
        with pytest.raises(ValidationError):
            Tool(name="test")  # missing description and inputSchema


class TestToolResult:
    """Test suite for ToolResult model."""

    def test_create_tool_result_success(self):
        """Test creating successful ToolResult."""
        result = ToolResult(content=[TextContent(text="Success")])
        assert len(result.content) == 1
        assert result.content[0].text == "Success"
        assert result.isError is False

    def test_create_tool_result_error(self):
        """Test creating error ToolResult."""
        result = ToolResult(content=[TextContent(text="Error occurred")], isError=True)
        assert result.isError is True

    def test_tool_result_with_multiple_content(self):
        """Test ToolResult with multiple content items."""
        result = ToolResult(
            content=[
                TextContent(text="First"),
                TextContent(text="Second"),
            ]
        )
        assert len(result.content) == 2
        assert result.content[0].text == "First"
        assert result.content[1].text == "Second"

    def test_tool_result_with_image_content(self):
        """Test ToolResult with image content."""
        result = ToolResult(
            content=[ImageContent(data="base64data", mimeType="image/png")]
        )
        assert result.content[0].type == "image"
        assert result.content[0].data == "base64data"

    def test_tool_result_serialization(self):
        """Test ToolResult serializes correctly."""
        result = ToolResult(content=[TextContent(text="Test")], isError=False)
        data = result.model_dump()
        assert data == {
            "content": [{"type": "text", "text": "Test"}],
            "isError": False,
        }

    def test_tool_result_default_is_error(self):
        """Test ToolResult defaults isError to False."""
        result = ToolResult(content=[])
        assert result.isError is False


class TestJsonRpcError:
    """Test suite for JsonRpcError model."""

    def test_create_error(self):
        """Test creating JsonRpcError with required fields."""
        error = JsonRpcError(code=-32600, message="Invalid Request")
        assert error.code == -32600
        assert error.message == "Invalid Request"
        assert error.data is None

    def test_create_error_with_data(self):
        """Test creating JsonRpcError with optional data."""
        error = JsonRpcError(
            code=-32602,
            message="Invalid params",
            data={"field": "id", "error": "must be integer"},
        )
        assert error.data == {"field": "id", "error": "must be integer"}

    def test_error_serialization(self):
        """Test JsonRpcError serializes correctly."""
        error = JsonRpcError(code=-32700, message="Parse error")
        data = error.model_dump()
        assert data == {"code": -32700, "message": "Parse error", "data": None}

    def test_error_from_dict(self):
        """Test JsonRpcError can be created from dict."""
        error = JsonRpcError.model_validate(
            {"code": -32603, "message": "Internal error"}
        )
        assert error.code == -32603


class TestJsonRpcRequest:
    """Test suite for JsonRpcRequest model."""

    def test_create_request_minimal(self):
        """Test creating JsonRpcRequest with minimal fields."""
        request = JsonRpcRequest(id=1, method="test_method")
        assert request.jsonrpc == "2.0"
        assert request.id == 1
        assert request.method == "test_method"
        assert request.params is None

    def test_create_request_with_params(self):
        """Test creating JsonRpcRequest with params."""
        request = JsonRpcRequest(
            id="request-123", method="call_tool", params={"name": "test", "args": {}}
        )
        assert request.id == "request-123"
        assert request.params == {"name": "test", "args": {}}

    def test_request_string_id(self):
        """Test JsonRpcRequest accepts string id."""
        request = JsonRpcRequest(id="abc-123", method="test")
        assert request.id == "abc-123"

    def test_request_integer_id(self):
        """Test JsonRpcRequest accepts integer id."""
        request = JsonRpcRequest(id=42, method="test")
        assert request.id == 42

    def test_request_serialization(self):
        """Test JsonRpcRequest serializes correctly."""
        request = JsonRpcRequest(id=1, method="list_tools")
        data = request.model_dump()
        assert data == {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "list_tools",
            "params": None,
        }

    def test_request_from_dict(self):
        """Test JsonRpcRequest can be created from dict."""
        request = JsonRpcRequest.model_validate(
            {"id": 5, "method": "initialize", "params": {"version": "1.0"}}
        )
        assert request.method == "initialize"
        assert request.params["version"] == "1.0"


class TestJsonRpcResponse:
    """Test suite for JsonRpcResponse model."""

    def test_create_success_response(self):
        """Test creating successful JsonRpcResponse."""
        response = JsonRpcResponse(id=1, result={"status": "ok"})
        assert response.jsonrpc == "2.0"
        assert response.id == 1
        assert response.result == {"status": "ok"}
        assert response.error is None

    def test_create_error_response(self):
        """Test creating error JsonRpcResponse."""
        error = JsonRpcError(code=-32600, message="Invalid Request")
        response = JsonRpcResponse(id=1, error=error)
        assert response.result is None
        assert response.error.code == -32600

    def test_response_string_id(self):
        """Test JsonRpcResponse accepts string id."""
        response = JsonRpcResponse(id="resp-123", result=None)
        assert response.id == "resp-123"

    def test_response_serialization(self):
        """Test JsonRpcResponse serializes correctly."""
        response = JsonRpcResponse(id=1, result=["tool1", "tool2"])
        data = response.model_dump()
        assert data == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": ["tool1", "tool2"],
            "error": None,
        }

    def test_response_with_nested_error(self):
        """Test JsonRpcResponse with error serializes correctly."""
        response = JsonRpcResponse(
            id=1, error=JsonRpcError(code=-32601, message="Method not found")
        )
        data = response.model_dump()
        assert data["error"]["code"] == -32601
        assert data["error"]["message"] == "Method not found"

    def test_response_from_dict(self):
        """Test JsonRpcResponse can be created from dict."""
        response = JsonRpcResponse.model_validate(
            {"id": 2, "result": {"tools": []}, "jsonrpc": "2.0"}
        )
        assert response.result == {"tools": []}


class TestProtocolModuleExports:
    """Test suite for protocol module exports."""

    def test_all_types_exported(self):
        """Test that all types are exported from protocol module."""
        from django_admin_mcp import protocol

        assert hasattr(protocol, "MCPErrorCode")
        assert hasattr(protocol, "JsonRpcError")
        assert hasattr(protocol, "JsonRpcRequest")
        assert hasattr(protocol, "JsonRpcResponse")
        assert hasattr(protocol, "TextContent")
        assert hasattr(protocol, "ImageContent")
        assert hasattr(protocol, "Content")
        assert hasattr(protocol, "Tool")
        assert hasattr(protocol, "ToolResult")

    def test_direct_imports_work(self):
        """Test that direct imports from submodules work."""
        from django_admin_mcp.protocol.errors import MCPErrorCode
        from django_admin_mcp.protocol.jsonrpc import JsonRpcRequest
        from django_admin_mcp.protocol.types import TextContent

        assert MCPErrorCode.PARSE_ERROR == -32700
        assert JsonRpcRequest(id=1, method="test").jsonrpc == "2.0"
        assert TextContent(text="test").type == "text"
