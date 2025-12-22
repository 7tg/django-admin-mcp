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
            else:
                delattr(admin_instance, 'mcp_expose')
