"""
URL patterns for django-admin-mcp HTTP interface
"""

from django.urls import path, re_path

from django_admin_mcp import views
from django_admin_mcp.models import MCPToken

app_name = "django_admin_mcp"

urlpatterns = [
    path("", views.mcp_endpoint, name="mcp_endpoint"),
    path("health/", views.mcp_health, name="health"),
    # Bearer token carried in the path, for clients that cannot send headers.
    # Anchored on the token prefix so it can never shadow a named route, and
    # 404s unless MCP_ALLOW_URL_TOKEN is enabled.
    re_path(
        rf"^(?P<token>{MCPToken.TOKEN_PREFIX}[^/]+)/$",
        views.mcp_endpoint_url_token,
        name="mcp_endpoint_url_token",
    ),
]
