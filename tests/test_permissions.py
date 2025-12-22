"""
Tests for MCP token permissions functionality
"""

import json

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import AsyncClient

from django_admin_mcp.models import MCPToken
from tests.models import Article, Author

User = get_user_model()


@pytest.mark.django_db(transaction=True)
class TestTokenPermissions:
    """Test suite for token permission checking."""

    def test_token_with_no_permissions_has_full_access(self):
        """Test that tokens without user/groups/permissions have full access (backward compatibility)."""
        token = MCPToken.objects.create(name="Test Token")
        
        # Should have all permissions when no restrictions are set
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.add_article")
        assert token.has_perm("tests.change_article")
        assert token.has_perm("tests.delete_article")

    def test_token_with_user_inherits_permissions(self):
        """Test that token with user inherits user's permissions."""
        # Create user with specific permissions
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(
            content_type=content_type, codename="view_article"
        )
        user.user_permissions.add(view_perm)
        
        # Create token associated with user
        token = MCPToken.objects.create(name="User Token", user=user)
        
        # Should have view permission from user
        assert token.has_perm("tests.view_article")
        # Should not have other permissions
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_with_direct_permissions(self):
        """Test that token can have direct permissions."""
        token = MCPToken.objects.create(name="Test Token")
        
        # Add specific permissions
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(
            content_type=content_type, codename="view_article"
        )
        add_perm = Permission.objects.get(
            content_type=content_type, codename="add_article"
        )
        token.permissions.add(view_perm, add_perm)
        
        # Should have assigned permissions
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.add_article")
        # Should not have other permissions
        assert not token.has_perm("tests.change_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_with_group_permissions(self):
        """Test that token inherits permissions from groups."""
        token = MCPToken.objects.create(name="Test Token")
        
        # Create group with permissions
        group = Group.objects.create(name="Article Editors")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(
            content_type=content_type, codename="view_article"
        )
        change_perm = Permission.objects.get(
            content_type=content_type, codename="change_article"
        )
        group.permissions.add(view_perm, change_perm)
        
        # Add group to token
        token.groups.add(group)
        
        # Should have group permissions
        assert token.has_perm("tests.view_article")
        assert token.has_perm("tests.change_article")
        # Should not have other permissions
        assert not token.has_perm("tests.add_article")
        assert not token.has_perm("tests.delete_article")

    def test_token_combines_all_permission_sources(self):
        """Test that token combines permissions from user, groups, and direct permissions."""
        # Create user with view permission
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(
            content_type=content_type, codename="view_article"
        )
        user.user_permissions.add(view_perm)
        
        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(
            content_type=content_type, codename="change_article"
        )
        group.permissions.add(change_perm)
        
        # Create token with user and add direct permission
        token = MCPToken.objects.create(name="Combined Token", user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(
            content_type=content_type, codename="add_article"
        )
        token.permissions.add(add_perm)
        
        # Should have all three permissions
        assert token.has_perm("tests.view_article")  # from user
        assert token.has_perm("tests.change_article")  # from group
        assert token.has_perm("tests.add_article")  # direct
        # Should not have delete permission
        assert not token.has_perm("tests.delete_article")

    def test_get_all_permissions(self):
        """Test get_all_permissions returns all permissions from all sources."""
        # Create user with view permission
        user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(Article)
        view_perm = Permission.objects.get(
            content_type=content_type, codename="view_article"
        )
        user.user_permissions.add(view_perm)
        
        # Create group with change permission
        group = Group.objects.create(name="Article Editors")
        change_perm = Permission.objects.get(
            content_type=content_type, codename="change_article"
        )
        group.permissions.add(change_perm)
        
        # Create token with user and add direct permission
        token = MCPToken.objects.create(name="Combined Token", user=user)
        token.groups.add(group)
        add_perm = Permission.objects.get(
            content_type=content_type, codename="add_article"
        )
        token.permissions.add(add_perm)
        
        # Get all permissions
        all_perms = token.get_all_permissions()
        
        # Should contain all three permissions
        assert "tests.view_article" in all_perms
        assert "tests.change_article" in all_perms
        assert "tests.add_article" in all_perms


@pytest.mark.django_db(transaction=True)
class TestHTTPPermissions:
    """Test suite for HTTP interface with permissions."""

    @pytest.mark.asyncio
    async def test_list_tools_filters_by_permissions(self):
        """Test that tools/list only returns tools user has permission for."""
        # Create token with only view permission
        token = await sync_to_async(MCPToken.objects.create)(name="View Only Token")
        content_type = await sync_to_async(ContentType.objects.get_for_model)(Article)
        view_perm = await sync_to_async(Permission.objects.get)(
            content_type=content_type, codename="view_article"
        )
        await sync_to_async(token.permissions.add)(view_perm)
        
        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        tool_names = [tool["name"] for tool in data["tools"]]
        
        # Should have find_models (always available)
        assert "find_models" in tool_names
        # Should have view tools (list and get)
        assert "list_article" in tool_names
        assert "get_article" in tool_names
        # Should NOT have create, update, or delete tools
        assert "create_article" not in tool_names
        assert "update_article" not in tool_names
        assert "delete_article" not in tool_names

    @pytest.mark.asyncio
    async def test_call_tool_checks_permissions(self):
        """Test that tools/call enforces permissions."""
        # Create token with only view permission
        token = await sync_to_async(MCPToken.objects.create)(name="View Only Token")
        content_type = await sync_to_async(ContentType.objects.get_for_model)(Article)
        view_perm = await sync_to_async(Permission.objects.get)(
            content_type=content_type, codename="view_article"
        )
        await sync_to_async(token.permissions.add)(view_perm)
        
        client = AsyncClient()
        
        # Should be able to call list_article (view permission)
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({
                "method": "tools/call",
                "name": "list_article",
                "arguments": {}
            }),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        assert response.status_code == 200
        
        # Should NOT be able to call create_article (no add permission)
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({
                "method": "tools/call",
                "name": "create_article",
                "arguments": {"data": {"title": "Test"}}
            }),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        assert response.status_code == 403
        data = json.loads(response.content)
        assert "Permission denied" in data["error"]

    @pytest.mark.asyncio
    async def test_token_without_restrictions_has_full_access(self):
        """Test backward compatibility: token without permissions has full access."""
        # Create token without any user/groups/permissions
        token = await sync_to_async(MCPToken.objects.create)(name="Full Access Token")
        
        client = AsyncClient()
        
        # Should have all tools in list
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        tool_names = [tool["name"] for tool in data["tools"]]
        
        # Should have all CRUD tools
        assert "list_article" in tool_names
        assert "get_article" in tool_names
        assert "create_article" in tool_names
        assert "update_article" in tool_names
        assert "delete_article" in tool_names

    @pytest.mark.asyncio
    async def test_permissions_apply_to_different_models(self):
        """Test that permissions are model-specific."""
        # Create token with only Article view permission
        token = await sync_to_async(MCPToken.objects.create)(name="Article Viewer")
        content_type = await sync_to_async(ContentType.objects.get_for_model)(Article)
        view_perm = await sync_to_async(Permission.objects.get)(
            content_type=content_type, codename="view_article"
        )
        await sync_to_async(token.permissions.add)(view_perm)
        
        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        tool_names = [tool["name"] for tool in data["tools"]]
        
        # Should have Article view tools
        assert "list_article" in tool_names
        assert "get_article" in tool_names
        # Should NOT have Author tools (no permission)
        assert "list_author" not in tool_names
        assert "get_author" not in tool_names

    @pytest.mark.asyncio
    async def test_group_based_permissions(self):
        """Test that group-based permissions work correctly."""
        # Create group with Article permissions
        @sync_to_async
        def setup_group():
            group = Group.objects.create(name="Article Managers")
            content_type = ContentType.objects.get_for_model(Article)
            view_perm = Permission.objects.get(
                content_type=content_type, codename="view_article"
            )
            add_perm = Permission.objects.get(
                content_type=content_type, codename="add_article"
            )
            change_perm = Permission.objects.get(
                content_type=content_type, codename="change_article"
            )
            group.permissions.add(view_perm, add_perm, change_perm)
            return group
        
        group = await setup_group()
        
        # Create token and add to group
        token = await sync_to_async(MCPToken.objects.create)(name="Manager Token")
        await sync_to_async(token.groups.add)(group)
        
        client = AsyncClient()
        response = await client.post(
            "/api/mcp/",
            data=json.dumps({"method": "tools/list"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        
        assert response.status_code == 200
        data = json.loads(response.content)
        tool_names = [tool["name"] for tool in data["tools"]]
        
        # Should have view, create, and update tools from group
        assert "list_article" in tool_names
        assert "get_article" in tool_names
        assert "create_article" in tool_names
        assert "update_article" in tool_names
        # Should NOT have delete tool (not in group)
        assert "delete_article" not in tool_names
