"""
HTTP views for django-admin-mcp

Provides HTTP interface for MCP protocol with token-based authentication.

Two endpoints share the core auth/parse/validate/execute pipeline:
- ``MCPHTTPView`` (class-based) returns bare JSON responses (legacy shape)
- ``mcp_endpoint`` (function-based) returns JSON-RPC envelopes per the MCP spec
"""

from typing import Any

from asgiref.sync import sync_to_async
from django.db import DatabaseError, transaction
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pydantic import BaseModel, TypeAdapter, ValidationError

from django_admin_mcp import __version__
from django_admin_mcp.handlers.base import sanitize_pydantic_errors
from django_admin_mcp.models import MCPToken
from django_admin_mcp.prompts import PromptError, get_prompt, list_prompts
from django_admin_mcp.protocol import (
    InitializeResponse,
    InitializeResult,
    JsonRpcError,
    JsonRpcResponse,
    NotificationsInitializedResponse,
    ServerCapabilities,
    ServerInfo,
    TextContent,
    Tool,
    ToolsCallRequest,
    ToolsCallResponse,
    ToolsCallResult,
    ToolsListRequest,
    ToolsListResponse,
    ToolsListResult,
)
from django_admin_mcp.resources import ResourceError, list_resource_templates, list_resources, read_resource
from django_admin_mcp.tools import call_tool, get_tools


class RequestBody(BaseModel):
    """
    Base model for parsing MCP JSON-RPC request body.

    Represents the structure of JSON-RPC requests as per the MCP protocol,
    containing the method name, optional request ID, and optional parameters dict.
    """

    method: str
    id: str | int | None = None
    params: dict[str, Any] | None = None


# TypeAdapter for parsing arbitrary JSON dictionaries
dict_adapter: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


@sync_to_async
def authenticate_token(request):
    """
    Authenticate request using Bearer token with O(1) lookup.

    Token format: mcp_<key>.<secret>
    - key: used for indexed database lookup
    - secret: verified against stored hash

    Returns:
        MCPToken if valid, None otherwise
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token_value = auth_header[7:]  # Remove 'Bearer ' prefix

    try:
        # Parse token to extract key and secret
        parsed = MCPToken.parse_token(token_value)
        if not parsed:
            return None

        key, secret = parsed

        # O(1) lookup by key (indexed)
        token = MCPToken.get_by_key(key)
        if not token:
            return None

        # Verify the secret portion
        if not token.verify_secret(secret):
            return None

        # Check if token is valid (not expired)
        if not token.is_valid():
            return None

        token.mark_used()
        return token
    except (DatabaseError, ValueError):
        return None


def _unauthorized_response() -> JsonResponse:
    """401 response for missing/invalid tokens."""
    return JsonResponse({"error": "Invalid or missing authentication token"}, status=401)


def _parse_request_body(request: HttpRequest) -> tuple[RequestBody | None, JsonResponse | None]:
    """Parse the JSON-RPC request body; returns (body, None) or (None, error response)."""
    try:
        return RequestBody.model_validate_json(request.body), None
    except ValidationError:
        return None, JsonResponse({"error": "Invalid JSON in request body"}, status=400)


def _invalid_request_response(exc: ValidationError) -> JsonResponse:
    """400 response with sanitized Pydantic validation details."""
    return JsonResponse({"error": "Invalid request", "details": sanitize_pydantic_errors(exc.errors())}, status=400)


def _validate_tools_list(request: HttpRequest) -> JsonResponse | None:
    """Validate a tools/list request body; returns an error response or None."""
    try:
        ToolsListRequest.model_validate_json(request.body)
    except ValidationError as e:
        return _invalid_request_response(e)
    return None


def _request_for_token(token) -> HttpRequest:
    """Build a synthetic request carrying the token's user for permission checks."""
    tool_request = HttpRequest()
    tool_request.user = token.user if token else None  # type: ignore[assignment]
    return tool_request


async def _execute_tool(request_obj: ToolsCallRequest, token) -> list[TextContent]:
    """Run a tool call with a request carrying the token's user for permission checks."""
    return await call_tool(request_obj.name, request_obj.arguments, _request_for_token(token))


def _jsonrpc_result(request_id, result: Any) -> JsonResponse:
    """JSON-RPC success envelope."""
    return JsonResponse(JsonRpcResponse(id=request_id, result=result).model_dump())


def _jsonrpc_error(request_id, code: int, message: str) -> JsonResponse:
    """JSON-RPC error envelope."""
    return JsonResponse(JsonRpcResponse(id=request_id, error=JsonRpcError(code=code, message=message)).model_dump())


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(transaction.non_atomic_requests, name="dispatch")
class MCPHTTPView(View):
    """
    HTTP view for MCP protocol.

    Handles MCP requests over HTTP with token authentication.
    Responses use the legacy bare-JSON shape (no JSON-RPC envelope).
    """

    async def post(self, request):
        """Handle POST requests for MCP operations."""
        token = await authenticate_token(request)
        if not token:
            return _unauthorized_response()

        body, error = _parse_request_body(request)
        if error:
            return error
        assert body is not None  # narrowed by error check

        method = body.method

        if method == "tools/list":
            error = _validate_tools_list(request)
            if error:
                return error
            return await self.handle_list_tools(request)
        elif method == "tools/call":
            try:
                request_obj = ToolsCallRequest.model_validate_json(request.body)
            except ValidationError as e:
                return _invalid_request_response(e)
            return await self.handle_call_tool(request, request_obj, token=token)
        else:
            return JsonResponse({"error": f"Unknown method: {method}"}, status=400)

    async def handle_list_tools(self, request):
        """Handle tools/list request."""
        tools = get_tools()

        tools_data = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ]

        return JsonResponse({"tools": tools_data})

    async def handle_call_tool(self, request, request_obj: ToolsCallRequest, token=None):
        """Handle tools/call request."""
        result = await _execute_tool(request_obj, token)

        # Extract text from result - content.text is a JSON string
        if result and len(result) > 0:
            content = result[0]
            # Parse JSON string using Pydantic TypeAdapter
            response_data = dict_adapter.validate_json(content.text)
            return JsonResponse(response_data)
        else:
            return JsonResponse({"error": "No result from tool"}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def mcp_health(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok", "service": "django-admin-mcp"})


@transaction.non_atomic_requests
async def mcp_endpoint(request):
    """Main MCP HTTP endpoint (JSON-RPC envelope per the MCP spec)."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    token = await authenticate_token(request)
    if not token:
        return _unauthorized_response()

    body, error = _parse_request_body(request)
    if error:
        return error
    assert body is not None  # narrowed by error check

    method = body.method

    if method == "initialize":
        # Handle MCP initialization
        response = InitializeResponse(
            id=body.id,
            result=InitializeResult(
                protocolVersion="2025-11-25",
                serverInfo=ServerInfo(name="django-admin-mcp", version=__version__),
                capabilities=ServerCapabilities(),
            ),
        )
        return JsonResponse(response.model_dump())
    elif method == "notifications/initialized":
        # Client acknowledgement - just return success
        response = NotificationsInitializedResponse(id=body.id)
        return JsonResponse(response.model_dump())
    elif method == "tools/list":
        error = _validate_tools_list(request)
        if error:
            return error
        return await handle_list_tools_request(request, body.id)
    elif method == "tools/call":
        # Extract params from JSON-RPC structure
        params = body.params or {}
        # Build a flat structure for validation
        call_data = {"method": method, "name": params.get("name"), "arguments": params.get("arguments", {})}
        try:
            request_obj = ToolsCallRequest.model_validate(call_data)
        except ValidationError as e:
            return _invalid_request_response(e)
        return await handle_call_tool_request(request, request_obj, token=token, request_id=body.id)
    elif method == "prompts/list":
        return _jsonrpc_result(body.id, {"prompts": list_prompts()})
    elif method == "prompts/get":
        params = body.params or {}
        try:
            prompt = get_prompt(params.get("name", ""), params.get("arguments") or {})
        except PromptError as e:
            return _jsonrpc_error(body.id, -32602, str(e))
        return _jsonrpc_result(body.id, prompt)
    elif method == "resources/list":
        resources = await list_resources(_request_for_token(token))
        return _jsonrpc_result(body.id, {"resources": resources})
    elif method == "resources/templates/list":
        return _jsonrpc_result(body.id, {"resourceTemplates": list_resource_templates()})
    elif method == "resources/read":
        uri = (body.params or {}).get("uri")
        if not uri:
            return _jsonrpc_error(body.id, -32602, "uri parameter is required")
        try:
            contents = await read_resource(uri, _request_for_token(token))
        except ResourceError as e:
            return _jsonrpc_error(body.id, -32002, str(e))
        return _jsonrpc_result(body.id, {"contents": [contents]})
    else:
        return JsonResponse({"error": f"Unknown method: {method}"}, status=400)


# Mark as CSRF exempt
mcp_endpoint.csrf_exempt = True  # type: ignore[attr-defined]


async def handle_list_tools_request(request, request_id=None):
    """Handle tools/list request."""
    tools = get_tools()

    # Convert to Pydantic Tool models
    tool_models = [Tool(name=tool.name, description=tool.description, inputSchema=tool.inputSchema) for tool in tools]

    response = ToolsListResponse(
        id=request_id,
        result=ToolsListResult(tools=tool_models),
    )
    return JsonResponse(response.model_dump())


async def handle_call_tool_request(request, request_obj: ToolsCallRequest, token=None, request_id=None):
    """Handle tools/call request."""
    result = await _execute_tool(request_obj, token)

    # Extract text from result - content.text is already a JSON string
    if result and len(result) > 0:
        content = result[0]
        # Validate that content.text is valid JSON using Pydantic TypeAdapter
        # This provides type safety without the overhead of parse-then-reserialize
        try:
            dict_adapter.validate_json(content.text)
        except ValidationError as e:
            error_response = JsonRpcResponse(
                id=request_id,
                error=JsonRpcError(
                    code=-32000,
                    message="Invalid JSON in tool result",
                    data={"validation_errors": sanitize_pydantic_errors(e.errors())},
                ),
            )
            return JsonResponse(error_response.model_dump(), status=500)

        # Pass through the JSON string as-is
        response = ToolsCallResponse(
            id=request_id,
            result=ToolsCallResult(content=[TextContent(text=content.text)]),
        )
        return JsonResponse(response.model_dump())
    else:
        error_response = JsonRpcResponse(
            id=request_id,
            error=JsonRpcError(code=-32000, message="No result from tool"),
        )
        return JsonResponse(error_response.model_dump(), status=500)
