"""
Serve django-admin-mcp over stdio.

Reads newline-delimited JSON-RPC messages from stdin, runs each one through
the same code path as ``POST <mount_point>/`` (token authentication,
permission capping, audit logging) and writes the response to stdout, so
stdio-only MCP clients and hosting registries can run the server as a local
process::

    python manage.py mcp_stdio --token mcp_<key>.<secret>

The token can also be supplied in ``DJANGO_ADMIN_MCP_TOKEN``. Diagnostics go
to stderr; stdout carries protocol messages only.
"""

import asyncio
import io
import os
import sys

from django.core.handlers.asgi import ASGIRequest
from django.core.management.base import BaseCommand, CommandError

from django_admin_mcp.models import MCPToken
from django_admin_mcp.views import mcp_endpoint

TOKEN_ENV = "DJANGO_ADMIN_MCP_TOKEN"


class Command(BaseCommand):
    help = "Serve the MCP endpoint over stdio (newline-delimited JSON-RPC) for local clients"
    stealth_options = ("stdin",)

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            help=f"Bearer token the client acts as, mcp_<key>.<secret> (default: ${TOKEN_ENV})",
        )

    def handle(self, *args, **options):
        token_value = options["token"] or os.environ.get(TOKEN_ENV)
        if not token_value:
            raise CommandError(f"Pass --token or set {TOKEN_ENV}")
        if not self._token_is_valid(token_value):
            raise CommandError("The token is not valid (unknown, inactive or expired)")

        stdin = options.get("stdin") or sys.stdin
        self.stderr.write("django-admin-mcp: serving MCP over stdio")
        asyncio.run(self._serve(stdin, token_value))

    @staticmethod
    def _token_is_valid(token_value: str) -> bool:
        parsed = MCPToken.parse_token(token_value)
        if not parsed:
            return False
        key, secret = parsed
        token = MCPToken.get_by_key(key)
        return bool(token and token.verify_secret(secret) and token.is_valid())

    async def _serve(self, stdin, token_value: str) -> None:
        headers = [
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {token_value}".encode()),
        ]
        while True:
            line = await asyncio.to_thread(stdin.readline)
            if not line:
                return  # EOF: the client closed the pipe
            message = line.strip()
            if not message:
                continue

            response = await mcp_endpoint(self._request(message.encode(), headers))
            # Notifications are answered with 202 and no body; everything else
            # (results and JSON-RPC error envelopes alike) is one line of JSON.
            if response.status_code == 202 or not response.content:
                continue
            self.stdout.write(response.content.decode())
            self.stdout.flush()

    @staticmethod
    def _request(body: bytes, headers: list[tuple[bytes, bytes]]) -> ASGIRequest:
        """Build the request the HTTP endpoint would have received for this message."""
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "root_path": "",
            "query_string": b"",
            "headers": [*headers, (b"content-length", str(len(body)).encode())],
            "client": ("stdio", 0),
            "server": ("stdio", 0),
        }
        return ASGIRequest(scope, io.BytesIO(body))
