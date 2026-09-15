"""
Tests for issue #106: related_* must return a null single-relation result for
null forward FK/O2O values and empty reverse one-to-one accessors, instead of
the removed "value" branch or an internal error.
"""

import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import create_mock_request, handle_related
from tests.models import Author, Gadget


def unique_id():
    return uuid.uuid4().hex[:8]


@sync_to_async
def make_fixture(uid, with_owner=False, with_twin=False):
    author = Author.objects.create(name=f"Rel Author {uid}", email=f"relnull_{uid}@example.com")
    gadget = Gadget.objects.create(
        title=f"Gadget {uid}",
        owner=author if with_owner else None,
        twin=author if with_twin else None,
    )
    user = User.objects.create_superuser(
        username=f"relnull_{uid}", email=f"relnull_u_{uid}@example.com", password="pw"
    )
    return author, gadget, user


@pytest.mark.asyncio
@pytest.mark.django_db
class TestNullRelations:
    """Null and missing relations must come back as type=single, result=null."""

    async def test_null_forward_fk_returns_null_single(self):
        uid = unique_id()
        author, gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_related("gadget", {"id": gadget.pk, "relation": "owner"}, request)
        data = json.loads(result[0].text)

        assert data == {"relation": "owner", "type": "single", "result": None}

    async def test_null_forward_o2o_returns_null_single(self):
        uid = unique_id()
        author, gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_related("gadget", {"id": gadget.pk, "relation": "twin"}, request)
        data = json.loads(result[0].text)

        assert data == {"relation": "twin", "type": "single", "result": None}

    async def test_empty_reverse_o2o_returns_null_single(self):
        uid = unique_id()
        author, gadget, user = await make_fixture(uid)
        request = create_mock_request(user)

        result = await handle_related("author", {"id": author.pk, "relation": "twin_gadget"}, request)
        data = json.loads(result[0].text)

        assert data == {"relation": "twin_gadget", "type": "single", "result": None}

    async def test_populated_forward_fk_still_returns_object(self):
        uid = unique_id()
        author, gadget, user = await make_fixture(uid, with_owner=True)
        request = create_mock_request(user)

        result = await handle_related("gadget", {"id": gadget.pk, "relation": "owner"}, request)
        data = json.loads(result[0].text)

        assert data["type"] == "single"
        assert data["result"]["id"] == author.pk

    async def test_populated_reverse_o2o_still_returns_object(self):
        uid = unique_id()
        author, gadget, user = await make_fixture(uid, with_twin=True)
        request = create_mock_request(user)

        result = await handle_related("author", {"id": author.pk, "relation": "twin_gadget"}, request)
        data = json.loads(result[0].text)

        assert data["type"] == "single"
        assert data["result"]["id"] == gadget.pk
