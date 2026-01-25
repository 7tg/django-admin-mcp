"""
Tests for MCPToken field filtering to ensure sensitive data is not exposed.
"""

import pytest
from django.contrib.auth.models import User

from django_admin_mcp.handlers import get_model_admin, serialize_instance
from django_admin_mcp.models import MCPToken


@pytest.mark.django_db
class TestMCPTokenFieldFiltering:
    """Tests for MCPToken serialization with sensitive field filtering."""

    def test_mcptoken_excludes_sensitive_fields(self):
        """Test that MCPToken serialization excludes token_key, token_hash, and salt."""
        # Create a user and token
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        token = MCPToken.objects.create(name="Test Token", user=user)

        # Get the MCPTokenAdmin
        _, model_admin = get_model_admin("mcptoken")
        assert model_admin is not None, "MCPToken should be registered with admin"

        # Serialize the token
        result = serialize_instance(token, model_admin)

        # Verify sensitive fields are NOT included
        assert "token_key" not in result, "token_key should be excluded from serialization"
        assert "token_hash" not in result, "token_hash should be excluded from serialization"
        assert "salt" not in result, "salt should be excluded from serialization"

        # Verify safe fields ARE included
        assert "id" in result
        assert "name" in result
        assert result["name"] == "Test Token"
        assert "user" in result
        assert "is_active" in result
        # Note: created_at and last_used_at might not be included by model_to_dict
        # since they are auto fields, but expires_at should be included
        assert "expires_at" in result

    def test_mcptoken_list_operation_excludes_sensitive_fields(self):
        """Test that list operations on MCPToken exclude sensitive fields."""
        # Create a user and token
        user = User.objects.create_user(username="listuser", email="list@example.com", password="testpass")
        token1 = MCPToken.objects.create(name="Token 1", user=user)
        token2 = MCPToken.objects.create(name="Token 2", user=user)

        # Get the MCPTokenAdmin
        _, model_admin = get_model_admin("mcptoken")

        # Serialize both tokens
        result1 = serialize_instance(token1, model_admin)
        result2 = serialize_instance(token2, model_admin)

        # Verify sensitive fields are NOT in any serialized token
        for result in [result1, result2]:
            assert "token_key" not in result
            assert "token_hash" not in result
            assert "salt" not in result
            assert "name" in result
            assert "is_active" in result
