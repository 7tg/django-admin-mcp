"""
Tests for serializing admin action HttpResponse downloads via MCP.
"""

import base64
import json
import uuid

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.http import HttpResponse, StreamingHttpResponse

from django_admin_mcp.handlers import handle_action
from django_admin_mcp.handlers.actions import (
    ActionFileTooLargeError,
    _filename_from_content_disposition,
    _is_text_content_type,
    serialize_action_result,
)
from django_admin_mcp.handlers.base import create_mock_request
from tests.models import Author


def unique_id() -> str:
    return uuid.uuid4().hex[:8]


@sync_to_async
def create_superuser(uid: str) -> User:
    return User.objects.create_superuser(
        username=f"dl_admin_{uid}",
        email=f"dl_admin_{uid}@example.com",
        password="admin",
    )


@sync_to_async
def create_author(name: str, email: str) -> Author:
    return Author.objects.create(name=name, email=email)


class TestSerializeActionResultHelpers:
    """Unit tests for download serialization helpers."""

    def test_filename_from_content_disposition(self):
        assert _filename_from_content_disposition('attachment; filename="export.csv"') == "export.csv"
        assert _filename_from_content_disposition("attachment;filename=export.tsv") == "export.tsv"
        assert _filename_from_content_disposition("attachment; filename*=UTF-8''report.pdf") == "report.pdf"
        assert _filename_from_content_disposition("") is None

    def test_is_text_content_type(self):
        assert _is_text_content_type("text/csv") is True
        assert _is_text_content_type("text/tsv; charset=utf-8") is True
        assert _is_text_content_type("application/json") is True
        assert _is_text_content_type("application/pdf") is False

    def test_serialize_none(self):
        assert serialize_action_result(None) is None

    def test_serialize_plain_string(self):
        assert serialize_action_result("done") == "done"

    def test_serialize_http_response_text_file(self):
        response = HttpResponse("a,b\r\n1,2\r\n", content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="export.csv"'
        payload = serialize_action_result(response)
        assert payload["type"] == "file"
        assert payload["encoding"] == "utf-8"
        assert payload["filename"] == "export.csv"
        assert payload["content_type"].startswith("text/csv")
        assert "1,2" in payload["content"]
        assert payload["size"] == len(b"a,b\r\n1,2\r\n")

    def test_serialize_http_response_binary_file(self):
        raw = b"%PDF-1.4 fake"
        response = HttpResponse(raw, content_type="application/pdf")
        response["Content-Disposition"] = "attachment;filename=report.pdf"
        payload = serialize_action_result(response)
        assert payload["type"] == "file"
        assert payload["encoding"] == "base64"
        assert payload["filename"] == "report.pdf"
        assert base64.b64decode(payload["content"]) == raw

    def test_serialize_streaming_http_response(self):
        chunks = [b"hello", b" ", b"world"]
        response = StreamingHttpResponse(chunks, content_type="text/plain")
        response["Content-Disposition"] = 'attachment; filename="note.txt"'
        payload = serialize_action_result(response)
        assert payload["type"] == "file"
        assert payload["encoding"] == "utf-8"
        assert payload["content"] == "hello world"

    def test_serialize_rejects_oversized_body(self, settings):
        settings.MCP_ACTION_MAX_FILE_BYTES = 8
        response = HttpResponse(b"0123456789", content_type="application/octet-stream")
        response["Content-Disposition"] = "attachment;filename=big.bin"
        with pytest.raises(ActionFileTooLargeError) as exc_info:
            serialize_action_result(response)
        assert "MCP_ACTION_MAX_FILE_BYTES" in str(exc_info.value)


@pytest.mark.django_db(transaction=True)
class TestHandleActionFileDownloads:
    """Integration: action_* returns file payloads for download HttpResponses."""

    @pytest.mark.asyncio
    async def test_action_returns_csv_file_payload(self):
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(f"DL Author {uid}", f"dl_{uid}@example.com")
        request = create_mock_request(user)

        @sync_to_async
        def add_export_action():
            author_admin = django_admin.site._registry[Author]
            admin_class = author_admin.__class__
            original_actions = getattr(author_admin, "actions", [])

            def export_csv(modeladmin, request, queryset):
                response = HttpResponse("a,b\r\n1,2\r\n", content_type="text/csv")
                response["Content-Disposition"] = 'attachment; filename="export.csv"'
                return response

            export_csv.short_description = "Export CSV"
            admin_class.export_csv = export_csv
            author_admin.actions = list(original_actions or []) + ["export_csv"]
            return author_admin, admin_class, original_actions

        @sync_to_async
        def restore(admin_instance, admin_class, original):
            admin_instance.actions = original
            if hasattr(admin_class, "export_csv"):
                delattr(admin_class, "export_csv")

        admin_instance, admin_class, original = await add_export_action()
        try:
            result = await handle_action(
                "author",
                {"action": "export_csv", "ids": [author.pk]},
                request,
            )
            parsed = json.loads(result[0].text)
            assert parsed["success"] is True
            payload = parsed["result"]
            assert payload["type"] == "file"
            assert payload["encoding"] == "utf-8"
            assert payload["filename"] == "export.csv"
            assert "1,2" in payload["content"]
            assert "<HttpResponse" not in json.dumps(parsed)
        finally:
            await restore(admin_instance, admin_class, original)

    @pytest.mark.asyncio
    async def test_action_returns_none_result(self):
        uid = unique_id()
        user = await create_superuser(uid)
        author = await create_author(f"None Author {uid}", f"none_{uid}@example.com")
        request = create_mock_request(user)

        @sync_to_async
        def add_noop_action():
            author_admin = django_admin.site._registry[Author]
            admin_class = author_admin.__class__
            original_actions = getattr(author_admin, "actions", [])

            def noop_action(modeladmin, request, queryset):
                return None

            noop_action.short_description = "Noop"
            admin_class.noop_action = noop_action
            author_admin.actions = list(original_actions or []) + ["noop_action"]
            return author_admin, admin_class, original_actions

        @sync_to_async
        def restore(admin_instance, admin_class, original):
            admin_instance.actions = original
            if hasattr(admin_class, "noop_action"):
                delattr(admin_class, "noop_action")

        admin_instance, admin_class, original = await add_noop_action()
        try:
            result = await handle_action(
                "author",
                {"action": "noop_action", "ids": [author.pk]},
                request,
            )
            parsed = json.loads(result[0].text)
            assert parsed["success"] is True
            assert parsed["result"] is None
        finally:
            await restore(admin_instance, admin_class, original)
