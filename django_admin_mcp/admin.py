"""
Admin configuration for django-admin-mcp models
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from django_admin_mcp.models import MCPToken


@admin.register(MCPToken)
class MCPTokenAdmin(admin.ModelAdmin):
    """Admin for MCP authentication tokens."""

    list_display = [
        "name",
        "token_preview",
        "user",
        "is_active",
        "status_display",
        "created_at",
        "expires_at",
        "last_used_at",
    ]
    list_filter = ["is_active", "created_at", "expires_at", "groups"]
    search_fields = ["name", "token", "user__username"]
    readonly_fields = ["token", "created_at", "last_used_at", "status_display"]
    filter_horizontal = ["groups", "permissions"]

    fieldsets = (
        (None, {"fields": ("name", "is_active", "expires_at")}),
        (
            "Permissions",
            {
                "fields": ("user", "groups", "permissions"),
                "description": "Assign a user, groups, or specific permissions to control access. "
                "Tokens with no permissions have no access (principle of least privilege).",
            },
        ),
        (
            "Token Information",
            {
                "fields": ("token", "created_at", "last_used_at", "status_display"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Token")
    def token_preview(self, obj):
        """Show a preview of the token."""
        if obj.token:
            return f"{obj.token[:8]}...{obj.token[-8:]}"
        return "-"

    @admin.display(description="Status")
    def status_display(self, obj):
        """Display token status with color coding."""
        if not obj.is_active:
            return mark_safe('<span style="color: #999;">Inactive</span>')
        elif obj.is_expired():
            return mark_safe('<span style="color: #dc3545;">Expired</span>')
        elif obj.expires_at is None:
            return mark_safe('<span style="color: #28a745;">Active (Indefinite)</span>')
        else:
            days_until_expiry = (obj.expires_at - timezone.now()).days
            if days_until_expiry <= 7:
                return format_html(
                    '<span style="color: #ffc107;">Expires in {} days</span>',
                    days_until_expiry,
                )
            else:
                return mark_safe('<span style="color: #28a745;">Active</span>')
