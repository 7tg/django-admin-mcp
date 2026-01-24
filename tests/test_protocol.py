"""
Tests for django_admin_mcp.protocol module.
"""

import pytest
from pydantic import ValidationError

from django_admin_mcp.protocol import (
    ImageContent,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    TextContent,
    Tool,
    ToolResult,
    ToolsCallRequest,
    ToolsListRequest,
)


class TestTextContent:
    """Test suite for TextContent model."""

    def test_create_text_content(self):
        """Test creating TextContent with required fields."""
        content = TextContent(text="Hello, world!")
        assert content.type == "text"
        assert content.text == "Hello, world!"

    def test_text_content_serialization(self):
        """Test TextContent serializes correctly."""
        content = TextContent(text="Test message")
        data = content.model_dump()
        assert data == {"type": "text", "text": "Test message"}


class TestImageContent:
    """Test suite for ImageContent model."""

    def test_create_image_content(self):
        """Test creating ImageContent with required fields."""
        content = ImageContent(data="base64data", mimeType="image/png")
        assert content.type == "image"
        assert content.data == "base64data"
        assert content.mimeType == "image/png"

    def test_image_content_serialization(self):
        """Test ImageContent serializes correctly."""
        content = ImageContent(data="abc123", mimeType="image/gif")
        data = content.model_dump()
        assert data == {"type": "image", "data": "abc123", "mimeType": "image/gif"}


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
        result = ToolResult(content=[ImageContent(data="base64data", mimeType="image/png")])
        assert result.content[0].type == "image"
        assert result.content[0].data == "base64data"


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
        request = JsonRpcRequest(id="request-123", method="call_tool", params={"name": "test", "args": {}})
        assert request.id == "request-123"
        assert request.params == {"name": "test", "args": {}}

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
        response = JsonRpcResponse(id=1, error=JsonRpcError(code=-32601, message="Method not found"))
        data = response.model_dump()
        assert data["error"]["code"] == -32601
        assert data["error"]["message"] == "Method not found"


class TestMCPRequests:
    """Test suite for MCP request models."""

    def test_tools_list_request(self):
        """Test ToolsListRequest validation."""
        # Valid request
        request = ToolsListRequest(method="tools/list")
        assert request.method == "tools/list"
        assert request.model_dump() == {"method": "tools/list"}

    def test_tools_list_request_invalid_method(self):
        """Test ToolsListRequest rejects invalid method."""
        # Invalid method should fail
        with pytest.raises(ValidationError) as exc_info:
            ToolsListRequest(method="invalid/method")
        assert len(exc_info.value.errors()) > 0
        assert "method" in str(exc_info.value)

    def test_tools_call_request(self):
        """Test ToolsCallRequest validation."""
        # Valid request with arguments
        request = ToolsCallRequest(method="tools/call", name="find_models", arguments={"query": "article"})
        assert request.method == "tools/call"
        assert request.name == "find_models"
        assert request.arguments == {"query": "article"}

    def test_tools_call_request_default_arguments(self):
        """Test ToolsCallRequest with default empty arguments."""
        # Request without arguments should default to empty dict
        request = ToolsCallRequest(method="tools/call", name="find_models")
        assert request.method == "tools/call"
        assert request.name == "find_models"
        assert request.arguments == {}

    def test_tools_call_request_missing_name(self):
        """Test ToolsCallRequest requires name field."""
        # Missing name should fail
        with pytest.raises(ValidationError) as exc_info:
            ToolsCallRequest(method="tools/call")
        assert len(exc_info.value.errors()) > 0
        # Check that 'name' field is mentioned in the error
        error_fields = [err["loc"][0] for err in exc_info.value.errors()]
        assert "name" in error_fields

    def test_tools_call_request_serialization(self):
        """Test ToolsCallRequest serializes correctly."""
        request = ToolsCallRequest(method="tools/call", name="list_article", arguments={"limit": 10})
        data = request.model_dump()
        assert data == {"method": "tools/call", "name": "list_article", "arguments": {"limit": 10}}
