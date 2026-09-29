"""
Tests for choice/enum field serialization and schema exposure (issue #113).

Covers:
- serialize_instance adds a ``<field>_display`` sidecar with the human-readable
  label for every field defined with choices, keeping the raw value untouched
- field visibility rules apply to the sidecar too
- a real model field named ``<field>_display`` always wins (collision guard)
- describe exposes all choices, including grouped (optgroup) choices
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.auth.models import User

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import (
    create_mock_request,
    handle_create,
    handle_describe,
    handle_get,
    handle_list,
    handle_update,
    serialize_instance,
)
from django_admin_mcp.handlers.meta import _get_field_metadata
from tests.models import Ticket, TicketPriority, TicketStatus


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


def make_ticket(**overrides):
    """Create a Ticket with sensible defaults."""
    defaults = {
        "title": f"Ticket {unique_id()}",
        "status": TicketStatus.ACTIVE,
        "priority": TicketPriority.HIGH,
    }
    defaults.update(overrides)
    return Ticket.objects.create(**defaults)


@pytest.mark.django_db
class TestSerializeChoiceDisplay:
    """serialize_instance emits *_display sidecars for choice fields."""

    def test_integer_choices_sidecar(self):
        ticket = make_ticket(status=TicketStatus.ACTIVE)
        result = serialize_instance(ticket)
        assert result["status"] == 2
        assert result["status_display"] == "Active"

    def test_text_choices_sidecar(self):
        ticket = make_ticket(priority=TicketPriority.HIGH)
        result = serialize_instance(ticket)
        assert result["priority"] == "high"
        assert result["priority_display"] == "High priority"

    def test_plain_list_choices_sidecar(self):
        ticket = make_ticket(size="s")
        result = serialize_instance(ticket)
        assert result["size"] == "s"
        assert result["size_display"] == "Small"

    def test_grouped_choices_sidecar(self):
        ticket = make_ticket(media="vinyl")
        result = serialize_instance(ticket)
        assert result["media"] == "vinyl"
        assert result["media_display"] == "Vinyl"

    def test_none_value_yields_none_sidecar(self):
        ticket = make_ticket(severity=None)
        result = serialize_instance(ticket)
        assert result["severity"] is None
        assert result["severity_display"] is None

    def test_value_not_in_choices_falls_back_to_raw_value(self):
        ticket = make_ticket(severity=99)
        result = serialize_instance(ticket)
        assert result["severity"] == 99
        assert result["severity_display"] == 99

    def test_non_choice_fields_get_no_sidecar(self):
        ticket = make_ticket()
        result = serialize_instance(ticket)
        assert "title" in result
        assert "title_display" not in result

    def test_collision_with_real_field_is_not_overwritten(self):
        ticket = make_ticket(state=1, state_display="hand-written")
        result = serialize_instance(ticket)
        assert result["state"] == 1
        assert result["state_display"] == "hand-written"

    def test_excluded_choice_field_has_no_sidecar(self):
        class TestTicketAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_exclude_fields = ["status"]

        model_admin = TestTicketAdmin(Ticket, admin.site)
        ticket = make_ticket()
        result = serialize_instance(ticket, model_admin)
        assert "status" not in result
        assert "status_display" not in result

    def test_include_list_limits_sidecars(self):
        class TestTicketAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_fields = ["title", "status"]

        model_admin = TestTicketAdmin(Ticket, admin.site)
        ticket = make_ticket()
        result = serialize_instance(ticket, model_admin)
        assert result["status_display"] == "Active"
        assert "priority" not in result
        assert "priority_display" not in result


class TestDescribeChoicesMetadata:
    """_get_field_metadata exposes all choices, flat and grouped."""

    def test_integer_choices_listed(self):
        meta = _get_field_metadata(Ticket._meta.get_field("status"))
        assert meta["choices"] == [
            {"value": 1, "label": "Draft"},
            {"value": 2, "label": "Active"},
            {"value": 3, "label": "Closed"},
        ]

    def test_grouped_choices_are_flattened(self):
        meta = _get_field_metadata(Ticket._meta.get_field("media"))
        assert meta["choices"] == [
            {"value": "cd", "label": "CD"},
            {"value": "vinyl", "label": "Vinyl"},
            {"value": "unknown", "label": "Unknown"},
        ]


@pytest.mark.asyncio
@pytest.mark.django_db
class TestChoiceDisplayEndToEnd:
    """Choice labels flow through the MCP tool responses."""

    async def _create_superuser_request(self, uid):
        def _create():
            user = User.objects.create_superuser(
                username=f"admin_{uid}",
                email=f"admin_{uid}@example.com",
                password="password",
            )
            return create_mock_request(user)

        return await sync_to_async(_create)()

    async def test_get_includes_display(self):
        uid = unique_id()
        ticket = await sync_to_async(make_ticket)()
        request = await self._create_superuser_request(uid)

        result = await handle_get("ticket", {"id": ticket.pk}, request)

        data = json.loads(result[0].text)
        assert data["status"] == 2
        assert data["status_display"] == "Active"
        assert data["priority_display"] == "High priority"

    async def test_list_includes_display(self):
        uid = unique_id()
        ticket = await sync_to_async(make_ticket)()
        request = await self._create_superuser_request(uid)

        result = await handle_list("ticket", {"filters": {"id": ticket.pk}}, request)

        data = json.loads(result[0].text)
        assert data["results"][0]["status_display"] == "Active"

    async def test_create_response_includes_display(self):
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_create(
            "ticket",
            {"data": {"title": f"Created {uid}", "status": 3, "priority": "low"}},
            request,
        )

        data = json.loads(result[0].text)
        assert data["object"]["status_display"] == "Closed"
        assert data["object"]["priority_display"] == "Low priority"

    async def test_update_response_includes_display(self):
        uid = unique_id()
        ticket = await sync_to_async(make_ticket)()
        request = await self._create_superuser_request(uid)

        result = await handle_update(
            "ticket",
            {"id": ticket.pk, "data": {"status": 1}},
            request,
        )

        data = json.loads(result[0].text)
        assert data["object"]["status_display"] == "Draft"

    async def test_describe_includes_all_choices(self):
        uid = unique_id()
        request = await self._create_superuser_request(uid)

        result = await handle_describe("ticket", {}, request)

        data = json.loads(result[0].text)
        by_name = {f["name"]: f for f in data["fields"]}
        assert {c["value"] for c in by_name["status"]["choices"]} == {1, 2, 3}
        assert {c["value"] for c in by_name["priority"]["choices"]} == {"low", "high"}
        assert {c["value"] for c in by_name["media"]["choices"]} == {"cd", "vinyl", "unknown"}
