"""
Tests for MCP Prompts (#65) and Resources (#66) support on the JSON-RPC endpoint.
"""

import json

import django
import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import Permission, User
from django.test import AsyncClient

from tests.factories import MCPTokenFactory

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)


@sync_to_async
def make_superuser_token():
    """Full-access token: permissions are enforced on the token, not the linked user."""
    superuser = User.objects.create_superuser(
        username=f"proto_super_{User.objects.count()}",
        email="proto_super@example.com",
        password="test",
    )
    token = MCPTokenFactory(user=superuser)
    token.permissions.set(Permission.objects.all())
    return token


async def rpc(token, method, params=None, request_id=1):
    client = AsyncClient()
    payload = {"method": method, "id": request_id}
    if params is not None:
        payload["params"] = params
    response = await client.post(
        "/api/",
        data=json.dumps(payload),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )
    return response.status_code, json.loads(response.content)


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestCapabilities:
    @pytest.mark.asyncio
    async def test_initialize_declares_prompts_and_resources(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "initialize")
        assert status == 200
        capabilities = data["result"]["capabilities"]
        assert "prompts" in capabilities
        assert "resources" in capabilities
        assert "tools" in capabilities


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestPrompts:
    @pytest.mark.asyncio
    async def test_prompts_list_returns_prompts(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "prompts/list")
        assert status == 200
        prompts = data["result"]["prompts"]
        assert len(prompts) >= 3
        names = [p["name"] for p in prompts]
        assert "explore_models" in names
        assert "understand_model" in names
        for prompt in prompts:
            assert prompt["name"]
            assert prompt["description"]
            assert isinstance(prompt.get("arguments", []), list)

    @pytest.mark.asyncio
    async def test_prompts_get_returns_messages(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "prompts/get", {"name": "explore_models"})
        assert status == 200
        result = data["result"]
        assert result["messages"]
        message = result["messages"][0]
        assert message["role"] == "user"
        assert message["content"]["type"] == "text"
        assert "find_models" in message["content"]["text"]

    @pytest.mark.asyncio
    async def test_prompts_get_substitutes_arguments(self):
        token = await make_superuser_token()
        status, data = await rpc(
            token, "prompts/get", {"name": "understand_model", "arguments": {"model_name": "author"}}
        )
        assert status == 200
        text = data["result"]["messages"][0]["content"]["text"]
        assert "author" in text
        assert "describe_author" in text

    @pytest.mark.asyncio
    async def test_prompts_get_unknown_prompt_is_an_error(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "prompts/get", {"name": "no_such_prompt"})
        assert "error" in data
        assert "no_such_prompt" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_prompts_get_missing_required_argument_is_an_error(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "prompts/get", {"name": "understand_model"})
        assert "error" in data


@skip_if_django_lt_42
@pytest.mark.django_db(transaction=True)
class TestResources:
    @pytest.mark.asyncio
    async def test_resources_list_includes_model_schemas(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "resources/list")
        assert status == 200
        resources = data["result"]["resources"]
        uris = [r["uri"] for r in resources]
        assert "models://author/schema" in uris
        assert "models://article/schema" in uris
        for resource in resources:
            assert resource["name"]
            assert resource["mimeType"] == "application/json"

    @pytest.mark.asyncio
    async def test_resources_list_filters_by_permission(self):
        """A token whose user has no permissions sees no model resources."""
        token = await sync_to_async(MCPTokenFactory)()
        status, data = await rpc(token, "resources/list")
        assert status == 200
        uris = [r["uri"] for r in data["result"]["resources"]]
        assert "models://author/schema" not in uris

    @pytest.mark.asyncio
    async def test_resources_templates_list(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "resources/templates/list")
        assert status == 200
        templates = data["result"]["resourceTemplates"]
        uri_templates = [t["uriTemplate"] for t in templates]
        assert "data://{model_name}/{id}" in uri_templates

    @pytest.mark.asyncio
    async def test_resources_read_model_schema(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "resources/read", {"uri": "models://author/schema"})
        assert status == 200
        contents = data["result"]["contents"]
        assert contents[0]["uri"] == "models://author/schema"
        assert contents[0]["mimeType"] == "application/json"
        schema = json.loads(contents[0]["text"])
        assert schema["model_name"] == "author"
        assert "fields" in schema

    @pytest.mark.asyncio
    async def test_resources_read_instance_data(self):
        from tests.models import Author  # noqa: PLC0415

        token = await make_superuser_token()
        author = await sync_to_async(Author.objects.create)(name="Resource Author", email="resource_author@example.com")
        status, data = await rpc(token, "resources/read", {"uri": f"data://author/{author.pk}"})
        assert status == 200
        payload = json.loads(data["result"]["contents"][0]["text"])
        assert payload["name"] == "Resource Author"

    @pytest.mark.asyncio
    async def test_resources_read_instance_list(self):
        from tests.models import Author  # noqa: PLC0415

        token = await make_superuser_token()
        await sync_to_async(Author.objects.create)(name="Resource List Author", email="resource_list@example.com")
        status, data = await rpc(token, "resources/read", {"uri": "data://author/"})
        assert status == 200
        payload = json.loads(data["result"]["contents"][0]["text"])
        assert "results" in payload

    @pytest.mark.asyncio
    async def test_resources_read_unknown_uri_is_an_error(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "resources/read", {"uri": "bogus://nothing"})
        assert "error" in data

    @pytest.mark.asyncio
    async def test_resources_read_requires_uri(self):
        token = await make_superuser_token()
        status, data = await rpc(token, "resources/read", {})
        assert "error" in data
