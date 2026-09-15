"""
Tests for issue #107: grouped (tupled) entries in the admin's fields/exclude
must be flattened before use — otherwise model_to_dict drops every field and
serialization returns empty objects.
"""

import json
import uuid
from contextlib import contextmanager

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User

from django_admin_mcp.handlers import (
    create_mock_request,
    get_model_admin,
    handle_describe,
    handle_get,
    serialize_instance,
)
from tests.models import Author


def unique_id():
    return uuid.uuid4().hex[:8]


@contextmanager
def author_admin_attrs(**attrs):
    _, model_admin = get_model_admin("author")
    originals = {name: getattr(model_admin, name, None) for name in attrs}
    for name, value in attrs.items():
        setattr(model_admin, name, value)
    try:
        yield model_admin
    finally:
        for name, value in originals.items():
            setattr(model_admin, name, value)


@sync_to_async
def make_fixture(uid):
    author = Author.objects.create(name=f"Grouped {uid}", email=f"grouped_{uid}@example.com")
    user = User.objects.create_superuser(username=f"grouped_{uid}", email=f"grouped_u_{uid}@example.com", password="pw")
    return author, user


@pytest.mark.django_db
class TestGroupedFieldsSerialization:
    """Grouped fields tuples must not empty out serialization."""

    def test_serialize_instance_with_grouped_fields(self):
        author = Author.objects.create(name="Grouped One", email=f"grp_{unique_id()}@example.com")
        with author_admin_attrs(fields=[("name", "email")]) as model_admin:
            result = serialize_instance(author, model_admin)

        assert result.get("name") == "Grouped One"
        assert result.get("email") == author.email

    def test_serialize_instance_with_grouped_exclude(self):
        author = Author.objects.create(name="Grouped Two", email=f"grp_{unique_id()}@example.com")
        with author_admin_attrs(exclude=[("email", "bio")]) as model_admin:
            result = serialize_instance(author, model_admin)

        assert result.get("name") == "Grouped Two"
        assert "email" not in result
        assert "bio" not in result


@pytest.mark.asyncio
@pytest.mark.django_db
class TestGroupedFieldsHandlers:
    """get_* and describe_* must work under grouped admin fields."""

    async def test_get_returns_fields_with_grouped_config(self):
        uid = unique_id()
        author, user = await make_fixture(uid)
        request = create_mock_request(user)

        with author_admin_attrs(fields=[("name", "email")]):
            result = await handle_get("author", {"id": author.pk}, request)
        data = json.loads(result[0].text)

        assert data.get("name") == author.name
        assert data.get("email") == author.email

    async def test_describe_lists_fields_with_grouped_config(self):
        uid = unique_id()
        author, user = await make_fixture(uid)
        request = create_mock_request(user)

        with author_admin_attrs(fields=[("name", "email")]):
            result = await handle_describe("author", {}, request)
        data = json.loads(result[0].text)

        field_names = {f["name"] for f in data["fields"]}
        assert field_names == {"name", "email"}
