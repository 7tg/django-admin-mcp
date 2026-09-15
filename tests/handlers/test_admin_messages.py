"""
Tests for issue #100: admin hooks calling message_user() must not crash MCP writes.

The synthetic requests used by MCP handlers (MCPRequest and the request built
in views._request_for_token) need a messages storage so ModelAdmin hooks that
call self.message_user(request, ...) don't raise MessageFailure and roll back
the surrounding transaction.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_create
from django_admin_mcp.models import MCPToken
from django_admin_mcp.views import _request_for_token
from tests.factories import MCPTokenFactory


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid):
    return User.objects.create_superuser(
        username=f"msg_admin_{uid}",
        email=f"msg_{uid}@example.com",
        password="pw",
    )


class TestSyntheticRequestMessages:
    """messages.add_message on synthetic MCP requests must not raise."""

    def test_mock_request_accepts_messages(self):
        request = create_mock_request(None)
        messages.add_message(request, messages.INFO, "hello")

    @pytest.mark.django_db
    def test_request_for_token_accepts_messages(self):
        token = MCPTokenFactory()
        request = _request_for_token(token)
        messages.add_message(request, messages.INFO, "hello")


@pytest.mark.asyncio
@pytest.mark.django_db
class TestMessageUserDoesNotBreakWrites:
    """Admin save_model hooks calling message_user must not abort MCP writes."""

    async def test_create_mcptoken_succeeds_despite_message_user(self):
        """MCPTokenAdmin.save_model calls message_user; create_mcptoken must succeed."""
        uid = unique_id()
        user = await create_superuser(uid)
        request = create_mock_request(user)

        result = await handle_create(
            "mcptoken",
            {"data": {"name": f"tok {uid}", "user": user.pk, "is_active": True}},
            request,
        )
        data = json.loads(result[0].text)

        assert data.get("success") is True, data
        assert await sync_to_async(MCPToken.objects.filter(name=f"tok {uid}").exists)()
