"""
Tests for HTTP interface and token authentication
"""

import json
import pytest
from django.test import Client
from django_admin_mcp.models import MCPToken


@pytest.mark.django_db
class TestHTTPInterface:
    """Test suite for HTTP interface."""

    def test_health_endpoint(self):
        """Test health check endpoint."""
        client = Client()
        response = client.get('/api/health/')
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'ok'
        assert data['service'] == 'django-admin-mcp'

    def test_mcp_endpoint_without_token(self):
        """Test MCP endpoint rejects requests without token."""
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json'
        )
        
        assert response.status_code == 401
        data = json.loads(response.content)
        assert 'error' in data

    def test_mcp_endpoint_with_invalid_token(self):
        """Test MCP endpoint rejects requests with invalid token."""
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer invalid-token'
        )
        
        assert response.status_code == 401
        data = json.loads(response.content)
        assert 'error' in data

    def test_mcp_endpoint_with_valid_token_list_tools(self):
        """Test MCP endpoint with valid token lists tools."""
        # Create a token
        token = MCPToken.objects.create(name='Test Token')
        
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token.token}'
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'tools' in data
        
        # Check that tools are exposed (should have find, list, get, create, update, delete for each model)
        tool_names = [tool['name'] for tool in data['tools']]
        assert 'list_author' in tool_names
        assert 'find_author' in tool_names
        assert 'list_article' in tool_names
        assert 'find_article' in tool_names

    def test_mcp_endpoint_with_inactive_token(self):
        """Test MCP endpoint rejects inactive tokens."""
        # Create an inactive token
        token = MCPToken.objects.create(name='Inactive Token', is_active=False)
        
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token.token}'
        )
        
        assert response.status_code == 401
        data = json.loads(response.content)
        assert 'error' in data

    def test_token_last_used_updated(self):
        """Test that token last_used_at is updated on use."""
        # Create a token
        token = MCPToken.objects.create(name='Test Token')
        assert token.last_used_at is None
        
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token.token}'
        )
        
        assert response.status_code == 200
        
        # Reload token and check last_used_at is set
        token.refresh_from_db()
        assert token.last_used_at is not None


@pytest.mark.django_db
class TestMCPToken:
    """Test suite for MCPToken model."""

    def test_token_auto_generated(self):
        """Test that token is auto-generated on save."""
        token = MCPToken.objects.create(name='Test Token')
        assert token.token is not None
        assert len(token.token) > 0

    def test_token_unique(self):
        """Test that tokens are unique."""
        token1 = MCPToken.objects.create(name='Token 1')
        token2 = MCPToken.objects.create(name='Token 2')
        assert token1.token != token2.token

    def test_token_string_representation(self):
        """Test string representation of token."""
        token = MCPToken.objects.create(name='My Token')
        str_repr = str(token)
        assert 'My Token' in str_repr
        assert token.token[:8] in str_repr

    def test_token_default_expiry(self):
        """Test that tokens have default 90-day expiry."""
        from django.utils import timezone
        from datetime import timedelta
        
        token = MCPToken.objects.create(name='Test Token')
        assert token.expires_at is not None
        
        # Check that expiry is approximately 90 days from now
        expected_expiry = timezone.now() + timedelta(days=90)
        time_diff = abs((token.expires_at - expected_expiry).total_seconds())
        assert time_diff < 60  # Allow 1 minute tolerance

    def test_token_indefinite_expiry(self):
        """Test creating token with no expiry."""
        from django.utils import timezone
        
        token = MCPToken.objects.create(name='Indefinite Token', expires_at=None)
        assert token.expires_at is None
        assert not token.is_expired()
        assert token.is_valid()

    def test_token_custom_expiry(self):
        """Test creating token with custom expiry."""
        from django.utils import timezone
        from datetime import timedelta
        
        custom_expiry = timezone.now() + timedelta(days=30)
        token = MCPToken.objects.create(name='Custom Token', expires_at=custom_expiry)
        assert token.expires_at == custom_expiry
        assert not token.is_expired()

    def test_token_expired(self):
        """Test that expired tokens are detected."""
        from django.utils import timezone
        from datetime import timedelta
        
        past_date = timezone.now() - timedelta(days=1)
        token = MCPToken.objects.create(name='Expired Token', expires_at=past_date)
        assert token.is_expired()
        assert not token.is_valid()

    def test_expired_token_rejected(self):
        """Test that expired tokens are rejected in authentication."""
        from django.utils import timezone
        from datetime import timedelta
        
        past_date = timezone.now() - timedelta(days=1)
        token = MCPToken.objects.create(name='Expired Token', expires_at=past_date)
        
        client = Client()
        response = client.post(
            '/api/mcp/',
            data=json.dumps({'method': 'tools/list'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token.token}'
        )
        
        assert response.status_code == 401
        data = json.loads(response.content)
        assert 'error' in data


@pytest.mark.django_db
class TestMCPExpose:
    """Test suite for mcp_expose opt-in behavior."""

    def test_tools_not_exposed_without_mcp_expose(self):
        """Test that tools are not exposed when mcp_expose is False."""
        from django.contrib import admin
        from django_admin_mcp import MCPAdminMixin
        from tests.models import Author
        
        # Get the registered admin
        admin_class = admin.site._registry.get(Author).__class__
        
        # Temporarily set mcp_expose to False
        original_mcp_expose = getattr(admin_class, 'mcp_expose', None)
        
        # Get the actual admin instance from registry
        admin_instance = admin.site._registry[Author]
        admin_instance.mcp_expose = False
        
        try:
            # Create a token
            token = MCPToken.objects.create(name='Test Token')
            
            client = Client()
            response = client.post(
                '/api/mcp/',
                data=json.dumps({'method': 'tools/list'}),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {token.token}'
            )
            
            assert response.status_code == 200
            data = json.loads(response.content)
            
            # Tools for Author should NOT be in the list
            tool_names = [tool['name'] for tool in data['tools']]
            assert 'list_author' not in tool_names
            assert 'find_author' not in tool_names
        finally:
            # Restore original value
            if original_mcp_expose is not None:
                admin_instance.mcp_expose = original_mcp_expose
            elif hasattr(admin_instance, 'mcp_expose'):
                delattr(admin_instance, 'mcp_expose')
