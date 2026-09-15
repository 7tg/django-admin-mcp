"""
Tests for intermediate confirmation page support in admin actions.

Covers issue #63: actions that render an HTML confirmation page get a
two-step workflow — the first call reports requires_confirmation, the
second call (confirm=true) executes.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.http import HttpResponse

from django_admin_mcp.handlers import create_mock_request, handle_action
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid):
    return User.objects.create_superuser(
        username=f"confirm_admin_{uid}",
        email=f"confirm_admin_{uid}@example.com",
        password="admin",
    )


@sync_to_async
def create_author(uid):
    return Author.objects.create(name=f"Confirm Author {uid}", email=f"confirm_{uid}@example.com")


@sync_to_async
def get_bio(author):
    author.refresh_from_db()
    return author.bio


@sync_to_async
def add_confirmation_action():
    """Register a Django-style confirmation action on the Author admin."""
    author_admin = django_admin.site._registry[Author]
    admin_class = author_admin.__class__
    original_actions = getattr(author_admin, "actions", [])

    def archive_selected(modeladmin, request, queryset):
        if "confirm" not in request.POST:
            return HttpResponse(
                "<html><body>Archive these authors?</body></html>",
                content_type="text/html",
            )
        reason = request.POST.get("reason", "archived")
        queryset.update(bio=reason)
        return None

    archive_selected.short_description = "Archive selected authors"
    admin_class.archive_selected = archive_selected
    author_admin.actions = list(original_actions or []) + ["archive_selected"]
    return author_admin, admin_class, original_actions


@sync_to_async
def restore_actions(admin_instance, admin_class, original):
    admin_instance.actions = original
    if hasattr(admin_class, "archive_selected"):
        delattr(admin_class, "archive_selected")


@pytest.mark.django_db(transaction=True)
class TestActionConfirmation:
    """Two-step confirmation workflow for admin actions (issue #63)."""

    @pytest.mark.asyncio
    async def test_unconfirmed_call_reports_requires_confirmation(self):
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(uid)
        request = create_mock_request(user)

        handles = await add_confirmation_action()
        try:
            result = await handle_action(
                "author",
                {"action": "archive_selected", "ids": [author.pk]},
                request,
            )
            data = json.loads(result[0].text)

            assert data.get("requires_confirmation") is True, data
            assert data.get("success") is False
            assert data["action"] == "archive_selected"
            assert "confirm" in data.get("message", "")
            # The intermediate page content is surfaced for context
            assert "Archive these authors?" in data.get("confirmation_page", {}).get("content", "")
            # And nothing was executed
            assert await get_bio(author) == ""
        finally:
            await restore_actions(*handles)

    @pytest.mark.asyncio
    async def test_confirmed_call_executes_action(self):
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(uid)
        request = create_mock_request(user)

        handles = await add_confirmation_action()
        try:
            result = await handle_action(
                "author",
                {"action": "archive_selected", "ids": [author.pk], "confirm": True},
                request,
            )
            data = json.loads(result[0].text)

            assert data.get("success") is True, data
            assert await get_bio(author) == "archived"
        finally:
            await restore_actions(*handles)

    @pytest.mark.asyncio
    async def test_confirmation_data_reaches_the_action(self):
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(uid)
        request = create_mock_request(user)

        handles = await add_confirmation_action()
        try:
            result = await handle_action(
                "author",
                {
                    "action": "archive_selected",
                    "ids": [author.pk],
                    "confirm": True,
                    "confirmation_data": {"reason": "archived-for-cleanup"},
                },
                request,
            )
            data = json.loads(result[0].text)

            assert data.get("success") is True, data
            assert await get_bio(author) == "archived-for-cleanup"
        finally:
            await restore_actions(*handles)

    @pytest.mark.asyncio
    async def test_action_sees_selected_ids_in_post(self):
        """The synthetic POST carries Django's standard action fields."""
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(uid)
        request = create_mock_request(user)

        seen = {}

        @sync_to_async
        def add_probe_action():
            author_admin = django_admin.site._registry[Author]
            admin_class = author_admin.__class__
            original_actions = getattr(author_admin, "actions", [])

            def probe_post(modeladmin, request, queryset):
                seen["action"] = request.POST.get("action")
                seen["selected"] = request.POST.getlist("_selected_action")
                return None

            probe_post.short_description = "Probe POST"
            admin_class.probe_post = probe_post
            author_admin.actions = list(original_actions or []) + ["probe_post"]
            return author_admin, admin_class, original_actions

        @sync_to_async
        def restore(admin_instance, admin_class, original):
            admin_instance.actions = original
            if hasattr(admin_class, "probe_post"):
                delattr(admin_class, "probe_post")

        handles = await add_probe_action()
        try:
            result = await handle_action(
                "author",
                {"action": "probe_post", "ids": [author.pk]},
                request,
            )
            data = json.loads(result[0].text)
            assert data.get("success") is True, data
            assert seen["action"] == "probe_post"
            assert seen["selected"] == [str(author.pk)]
        finally:
            await restore(*handles)
