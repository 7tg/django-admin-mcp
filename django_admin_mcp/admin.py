"""
Admin configuration for django-admin-mcp models
"""

from django.contrib import admin
from .models import MCPToken


@admin.register(MCPToken)
class MCPTokenAdmin(admin.ModelAdmin):
    """Admin for MCP authentication tokens."""
    
    list_display = ['name', 'token_preview', 'is_active', 'created_at', 'last_used_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'token']
    readonly_fields = ['token', 'created_at', 'last_used_at']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'is_active')
        }),
        ('Token Information', {
            'fields': ('token', 'created_at', 'last_used_at'),
            'classes': ('collapse',)
        }),
    )
    
    def token_preview(self, obj):
        """Show a preview of the token."""
        if obj.token:
            return f"{obj.token[:8]}...{obj.token[-8:]}"
        return "-"
    token_preview.short_description = "Token"
