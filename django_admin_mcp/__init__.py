"""
Django Admin MCP - Expose Django admin models to MCP clients
"""

from django_admin_mcp.mixin import MCPAdminMixin
from django_admin_mcp.server import get_registered_models, get_server, run_mcp_server

__version__ = "0.1.0"
__author__ = "Barbaros Goren"
__email__ = "gorenbarbaros@gmail.com"
__all__ = [
    "MCPAdminMixin",
    "run_mcp_server",
    "get_registered_models",
    "get_server",
]
