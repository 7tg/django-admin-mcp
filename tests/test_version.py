"""
Tests that the package version is consistent everywhere it is declared.
"""

import json
import tomllib
from pathlib import Path

import django
import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient

import django_admin_mcp
from tests.factories import MCPTokenFactory

skip_if_django_lt_42 = pytest.mark.skipif(
    django.VERSION < (4, 2), reason="AsyncClient headers= parameter requires Django 4.2+"
)


def test_dunder_version_matches_pyproject():
    """__version__ must match the version published in pyproject.toml."""
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text())
    assert django_admin_mcp.__version__ == pyproject["project"]["version"]


@skip_if_django_lt_42
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_initialize_reports_package_version():
    """The MCP initialize response must report the real package version."""
    token = await sync_to_async(MCPTokenFactory)()

    client = AsyncClient()
    response = await client.post(
        "/api/",
        data=json.dumps({"method": "initialize", "id": 1}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {token.plaintext_token}"},
    )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["result"]["serverInfo"]["version"] == django_admin_mcp.__version__
