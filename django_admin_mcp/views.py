"""
HTTP views for django-admin-mcp

Provides HTTP interface for MCP protocol with token-based authentication.
"""

import json
from typing import Any, Dict, List

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from asgiref.sync import sync_to_async

from django_admin_mcp.models import MCPToken
from django_admin_mcp.mixin import MCPAdminMixin


@sync_to_async
def authenticate_token(request):
    """
    Authenticate request using Bearer token.
    
    Returns:
        MCPToken if valid, None otherwise
    """
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token_value = auth_header[7:]  # Remove 'Bearer ' prefix
    
    try:
        token = MCPToken.objects.get(token=token_value)
        
        # Check if token is valid (active and not expired)
        if not token.is_valid():
            return None
        
        token.mark_used()
        return token
    except MCPToken.DoesNotExist:
        return None


@method_decorator(csrf_exempt, name='dispatch')
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
            return JsonResponse({
                'error': 'Invalid or missing authentication token'
            }, status=401)
        
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON in request body'
            }, status=400)
        
        # Get method from request
        method = data.get('method')
        
        if method == 'tools/list':
            return await self.handle_list_tools(request)
        elif method == 'tools/call':
            return await self.handle_call_tool(request, data)
        else:
            return JsonResponse({
                'error': f'Unknown method: {method}'
            }, status=400)
    
    async def handle_list_tools(self, request):
        """Handle tools/list request."""
        tools = []
        for model_name, model_info in MCPAdminMixin._registered_models.items():
            model = model_info["model"]
            admin = model_info["admin"]
            
            # Check if tools should be exposed
            if not getattr(admin, 'mcp_expose', False):
                continue
            
            tools.extend(MCPAdminMixin.get_mcp_tools(model))
        
        # Serialize tools to dict format
        tools_data = []
        for tool in tools:
            tools_data.append({
                'name': tool.name,
                'description': tool.description,
                'inputSchema': tool.inputSchema
            })
        
        return JsonResponse({
            'tools': tools_data
        })
    
    async def handle_call_tool(self, request, data):
        """Handle tools/call request."""
        tool_name = data.get('name')
        arguments = data.get('arguments', {})
        
        if not tool_name:
            return JsonResponse({
                'error': 'Missing tool name'
            }, status=400)
        
        # Call the tool
        result = await MCPAdminMixin.handle_tool_call(tool_name, arguments)
        
        # Extract text from result
        if result and len(result) > 0:
            content = result[0]
            response_data = json.loads(content.text)
            return JsonResponse(response_data)
        else:
            return JsonResponse({
                'error': 'No result from tool'
            }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def mcp_health(request):
    """Health check endpoint."""
    return JsonResponse({
        'status': 'ok',
        'service': 'django-admin-mcp'
    })


@csrf_exempt
@require_http_methods(["POST"])
async def mcp_endpoint(request):
    """Main MCP HTTP endpoint."""
    view = MCPHTTPView()
    return await view.post(request)
