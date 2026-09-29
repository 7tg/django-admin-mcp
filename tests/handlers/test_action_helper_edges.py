"""
Unit tests for the action file-download helpers' fallback branches:
header parsing, byte coercion, size caps, and confirmation-page handling.
"""

import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from django.http import HttpResponse, StreamingHttpResponse
from django.test import override_settings

from django_admin_mcp.handlers import create_mock_request
from django_admin_mcp.handlers.actions import (
    ActionFileTooLargeError,
    _charset_from_content_type,
    _confirmation_response,
    _ensure_bytes,
    _filename_from_content_disposition,
    _http_response_body,
    _response_header,
    handle_action,
    serialize_action_result,
)
from tests.models import Author

raw_handle_action = handle_action.__wrapped__.__wrapped__


class TestFilenameParsing:
    def test_filename_star_with_unknown_charset_falls_back_to_utf8(self):
        disposition = "attachment; filename*=bogus-charset''na%C3%AFve.csv"
        assert _filename_from_content_disposition(disposition) == "naïve.csv"

    def test_disposition_without_filename_returns_none(self):
        assert _filename_from_content_disposition("attachment") is None


class TestCharsetAndBytes:
    def test_empty_content_type_has_no_charset(self):
        assert _charset_from_content_type("") is None

    def test_ensure_bytes_coerces_memoryview_and_bytearray(self):
        assert _ensure_bytes(memoryview(b"abc")) == b"abc"
        assert _ensure_bytes(bytearray(b"abc")) == b"abc"


class TestResponseBodyLimits:
    @override_settings(MCP_ACTION_MAX_FILE_BYTES=10)
    def test_streaming_body_over_limit_raises(self):
        response = StreamingHttpResponse(iter([b"x" * 8, b"y" * 8]))
        with pytest.raises(ActionFileTooLargeError):
            _http_response_body(response)


class TestResponseHeaderFallback:
    def test_missing_header_returns_empty_string(self):
        assert _response_header(HttpResponse(), "Content-Disposition") == ""

    def test_object_without_headers_attribute(self):
        fake = SimpleNamespace(get=lambda name, default="": "")
        assert _response_header(fake, "Content-Disposition") == ""


class TestSerializeActionResult:
    def test_undecodable_text_body_falls_back_to_base64(self):
        body = b"\xff\xfe\xfd invalid utf-8"
        response = HttpResponse(body, content_type="text/csv; charset=utf-8")
        payload = serialize_action_result(response)
        assert payload["encoding"] == "base64"
        assert base64.b64decode(payload["content"]) == body


class TestConfirmationResponse:
    def test_unrendered_response_is_rendered_first(self):
        rendered = HttpResponse("<html>confirm?</html>", content_type="text/html")
        unrendered = SimpleNamespace(render=lambda: rendered, is_rendered=False)
        payload = _confirmation_response(unrendered, "some_action")
        assert payload["requires_confirmation"] is True
        assert "confirm?" in payload["confirmation_page"]["content"]

    @override_settings(MCP_ACTION_MAX_FILE_BYTES=10)
    def test_oversized_confirmation_page_content_is_dropped(self):
        response = HttpResponse("<html>" + "x" * 100 + "</html>", content_type="text/html")
        payload = _confirmation_response(response, "some_action")
        assert payload["confirmation_page"]["content"] == ""

    def test_long_confirmation_page_is_truncated(self):
        response = HttpResponse("<html>" + "x" * 5000 + "</html>", content_type="text/html")
        payload = _confirmation_response(response, "some_action")
        content = payload["confirmation_page"]["content"]
        assert content.endswith("...")
        assert len(content) <= 4003


@pytest.mark.asyncio
@pytest.mark.django_db
class TestDeleteSelectedWithoutAdmin:
    async def test_delete_selected_falls_back_to_queryset_delete(self):
        uid = uuid.uuid4().hex[:8]
        author = await sync_to_async(Author.objects.create)(
            name=f"Action NoAdmin {uid}", email=f"act_na_{uid}@example.com"
        )
        user = await sync_to_async(User.objects.create_superuser)(
            username=f"act_na_{uid}", email=f"act_su_{uid}@example.com", password="pw"
        )
        request = create_mock_request(user)

        result = await raw_handle_action(
            "author",
            {"action": "delete_selected", "ids": [author.pk]},
            request,
            model=Author,
            model_admin=None,
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert not await sync_to_async(Author.objects.filter(pk=author.pk).exists)()
