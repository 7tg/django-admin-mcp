"""
Edge-case tests for MCPToken model helpers, prompts, resources, and the
token admin's regenerate view.
"""

import uuid
from unittest.mock import patch

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory

from django_admin_mcp.admin import MCPTokenAdmin
from django_admin_mcp.handlers import create_mock_request
from django_admin_mcp.models import MCPToken
from django_admin_mcp.prompts import get_prompt
from django_admin_mcp.resources import ResourceError, list_resources, read_resource
from tests.factories import UserFactory


def unique_id():
    return uuid.uuid4().hex[:8]


class TestMCPTokenEdges:
    """Uncommon states of the token model."""

    def test_str_without_token_key(self):
        token = MCPToken(name="Unsaved token")
        assert str(token) == "Unsaved token"

    def test_parse_token_with_empty_secret(self):
        assert MCPToken.parse_token("mcp_somekey.") is None
        assert MCPToken.parse_token("mcp_.somesecret") is None

    def test_verify_secret_without_stored_hash(self):
        token = MCPToken(name="No hash")
        assert token.verify_secret("anything") is False

    @pytest.mark.django_db
    def test_has_perm_rejects_string_without_app_label(self):
        user = UserFactory()
        token = MCPToken(name="Perm token", user=user)
        assert token.has_perm("view_author") is False


class TestPromptBuilders:
    """Every prompt builder renders its template."""

    def test_crud_guide(self):
        prompt = get_prompt("crud_guide", {"model_name": "author"})
        text = prompt["messages"][0]["content"]["text"]
        assert "create_author" in text
        assert "delete_author" in text

    def test_bulk_operations_guide(self):
        prompt = get_prompt("bulk_operations_guide", {})
        text = prompt["messages"][0]["content"]["text"]
        assert "bulk_" in text


@pytest.mark.asyncio
@pytest.mark.django_db
class TestResourceEdges:
    """Resource listing/reading error and filtering branches."""

    async def test_read_resource_without_scheme_is_an_error(self):
        request = create_mock_request()
        with pytest.raises(ResourceError):
            await read_resource("no-scheme-at-all", request)

    async def test_read_resource_error_payload_is_surfaced(self):
        from asgiref.sync import sync_to_async  # noqa: PLC0415

        user = await sync_to_async(User.objects.create_superuser)(
            username=f"res_super_{unique_id()}", email="rs@example.com", password="pw"
        )
        request = create_mock_request(user)
        with pytest.raises(ResourceError):
            await read_resource("data://author/999999999", request)

    async def test_list_resources_skips_models_without_view_permission(self):
        from asgiref.sync import sync_to_async  # noqa: PLC0415

        @sync_to_async
        def make_add_only_user():
            user = User.objects.create_user(username=f"res_addonly_{unique_id()}", password="pw")
            user.user_permissions.add(*Permission.objects.filter(codename="add_author"))
            return user

        user = await make_add_only_user()
        request = create_mock_request(user)
        resources = await list_resources(request)
        assert "models://author/schema" not in [r["uri"] for r in resources]


@pytest.mark.django_db
class TestRegenerateTokenNotFound:
    def test_post_with_unknown_token_id_redirects_with_error(self):
        staff = UserFactory(is_staff=True, is_superuser=True)
        request = RequestFactory().post("/admin/django_admin_mcp/mcptoken/999999/regenerate/")
        request.user = staff

        admin_instance = MCPTokenAdmin(MCPToken, django_admin.site)
        with patch.object(MCPTokenAdmin, "message_user") as message_user:
            response = admin_instance.regenerate_token_view(request, 999999)

        assert response.status_code == 302
        assert message_user.called
        assert "Token not found." in message_user.call_args.args
