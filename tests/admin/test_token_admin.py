"""
Tests for django_admin_mcp admin configuration
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.utils import timezone

from django_admin_mcp.admin import MCPTokenAdmin
from django_admin_mcp.models import MCPToken
from tests.factories import MCPTokenFactory, UserFactory


@pytest.mark.django_db
class TestMCPTokenAdmin:
    """Test suite for MCPTokenAdmin."""

    def test_token_preview_with_token(self):
        """Test token_preview method shows token key prefix."""
        token = MCPTokenFactory()
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)

        preview = admin_instance.token_preview(token)

        # Should show mcp_ prefix and token key
        assert "mcp_" in preview
        assert token.token_key in preview
        assert "..." in preview  # Indicates truncation

    def test_token_preview_without_token(self):
        """Test token_preview method with empty token."""
        # Create a token instance without calling save to avoid auto-generation
        user = UserFactory()
        token = MCPToken(name="Test Token", user=user)
        # No token_key set

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

    def test_admin_form_blank_expires_at_creates_indefinite_token(self):
        """Leaving expires_at blank in the admin form must create an indefinite token."""
        user = UserFactory()
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)
        request = RequestFactory().get("/")
        request.user = user

        form_class = admin_instance.get_form(request)
        form = form_class(
            data={
                "name": "Blank expiry token",
                "is_active": "on",
                # The admin renders expires_at as a split date/time widget
                "expires_at_0": "",
                "expires_at_1": "",
                "user": str(user.pk),
            }
        )

        assert form.is_valid(), form.errors
        token = form.save()

        assert token.pk is not None
        assert token.expires_at is None

    def test_admin_form_explicit_expires_at_is_kept(self):
        """A date entered in the admin form is stored as given."""
        user = UserFactory()
        admin_instance = MCPTokenAdmin(MCPToken, admin.site)
        request = RequestFactory().get("/")
        request.user = user
        expiry = timezone.now() + timedelta(days=30)

        form_class = admin_instance.get_form(request)
        form = form_class(
            data={
                "name": "Dated token",
                "is_active": "on",
                # The admin renders expires_at as a split date/time widget
                "expires_at_0": expiry.strftime("%Y-%m-%d"),
                "expires_at_1": expiry.strftime("%H:%M:%S"),
                "user": str(user.pk),
            }
        )

        assert form.is_valid(), form.errors
        token = form.save()

        assert token.expires_at is not None


@pytest.mark.django_db
class TestRegenerateTokenView:
    """Token regeneration must be POST-only and permission-checked (issue #96)."""

    def _admin(self):
        return MCPTokenAdmin(MCPToken, admin.site)

    def test_get_request_does_not_regenerate(self):
        token = MCPTokenFactory()
        original_key = token.token_key
        staff = UserFactory(is_staff=True, is_superuser=True)
        request = RequestFactory().get(f"/admin/django_admin_mcp/mcptoken/{token.pk}/regenerate/")
        request.user = staff

        response = self._admin().regenerate_token_view(request, token.pk)

        assert response.status_code == 405
        token.refresh_from_db()
        assert token.token_key == original_key

    def test_post_without_change_permission_is_denied(self):
        token = MCPTokenFactory()
        original_key = token.token_key
        staff = UserFactory(is_staff=True)  # staff but no MCPToken permissions
        request = RequestFactory().post(f"/admin/django_admin_mcp/mcptoken/{token.pk}/regenerate/")
        request.user = staff

        with pytest.raises(PermissionDenied):
            self._admin().regenerate_token_view(request, token.pk)

        token.refresh_from_db()
        assert token.token_key == original_key

    def test_post_with_change_permission_regenerates(self):
        token = MCPTokenFactory()
        original_key = token.token_key
        staff = UserFactory(is_staff=True, is_superuser=True)
        request = RequestFactory().post(f"/admin/django_admin_mcp/mcptoken/{token.pk}/regenerate/")
        request.user = staff

        admin_instance = self._admin()
        with patch.object(MCPTokenAdmin, "message_user") as message_user:
            response = admin_instance.regenerate_token_view(request, token.pk)

        assert response.status_code == 302
        assert message_user.called
        token.refresh_from_db()
        assert token.token_key != original_key

    def test_regenerate_button_submits_via_post(self):
        token = MCPTokenFactory()
        html = self._admin().regenerate_token_button(token)

        assert 'formmethod="post"' in html
        assert "<a " not in html
