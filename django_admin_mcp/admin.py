"""
Admin configuration for django-admin-mcp models
"""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
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
    search_fields = ["name", "user__username"]
    readonly_fields = [
        "token_key",
        "token_hash",
        "salt",
        "created_at",
        "last_used_at",
        "status_display",
        "regenerate_token_button",
    ]
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
                "fields": (
                    "token_key",
                    "token_hash",
                    "salt",
                    "created_at",
                    "last_used_at",
                    "status_display",
                    "regenerate_token_button",
                ),
                "classes": ("collapse",),
                "description": "Token format: mcp_<key>.<secret>. The key is stored for lookup, "
                "the secret is hashed for security.",
            },
        ),
    )

    def get_urls(self):
        """Add custom URL for regenerating tokens."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:token_id>/regenerate/",
                self.admin_site.admin_view(self.regenerate_token_view),
                name="django_admin_mcp_mcptoken_regenerate",
            ),
        ]
        return custom_urls + urls

    def regenerate_token_view(self, request, token_id):
        """View to regenerate a token."""
        token = self.get_object(request, token_id)
        if token is None:
            self.message_user(request, "Token not found.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:django_admin_mcp_mcptoken_changelist"))

        # Regenerate the token
        new_plaintext = token.regenerate_token()

        # Show the new token to the user
        self.message_user(
            request,
            format_html(
                "Token regenerated successfully. <strong>Copy this token now, it will not be shown again:</strong>"
                "<br><code style='background: #f5f5f5; padding: 8px 12px; display: inline-block; "
                "margin-top: 8px; font-size: 14px; border-radius: 4px; user-select: all;'>{}</code>",
                new_plaintext,
            ),
            messages.WARNING,
        )

        return HttpResponseRedirect(reverse("admin:django_admin_mcp_mcptoken_change", args=[token_id]))

    @admin.display(description="Regenerate Token")
    def regenerate_token_button(self, obj):
        """Display a button to regenerate the token."""
        if obj.pk:
            url = reverse("admin:django_admin_mcp_mcptoken_regenerate", args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" onclick="return confirm(\'Are you sure? '
                "This will invalidate the current token immediately.');\""
                'style="background: #dc3545; color: white; padding: 5px 10px; '
                'text-decoration: none; border-radius: 3px;">Regenerate Token</a>',
                url,
            )
        return "-"

    def save_model(self, request, obj, form, change):
        """Save the model and show the token on creation."""
        super().save_model(request, obj, form, change)

        if not change:
            # This is a new token, get the plaintext and show it
            plaintext = obj.get_plaintext_token()
            if plaintext:
                self.message_user(
                    request,
                    format_html(
                        "Token created successfully. <strong>Copy this token now, "
                        "it will not be shown again:</strong>"
                        "<br><code style='background: #f5f5f5; padding: 8px 12px; display: inline-block; "
                        "margin-top: 8px; font-size: 14px; border-radius: 4px; user-select: all;'>{}</code>",
                        plaintext,
                    ),
                    messages.WARNING,
                )

    @admin.display(description="Token")
    def token_preview(self, obj):
        """Show a preview of the token (key prefix only)."""
        if obj.token_key:
            return f"{obj.TOKEN_PREFIX}{obj.token_key}..."
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
