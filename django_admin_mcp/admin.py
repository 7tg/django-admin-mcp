"""
Admin configuration for django-admin-mcp models
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import MCPToken


@admin.register(MCPToken)
class MCPTokenAdmin(admin.ModelAdmin):
    """Admin for MCP authentication tokens."""
    
    list_display = ['name', 'token_preview', 'is_active', 'status_display', 'created_at', 'expires_at', 'last_used_at']
    list_filter = ['is_active', 'created_at', 'expires_at']
    search_fields = ['name', 'token']
    readonly_fields = ['token', 'created_at', 'last_used_at', 'status_display']
    
    fieldsets = (
        (None, {
            'fields': ('name', 'is_active', 'expires_at')
        }),
        ('Token Information', {
            'fields': ('token', 'created_at', 'last_used_at', 'status_display'),
            'classes': ('collapse',)
        }),
    )
    
    def token_preview(self, obj):
        """Show a preview of the token."""
        if obj.token:
            return f"{obj.token[:8]}...{obj.token[-8:]}"
        return "-"
    token_preview.short_description = "Token"
    
    def status_display(self, obj):
        """Display token status with color coding."""
        if not obj.is_active:
            return format_html('<span style="color: #999;">Inactive</span>')
        elif obj.is_expired():
            return format_html('<span style="color: #dc3545;">Expired</span>')
        elif obj.expires_at is None:
            return format_html('<span style="color: #28a745;">Active (Indefinite)</span>')
        else:
            days_until_expiry = (obj.expires_at - timezone.now()).days
            if days_until_expiry <= 7:
                return format_html('<span style="color: #ffc107;">Expires in {} days</span>', days_until_expiry)
            else:
                return format_html('<span style="color: #28a745;">Active</span>')
    status_display.short_description = "Status"
