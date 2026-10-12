"""
Tests for the ``mcp_stdio`` management command.

Hosting registries and stdio-only MCP clients run the server as a local
process. The command feeds newline-delimited JSON-RPC from stdin through
the same code path as the HTTP endpoint and writes responses to stdout.
"""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from tests.factories import MCPTokenFactory

INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


def run_stdio(lines, **kwargs):
    stdin = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
    stdout = io.StringIO()
    call_command("mcp_stdio", stdin=stdin, stdout=stdout, stderr=io.StringIO(), **kwargs)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


@pytest.mark.django_db(transaction=True)
class TestMcpStdio:
    def test_round_trip(self):
        """initialize and tools/list are answered in order; a notification gets no reply."""
        token = MCPTokenFactory()

        responses = run_stdio([INITIALIZE, INITIALIZED, TOOLS_LIST], token=token.plaintext_token)

        assert [r["id"] for r in responses] == [1, 2]
        assert responses[0]["result"]["serverInfo"]["name"] == "django-admin-mcp"
        assert "tools" in responses[1]["result"]

    def test_blank_lines_are_skipped(self):
        token = MCPTokenFactory()
        stdin = io.StringIO("\n" + json.dumps(INITIALIZE) + "\n\n")
        stdout = io.StringIO()

        call_command("mcp_stdio", token=token.plaintext_token, stdin=stdin, stdout=stdout, stderr=io.StringIO())

        assert len(stdout.getvalue().splitlines()) == 1

    def test_invalid_json_gets_parse_error(self):
        token = MCPTokenFactory()
        stdout = io.StringIO()

        call_command(
            "mcp_stdio",
            token=token.plaintext_token,
            stdin=io.StringIO("{not json\n"),
            stdout=stdout,
            stderr=io.StringIO(),
        )

        assert json.loads(stdout.getvalue())["error"]["code"] == -32700

    def test_token_from_environment(self, monkeypatch):
        token = MCPTokenFactory()
        monkeypatch.setenv("DJANGO_ADMIN_MCP_TOKEN", token.plaintext_token)

        responses = run_stdio([INITIALIZE])

        assert responses[0]["id"] == 1

    def test_missing_token_fails_fast(self, monkeypatch):
        monkeypatch.delenv("DJANGO_ADMIN_MCP_TOKEN", raising=False)

        with pytest.raises(CommandError, match="--token"):
            run_stdio([INITIALIZE])

    def test_unknown_token_fails_fast(self):
        with pytest.raises(CommandError, match="not valid"):
            run_stdio([INITIALIZE], token="mcp_nosuchkey.nosuchsecret")

    def test_inactive_token_fails_fast(self):
        token = MCPTokenFactory(is_active=False)

        with pytest.raises(CommandError, match="not valid"):
            run_stdio([INITIALIZE], token=token.plaintext_token)
