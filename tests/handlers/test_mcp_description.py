"""
Tests for ModelAdmin.mcp_description.

The description is prepended to every generated tool description and returned
as ``description`` by describe_<model> and find_models.
"""

import json

import pytest
from django.utils.translation import gettext_lazy

from django_admin_mcp.handlers import create_mock_request, handle_describe, handle_find_models
from django_admin_mcp.handlers.base import get_mcp_description, resolve_registered_admin
from django_admin_mcp.tools import get_model_tools
from tests.models import Article, Author

DESCRIPTION = "A person who writes articles. Never delete an author with published articles."


@pytest.fixture
def author_description(monkeypatch):
    """Give the registered Author admin an mcp_description for one test."""
    monkeypatch.setattr(resolve_registered_admin(Author), "mcp_description", DESCRIPTION, raising=False)


class TestGetMcpDescription:
    def test_unset_is_none(self):
        assert get_mcp_description(object()) is None

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_blank_is_none(self, value):
        admin = type("Admin", (), {"mcp_description": value})()
        assert get_mcp_description(admin) is None

    def test_strips_and_resolves_lazy_strings(self):
        admin = type("Admin", (), {"mcp_description": gettext_lazy("  Orders  ")})()
        assert get_mcp_description(admin) == "Orders"


@pytest.mark.django_db
class TestToolDescriptions:
    def test_prepended_to_every_tool(self, author_description):
        tools = get_model_tools(Author)

        assert tools
        for tool in tools:
            assert tool.description.startswith(f"{DESCRIPTION}\n\n"), tool.name

    def test_other_models_unchanged(self, author_description):
        for tool in get_model_tools(Article):
            assert DESCRIPTION not in tool.description

    def test_absent_by_default(self):
        list_tool = next(t for t in get_model_tools(Author) if t.name == "list_author")
        assert list_tool.description.startswith("List ")


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHandlers:
    async def test_describe_includes_description(self, author_description):
        result = await handle_describe("author", {}, create_mock_request())
        assert json.loads(result[0].text)["description"] == DESCRIPTION

    async def test_describe_omits_unset_description(self):
        result = await handle_describe("author", {}, create_mock_request())
        assert "description" not in json.loads(result[0].text)

    async def test_find_models_includes_description(self, author_description):
        result = await handle_find_models("", {}, create_mock_request())
        models = {m["model_name"]: m for m in json.loads(result[0].text)["models"]}

        assert models["author"]["description"] == DESCRIPTION
        assert "description" not in models["article"]
