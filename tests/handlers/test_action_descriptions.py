"""
Tests for issue #119: actions_* must format action descriptions the way the
admin changelist does, interpolating ``model_format_dict(opts)`` placeholders.
"""

import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import handle_actions
from django_admin_mcp.handlers.base import create_mock_request, get_model_admin


@sync_to_async
def create_superuser():
    uid = uuid.uuid4().hex[:8]
    return User.objects.create_superuser(username=f"desc_admin_{uid}", email=f"desc_{uid}@example.com", password="pw")


async def list_actions(request):
    result = await handle_actions("author", {}, request)
    return {a["name"]: a["description"] for a in json.loads(result[0].text)["actions"]}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestActionDescriptionFormatting:
    async def test_delete_selected_description_is_interpolated(self):
        request = create_mock_request(await create_superuser())

        descriptions = await list_actions(request)

        assert descriptions["delete_selected"] == "Delete selected authors"

    async def test_custom_action_description_is_interpolated(self):
        request = create_mock_request(await create_superuser())
        _, author_admin = get_model_admin("author")

        def archive(modeladmin, request, queryset):
            return None

        archive.short_description = "Archive %(verbose_name_plural)s (%(verbose_name)s)"

        with patch.object(author_admin, "actions", [archive]):
            descriptions = await list_actions(request)

        assert descriptions["archive"] == "Archive authors (author)"

    async def test_description_with_literal_percent_is_returned_as_is(self):
        """A description that is not a valid format string must not break the listing."""
        request = create_mock_request(await create_superuser())
        _, author_admin = get_model_admin("author")

        def discount(modeladmin, request, queryset):
            return None

        discount.short_description = "Apply 50% discount"

        with patch.object(author_admin, "actions", [discount]):
            descriptions = await list_actions(request)

        assert descriptions["discount"] == "Apply 50% discount"
