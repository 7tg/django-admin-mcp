"""
Tests for django_admin_mcp admin configuration
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.utils import timezone

from django_admin_mcp.admin import MCPTokenAdmin
from django_admin_mcp.models import MCPToken
from tests.factories import MCPTokenFactory, UserFactory


@pytest.mark.django_db
class TestMCPTokenAdmin:
    """Test suite for MCPTokenAdmin."""

    def test_token_preview_with_token(self):
        """Test token_preview method shows preview of token hash."""
        token = MCPTokenFactory()
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        preview = admin_instance.token_preview(token)

        # Should show first 8 and last 8 characters of the hash
        assert "Hash:" in preview
        assert token.token_hash[:8] in preview
        assert token.token_hash[-8:] in preview

    def test_token_preview_without_token(self):
        """Test token_preview method with empty token."""
        # Create a token instance without calling save to avoid auto-generation
        user = UserFactory()
        token = MCPToken(name="Test Token", user=user)
        # No token_hash or token set

        admin_instance = MCPTokenAdmin(MCPToken, admin.site)
        preview = admin_instance.token_preview(token)

        assert preview == "-"

    def test_status_display_inactive(self):
        """Test status_display for inactive token."""
        token = MCPTokenFactory(is_active=False)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        status = admin_instance.status_display(token)

        assert "Inactive" in status
        assert "#999" in status  # Check for color code

    def test_status_display_expired(self):
        """Test status_display for expired token."""
        past_date = timezone.now() - timedelta(days=1)
        token = MCPTokenFactory(is_active=True, expires_at=past_date)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        status = admin_instance.status_display(token)

        assert "Expired" in status
        assert "#dc3545" in status  # Check for color code

    def test_status_display_active_indefinite(self):
        """Test status_display for active indefinite token."""
        token = MCPTokenFactory(is_active=True, expires_at=None)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        status = admin_instance.status_display(token)

        assert "Active (Indefinite)" in status
        assert "#28a745" in status  # Check for color code

    def test_status_display_expires_soon(self):
        """Test status_display for token expiring within 7 days."""
        # Token expires in 5 days
        future_date = timezone.now() + timedelta(days=5)
        token = MCPTokenFactory(is_active=True, expires_at=future_date)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        status = admin_instance.status_display(token)

        assert "Expires in" in status
        assert "days" in status
        assert "#ffc107" in status  # Check for warning color code

    def test_status_display_active_future(self):
        """Test status_display for active token with future expiry."""
        # Token expires in 30 days (more than 7 days)
        future_date = timezone.now() + timedelta(days=30)
        token = MCPTokenFactory(is_active=True, expires_at=future_date)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        status = admin_instance.status_display(token)

        assert "Active" in status
        assert "#28a745" in status  # Check for success color code

    def test_admin_registered(self):
        """Test that MCPTokenAdmin is registered with admin site."""
        assert MCPToken in admin.site._registry
        assert isinstance(admin.site._registry[MCPToken], MCPTokenAdmin)

    def test_regenerate_token_button_with_saved_token(self):
        """Test regenerate_token_button shows button for saved token."""
        token = MCPTokenFactory()
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        # Mock reverse since admin URLs may not be set up in test context
        with patch("django_admin_mcp.admin.reverse") as mock_reverse:
            mock_reverse.return_value = f"/admin/django_admin_mcp/mcptoken/{token.pk}/regenerate/"
            button_html = admin_instance.regenerate_token_button(token)

        assert "Regenerate Token" in button_html
        assert "/regenerate/" in button_html
        assert "confirm(" in button_html  # JavaScript confirmation

    def test_regenerate_token_button_without_pk(self):
        """Test regenerate_token_button shows dash for unsaved token."""
        user = UserFactory()
        token = MCPToken(name="Unsaved", user=user)
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        button_html = admin_instance.regenerate_token_button(token)

        assert button_html == "-"

    def test_readonly_fields_include_regenerate_button(self):
        """Test that regenerate_token_button is in readonly_fields."""
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        assert "regenerate_token_button" in admin_instance.readonly_fields
