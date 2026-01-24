"""
Tests for MCPToken model and mcp_expose behavior
"""

import json
from datetime import timedelta

import django
import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.test import AsyncClient
from django.utils import timezone

from tests.factories import MCPTokenFactory
from tests.models import Author

# AsyncClient headers= parameter requires Django 4.2+
DJANGO_42_PLUS = django.VERSION >= (4, 2)
skip_if_django_lt_42 = pytest.mark.skipif(
    not DJANGO_42_PLUS, reason="AsyncClient headers= parameter requires Django 4.2+"
)


@pytest.mark.django_db(transaction=True)
class TestMCPToken:
    """Test suite for MCPToken model."""

    def test_token_auto_generated(self):
        """Test that token is auto-generated on save."""
        token = MCPTokenFactory()
        assert token.plaintext_token is not None
        assert len(token.plaintext_token) > 0

    def test_token_unique(self):
        """Test that tokens are unique."""
        token1 = MCPTokenFactory()
        token2 = MCPTokenFactory()
        assert token1.plaintext_token != token2.plaintext_token

    def test_token_string_representation(self):
        """Test string representation of token."""
        token = MCPTokenFactory(name="My Token")
        str_repr = str(token)
        assert "My Token" in str_repr
        # String representation shows token key prefix for identification
        assert f"mcp_{token.token_key}" in str_repr

    def test_token_default_expiry(self):
        """Test that tokens have default 90-day expiry."""
        token = MCPTokenFactory()
        assert token.expires_at is not None

        # Check that expiry is approximately 90 days from now
        expected_expiry = timezone.now() + timedelta(days=90)
        time_diff = abs((token.expires_at - expected_expiry).total_seconds())
        assert time_diff < 60  # Allow 1 minute tolerance

    def test_token_indefinite_expiry(self):
        """Test creating token with no expiry."""
        token = MCPTokenFactory(expires_at=None)
        assert token.expires_at is None
        assert not token.is_expired()
        assert token.is_valid()

    def test_token_custom_expiry(self):
        """Test creating token with custom expiry."""
        custom_expiry = timezone.now() + timedelta(days=30)
        token = MCPTokenFactory(expires_at=custom_expiry)
        assert token.expires_at == custom_expiry
        assert not token.is_expired()

    def test_token_expired(self):
        """Test that expired tokens are detected."""
        past_date = timezone.now() - timedelta(days=1)
        token = MCPTokenFactory(expires_at=past_date)
        assert token.is_expired()
        assert not token.is_valid()

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_expired_token_rejected(self):
        """Test that expired tokens are rejected in authentication."""
        past_date = timezone.now() - timedelta(days=1)
        token = await sync_to_async(MCPTokenFactory)(expires_at=past_date)

        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.plaintext_token}"},
        )

        assert response.status_code == 401
        data = json.loads(response.content)
        assert "error" in data


@pytest.mark.django_db(transaction=True)
class TestMCPExpose:
    """Test suite for mcp_expose opt-in behavior."""

    @skip_if_django_lt_42
    @pytest.mark.asyncio
    async def test_tools_not_exposed_without_mcp_expose(self):
        """Test that tools are not exposed when mcp_expose is False."""

        # Get the registered admin
        admin_class = admin.site._registry.get(Author).__class__

        # Temporarily set mcp_expose to False
        original_mcp_expose = getattr(admin_class, "mcp_expose", None)

        # Get the actual admin instance from registry
        admin_instance = admin.site._registry[Author]
        admin_instance.mcp_expose = False

        try:
            # Create a token
            token = await sync_to_async(MCPTokenFactory)()

            client = AsyncClient()
            response = await client.post(
                "/api/mcp/",
                data=json.dumps({"method": "tools/list"}),
                content_type="application/json",
                headers={"Authorization": f"Bearer {token.plaintext_token}"},
            )

            assert response.status_code == 200
            data = json.loads(response.content)

            # Tools for Author should NOT be in the list (but find_models should be)
            tool_names = [tool["name"] for tool in data["tools"]]
            assert "find_models" in tool_names  # This tool is always available
            assert "list_author" not in tool_names
        finally:
            # Restore original value
            if original_mcp_expose is not None:
                admin_instance.mcp_expose = original_mcp_expose
            elif hasattr(admin_instance, "mcp_expose"):
                delattr(admin_instance, "mcp_expose")
