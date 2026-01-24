"""
HTTP views for django-admin-mcp

Provides HTTP interface for MCP protocol with token-based authentication.
"""

import json

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pydantic import ValidationError

from django_admin_mcp.models import MCPToken
from django_admin_mcp.protocol import ToolsCallRequest, ToolsListRequest
from django_admin_mcp.tools import call_tool, get_tools


@sync_to_async
def authenticate_token(request):
    """
    Authenticate request using Bearer token.

    Returns:
        MCPToken if valid, None otherwise
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token_value = auth_header[7:]  # Remove 'Bearer ' prefix

    try:
        # Use select_related to pre-load user for async access
        token = MCPToken.objects.select_related("user").get(token=token_value)

        # Check if token is valid (active and not expired)
        if not token.is_valid():
            return None

        token.mark_used()
        return token
    except MCPToken.DoesNotExist:
        return None


@method_decorator(csrf_exempt, name="dispatch")
class MCPHTTPView(View):
    """
    HTTP view for MCP protocol.

    Handles MCP requests over HTTP with token authentication.
    """

    async def post(self, request):
        """Handle POST requests for MCP operations."""
        # Authenticate request
        token = await authenticate_token(request)
        if not token:
            return JsonResponse({"error": "Invalid or missing authentication token"}, status=401)

        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

        # Get method from request to determine which model to use
        method = data.get("method")

        if method == "tools/list":
            # Validate with ToolsListRequest
            try:
                _ = ToolsListRequest.model_validate(data)
            except ValidationError as e:
                return JsonResponse({"error": "Invalid request", "details": e.errors()}, status=400)
            return await self.handle_list_tools(request)
        elif method == "tools/call":
            # Validate with ToolsCallRequest
            try:
                request_obj = ToolsCallRequest.model_validate(data)
            except ValidationError as e:
                return JsonResponse({"error": "Invalid request", "details": e.errors()}, status=400)
            return await self.handle_call_tool(request, request_obj, token=token)
        else:
            return JsonResponse({"error": f"Unknown method: {method}"}, status=400)

    async def handle_list_tools(self, request):
        """Handle tools/list request."""
        tools = get_tools()

        # Serialize tools to dict format
        tools_data = []
        for tool in tools:
            tools_data.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
            )

        return JsonResponse({"tools": tools_data})

    async def handle_call_tool(self, request, request_obj: ToolsCallRequest, token=None):
        """Handle tools/call request."""
        tool_name = request_obj.name
        arguments = request_obj.arguments

        # Create request with user for permission checking
        tool_request = HttpRequest()
        tool_request.user = token.user if token else None  # type: ignore[assignment]

        # Call the tool with request context
        result = await call_tool(tool_name, arguments, tool_request)

        # Extract text from result
        if result and len(result) > 0:
            content = result[0]
            response_data = json.loads(content.text)
            return JsonResponse(response_data)
        else:
            return JsonResponse({"error": "No result from tool"}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def mcp_health(request):
    """Health check endpoint."""
    return JsonResponse({"status": "ok", "service": "django-admin-mcp"})


async def mcp_endpoint(request):
    """Main MCP HTTP endpoint."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # Authenticate request
    token = await authenticate_token(request)
    if not token:
        return JsonResponse({"error": "Invalid or missing authentication token"}, status=401)

    # Parse request body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

    # Get method from request to determine which model to use
    method = data.get("method")

    if method == "tools/list":
        # Validate with ToolsListRequest
        try:
            _ = ToolsListRequest.model_validate(data)
        except ValidationError as e:
            return JsonResponse({"error": "Invalid request", "details": e.errors()}, status=400)
        return await handle_list_tools_request(request)
    elif method == "tools/call":
        # Validate with ToolsCallRequest
        try:
            request_obj = ToolsCallRequest.model_validate(data)
        except ValidationError as e:
            return JsonResponse({"error": "Invalid request", "details": e.errors()}, status=400)
        return await handle_call_tool_request(request, request_obj, token=token)
    else:
        return JsonResponse({"error": f"Unknown method: {method}"}, status=400)


# Mark as CSRF exempt
mcp_endpoint.csrf_exempt = True  # type: ignore[attr-defined]


async def handle_list_tools_request(request):
    """Handle tools/list request."""
    tools = get_tools()

    # Serialize tools to dict format
    tools_data = []
    for tool in tools:
        tools_data.append(
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
        )

    return JsonResponse({"tools": tools_data})


async def handle_call_tool_request(request, request_obj: ToolsCallRequest, token=None):
    """Handle tools/call request."""
    tool_name = request_obj.name
    arguments = request_obj.arguments

    # Create request with user for permission checking
    tool_request = HttpRequest()
    tool_request.user = token.user if token else None  # type: ignore[assignment]

    # Call the tool with request context
    result = await call_tool(tool_name, arguments, tool_request)

    # Extract text from result
    if result and len(result) > 0:
        content = result[0]
        response_data = json.loads(content.text)
        return JsonResponse(response_data)
    else:
        return JsonResponse({"error": "No result from tool"}, status=500)
