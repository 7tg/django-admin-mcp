"""
Tests for issue #120: FileField / ImageField values can be set over MCP.

A file value is ``{"filename", "content_base64", "content_type"?}`` in ``data``.
It is decoded into an uploaded file and bound to the admin form through
``files=``, so the form field's own validation applies, on create, update,
bulk and inline rows alike.
"""

import base64
import json
import uuid
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from django_admin_mcp.handlers import (
    create_mock_request,
    handle_bulk,
    handle_create,
    handle_describe,
    handle_get,
    handle_update,
)
from django_admin_mcp.handlers.base import _serialize_data_for_log
from django_admin_mcp.handlers.uploads import UploadError, decode_upload, max_upload_file_bytes
from django_admin_mcp.tools.registry import get_model_tools
from tests.models import Article, Author, Document, DocumentPage

PDF = b"%PDF-1.4 fake pdf body"


def unique_id():
    return uuid.uuid4().hex[:8]


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def upload(filename="manual.pdf", content=PDF, **extra):
    return {"filename": filename, "content_base64": b64(content), **extra}


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """Every stored file lands in a pytest tmp dir, never in the repo."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@sync_to_async
def superuser_request():
    uid = unique_id()
    user = User.objects.create_superuser(username=f"up_admin_{uid}", email=f"up_{uid}@example.com", password="x")
    return create_mock_request(user)


@sync_to_async
def make_document(appendix=False, pages=0):
    document = Document(title=f"Doc {unique_id()}")
    document.file.save("stored.pdf", ContentFile(b"stored"), save=False)
    if appendix:
        document.appendix.save("appendix.txt", ContentFile(b"appendix"), save=False)
    document.save()
    rows = []
    for i in range(pages):
        page = DocumentPage(document=document, label=f"P{i}")
        page.scan.save(f"scan{i}.txt", ContentFile(b"scan"), save=False)
        page.save()
        rows.append(page)
    return document, rows


@sync_to_async
def reload(obj):
    return type(obj).objects.get(pk=obj.pk)


@sync_to_async
def read(field_file):
    with field_file.open("rb") as handle:
        return handle.read()


@sync_to_async
def log_messages(obj):
    return list(LogEntry.objects.filter(object_id=str(obj.pk)).values_list("change_message", flat=True))


async def call(handler, model_name, arguments, request):
    result = await handler(model_name, arguments, request)
    return json.loads(result[0].text)


def field_errors(data, field):
    """Messages reported for ``field`` in a validation_error payload."""
    assert data.get("code") == "validation_error", data
    errors = data["validation_errors"]
    assert field in errors["fields_with_errors"], data
    return next(entry["messages"] for entry in errors["errors"] if entry["field"] == field)


class TestDecodeUpload:
    def test_decodes_content_name_and_type(self):
        uploaded = decode_upload({"filename": "a.pdf", "content_base64": b64(PDF), "content_type": "application/x-pdf"})

        assert uploaded.name == "a.pdf"
        assert uploaded.read() == PDF
        assert uploaded.size == len(PDF)
        assert uploaded.content_type == "application/x-pdf"

    def test_content_type_is_guessed_from_filename(self):
        assert decode_upload(upload("a.pdf")).content_type == "application/pdf"
        assert decode_upload(upload("a.txt")).content_type == "text/plain"
        assert decode_upload(upload("a.unknownext")).content_type == "application/octet-stream"

    @pytest.mark.parametrize(
        "filename",
        ["../../etc/passwd.txt", "..\\..\\windows\\passwd.txt", "/abs/passwd.txt", "C:\\tmp\\passwd.txt"],
    )
    def test_filename_is_reduced_to_basename(self, filename):
        assert decode_upload(upload(filename)).name == "passwd.txt"

    def test_base64_with_line_breaks_is_accepted(self):
        encoded = base64.encodebytes(PDF * 10).decode("ascii")
        assert "\n" in encoded
        assert decode_upload({"filename": "a.pdf", "content_base64": encoded}).read() == PDF * 10

    @pytest.mark.parametrize(
        ("value", "fragment"),
        [
            ("documents/x.pdf", "storage path"),
            (5, "object"),
            (["a"], "object"),
            (True, "object"),
            ({"content_base64": b64(PDF)}, "filename"),
            ({"filename": "", "content_base64": b64(PDF)}, "filename"),
            ({"filename": "   ", "content_base64": b64(PDF)}, "filename"),
            ({"filename": "dir/", "content_base64": b64(PDF)}, "filename"),
            ({"filename": "..", "content_base64": b64(PDF)}, "filename"),
            ({"filename": 7, "content_base64": b64(PDF)}, "filename"),
            ({"filename": "a.pdf"}, "content_base64"),
            ({"filename": "a.pdf", "content_base64": 12}, "content_base64"),
            ({"filename": "a.pdf", "content_base64": "not base64!!"}, "base64"),
            ({"filename": "a.pdf", "content_base64": "abc"}, "base64"),
            ({"filename": "a.pdf", "content_base64": b64(PDF), "content_type": 3}, "content_type"),
            ({"filename": "a.pdf", "content_base64": b64(PDF), "path": "x"}, "path"),
        ],
    )
    def test_malformed_value_raises(self, value, fragment):
        with pytest.raises(UploadError) as excinfo:
            decode_upload(value)
        assert fragment in str(excinfo.value)

    def test_default_cap_is_five_mebibytes(self):
        assert max_upload_file_bytes() == 5 * 1024 * 1024

    def test_cap_is_checked_before_decoding(self, settings):
        settings.MCP_UPLOAD_MAX_FILE_BYTES = 10
        with patch("django_admin_mcp.handlers.uploads.base64.b64decode") as b64decode:
            with pytest.raises(UploadError) as excinfo:
                decode_upload(upload(content=b"x" * 11))
        b64decode.assert_not_called()
        assert "MCP_UPLOAD_MAX_FILE_BYTES" in str(excinfo.value)

    def test_content_at_the_cap_is_accepted(self, settings):
        settings.MCP_UPLOAD_MAX_FILE_BYTES = 10
        for size in (8, 9, 10):
            assert decode_upload(upload(content=b"x" * size)).size == size


@pytest.mark.asyncio
@pytest.mark.django_db
class TestCreateWithFile:
    async def test_required_file_field_can_be_created(self, media_root):
        request = await superuser_request()

        data = await call(handle_create, "document", {"data": {"title": "Manual", "file": upload()}}, request)

        assert data.get("success") is True, data
        document = await sync_to_async(Document.objects.get)(pk=data["id"])
        assert document.file.name.startswith("documents/manual")
        assert await read(document.file) == PDF
        assert (media_root / document.file.name).is_file()
        # Responses keep serializing a file field as its stored name
        assert data["object"]["file"] == document.file.name
        assert data["object"]["appendix"] == ""

    async def test_missing_required_file_is_a_validation_error(self):
        request = await superuser_request()

        data = await call(handle_create, "document", {"data": {"title": "Manual"}}, request)

        assert field_errors(data, "file") == ["This field is required."]

    async def test_null_on_required_file_is_a_validation_error(self):
        request = await superuser_request()

        data = await call(handle_create, "document", {"data": {"title": "Manual", "file": None}}, request)

        assert field_errors(data, "file") == ["This field is required."]

    async def test_optional_file_field(self):
        request = await superuser_request()
        uid = unique_id()

        data = await call(
            handle_create,
            "author",
            {"data": {"name": "A", "email": f"a_{uid}@example.com", "attachment": upload("cv.txt", b"cv")}},
            request,
        )

        assert data.get("success") is True, data
        author = await sync_to_async(Author.objects.get)(pk=data["id"])
        assert author.attachment.name.startswith("attachments/cv")
        assert await read(author.attachment) == b"cv"

    async def test_null_on_optional_file_creates_without_file(self):
        request = await superuser_request()

        data = await call(
            handle_create, "document", {"data": {"title": "Manual", "file": upload(), "appendix": None}}, request
        )

        assert data.get("success") is True, data
        assert data["object"]["appendix"] == ""

    async def test_filename_is_sanitised_to_basename(self, media_root):
        request = await superuser_request()

        data = await call(
            handle_create, "document", {"data": {"title": "Manual", "file": upload("../../escape.pdf")}}, request
        )

        assert data.get("success") is True, data
        assert data["object"]["file"].startswith("documents/escape")
        assert not (media_root.parent / "escape.pdf").exists()

    async def test_extension_validator_applies(self):
        request = await superuser_request()

        title = f"Manual {unique_id()}"

        data = await call(handle_create, "document", {"data": {"title": title, "file": upload("run.exe")}}, request)

        assert "exe" in field_errors(data, "file")[0]
        assert not await sync_to_async(Document.objects.filter(title=title).exists)()

    async def test_max_length_applies(self):
        request = await superuser_request()

        data = await call(
            handle_create, "document", {"data": {"title": "Manual", "file": upload("a" * 200 + ".pdf")}}, request
        )

        assert "100 characters" in field_errors(data, "file")[0]

    async def test_empty_file_is_rejected_by_the_form_field(self):
        request = await superuser_request()

        data = await call(
            handle_create, "document", {"data": {"title": "Manual", "file": upload(content=b"")}}, request
        )

        assert field_errors(data, "file") == ["The submitted file is empty."]

    @pytest.mark.parametrize(
        ("value", "fragment"),
        [
            ("documents/x.pdf", "storage path"),
            (42, "object"),
            (["x"], "object"),
            ({"filename": "a.pdf", "content_base64": "@@@"}, "base64"),
            ({"content_base64": "aGk="}, "filename"),
            ({"filename": "", "content_base64": "aGk="}, "filename"),
            ({"filename": "a.pdf", "content_base64": "aGk=", "url": "http://x"}, "url"),
        ],
    )
    async def test_malformed_file_value_is_a_field_validation_error(self, value, fragment):
        request = await superuser_request()

        data = await call(handle_create, "document", {"data": {"title": "Manual", "file": value}}, request)

        assert "success" not in data, data
        assert data["error"] == "Validation failed"
        messages = field_errors(data, "file")
        assert len(messages) == 1
        assert fragment in messages[0]
        assert "invalid_fields" not in data

    async def test_other_field_errors_are_reported_alongside(self):
        request = await superuser_request()

        data = await call(handle_create, "document", {"data": {"file": "x.pdf"}}, request)

        assert data["validation_errors"]["fields_with_errors"] == ["title", "file"]

    async def test_oversized_file_is_rejected(self, settings):
        settings.MCP_UPLOAD_MAX_FILE_BYTES = 16
        request = await superuser_request()

        data = await call(
            handle_create, "document", {"data": {"title": "Manual", "file": upload(content=b"x" * 17)}}, request
        )

        message = field_errors(data, "file")[0]
        assert "MCP_UPLOAD_MAX_FILE_BYTES" in message
        assert "16" in message


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUpdateWithFile:
    async def test_file_is_replaced(self):
        request = await superuser_request()
        document, _ = await make_document()

        data = await call(
            handle_update, "document", {"id": document.pk, "data": {"file": upload("new.txt", b"new")}}, request
        )

        assert data.get("success") is True, data
        document = await reload(document)
        assert document.file.name.startswith("documents/new")
        assert await read(document.file) == b"new"

    async def test_unsent_file_fields_keep_their_files(self):
        request = await superuser_request()
        document, _ = await make_document(appendix=True)
        before = (document.file.name, document.appendix.name)

        data = await call(handle_update, "document", {"id": document.pk, "data": {"title": "Renamed"}}, request)

        assert data.get("success") is True, data
        document = await reload(document)
        assert (document.file.name, document.appendix.name) == before

    async def test_replacing_one_file_keeps_the_other(self):
        request = await superuser_request()
        document, _ = await make_document(appendix=True)
        before = document.file.name

        data = await call(
            handle_update, "document", {"id": document.pk, "data": {"appendix": upload("b.txt", b"b")}}, request
        )

        assert data.get("success") is True, data
        document = await reload(document)
        assert document.file.name == before
        assert await read(document.appendix) == b"b"

    async def test_null_clears_optional_file(self):
        request = await superuser_request()
        document, _ = await make_document(appendix=True)

        data = await call(handle_update, "document", {"id": document.pk, "data": {"appendix": None}}, request)

        assert data.get("success") is True, data
        assert data["object"]["appendix"] == ""
        document = await reload(document)
        assert not document.appendix
        assert document.file

    async def test_clear_key_still_clears_optional_file(self):
        request = await superuser_request()
        document, _ = await make_document(appendix=True)

        data = await call(handle_update, "document", {"id": document.pk, "data": {"appendix-clear": True}}, request)

        assert data.get("success") is True, data
        assert not (await reload(document)).appendix

    async def test_null_on_required_file_is_rejected_and_file_kept(self):
        request = await superuser_request()
        document, _ = await make_document()
        before = document.file.name

        data = await call(handle_update, "document", {"id": document.pk, "data": {"file": None}}, request)

        assert field_errors(data, "file") == ["This field is required."]
        assert (await reload(document)).file.name == before

    async def test_upload_together_with_clear_is_a_contradiction(self):
        request = await superuser_request()
        document, _ = await make_document(appendix=True)
        before = document.appendix.name

        data = await call(
            handle_update,
            "document",
            {"id": document.pk, "data": {"appendix": upload("b.txt", b"b"), "appendix-clear": True}},
            request,
        )

        assert "not both" in field_errors(data, "appendix")[0]
        assert (await reload(document)).appendix.name == before

    async def test_invalid_upload_changes_nothing(self):
        request = await superuser_request()
        document, _ = await make_document()
        before = (document.title, document.file.name)

        data = await call(
            handle_update,
            "document",
            {"id": document.pk, "data": {"title": "Changed", "file": {"filename": "a.pdf", "content_base64": "@"}}},
            request,
        )

        assert "base64" in field_errors(data, "file")[0]
        document = await reload(document)
        assert (document.title, document.file.name) == before

    async def test_string_value_is_an_explicit_error(self):
        request = await superuser_request()
        document, _ = await make_document()
        before = document.file.name

        data = await call(handle_update, "document", {"id": document.pk, "data": {"file": "documents/x.pdf"}}, request)

        assert "storage path" in field_errors(data, "file")[0]
        assert (await reload(document)).file.name == before

    async def test_get_serializes_stored_name(self):
        request = await superuser_request()
        document, _ = await make_document()

        data = await call(handle_get, "document", {"id": document.pk}, request)

        assert data["file"] == document.file.name


@pytest.mark.asyncio
@pytest.mark.django_db
class TestBulkWithFile:
    async def test_bulk_create(self):
        request = await superuser_request()
        items = [
            {"title": "One", "file": upload("one.pdf", b"1")},
            {"title": "Two", "file": {"filename": "two.pdf", "content_base64": "@"}},
            {"title": "Three"},
        ]

        data = await call(handle_bulk, "document", {"operation": "create", "items": items}, request)

        assert [entry["index"] for entry in data["results"]["success"]] == [0], data
        created = await sync_to_async(Document.objects.get)(pk=data["results"]["success"][0]["id"])
        assert await read(created.file) == b"1"
        errors = {entry["index"]: entry for entry in data["results"]["errors"]}
        assert "base64" in field_errors(errors[1], "file")[0]
        assert field_errors(errors[2], "file") == ["This field is required."]

    async def test_bulk_update(self):
        request = await superuser_request()
        first, _ = await make_document(appendix=True)
        second, _ = await make_document(appendix=True)
        second_file = second.file.name
        items = [
            {"id": first.pk, "data": {"file": upload("fresh.txt", b"fresh"), "appendix": None}},
            {"id": second.pk, "data": {"file": "documents/x.pdf"}},
        ]

        data = await call(handle_bulk, "document", {"operation": "update", "items": items}, request)

        assert [entry["index"] for entry in data["results"]["success"]] == [0], data
        first = await reload(first)
        assert await read(first.file) == b"fresh"
        assert not first.appendix
        assert "storage path" in field_errors(data["results"]["errors"][0], "file")[0]
        assert (await reload(second)).file.name == second_file


@pytest.mark.asyncio
@pytest.mark.django_db
class TestInlineRowsWithFile:
    async def test_create_parent_with_inline_files(self):
        request = await superuser_request()

        data = await call(
            handle_create,
            "document",
            {
                "data": {"title": "Manual", "file": upload()},
                "inlines": {
                    "documentpage": [
                        {"data": {"label": "one", "scan": upload("one.txt", b"page one")}},
                        {"data": {"label": "two", "scan": upload("two.txt", b"page two")}},
                    ]
                },
            },
            request,
        )

        assert data.get("success") is True, data
        pages = await sync_to_async(
            lambda: list(DocumentPage.objects.filter(document_id=data["id"]).order_by("label"))
        )()
        assert [page.label for page in pages] == ["one", "two"]
        assert [await read(page.scan) for page in pages] == [b"page one", b"page two"]
        assert all(page.scan.name.startswith("pages/") for page in pages)

    async def test_add_and_change_inline_rows_on_update(self):
        request = await superuser_request()
        document, (kept, changed) = await make_document(pages=2)
        kept_scan = kept.scan.name

        data = await call(
            handle_update,
            "document",
            {
                "id": document.pk,
                "inlines": {
                    "documentpage": [
                        {"data": {"label": "added", "scan": upload("added.txt", b"added")}},
                        {"id": changed.pk, "data": {"scan": upload("replaced.txt", b"replaced")}},
                        {"id": kept.pk, "data": {"label": "relabelled"}},
                    ]
                },
            },
            request,
        )

        assert data.get("success") is True, data
        kept = await reload(kept)
        assert (kept.label, kept.scan.name) == ("relabelled", kept_scan)
        changed = await reload(changed)
        assert changed.label == "P1"
        assert await read(changed.scan) == b"replaced"
        added = await sync_to_async(DocumentPage.objects.get)(document=document, label="added")
        assert await read(added.scan) == b"added"

    async def test_inline_upload_errors_reject_the_whole_write(self):
        request = await superuser_request()
        document, (page,) = await make_document(pages=1)
        before = (document.title, page.scan.name)

        data = await call(
            handle_update,
            "document",
            {
                "id": document.pk,
                "data": {"title": "Changed"},
                "inlines": {
                    "documentpage": [
                        {"id": page.pk, "data": {"scan": "pages/x.txt"}},
                        {"data": {"label": "no scan"}},
                        {"data": {"label": "bad", "scan": {"filename": "a.txt", "content_base64": "@"}}},
                        {"id": page.pk + 1000, "data": {"scan": None}},
                    ]
                },
            },
            request,
        )

        assert data.get("code") == "inline_error", data
        errors = {entry["index"]: entry for entry in data["inlines"]["errors"]}
        assert "storage path" in field_errors({"code": "validation_error", **errors[0]}, "scan")[0]
        assert field_errors({"code": "validation_error", **errors[1]}, "scan") == ["This field is required."]
        assert "base64" in field_errors({"code": "validation_error", **errors[2]}, "scan")[0]
        assert all("invalid_fields" not in entry for entry in errors.values())
        document = await reload(document)
        assert (document.title, (await reload(page)).scan.name) == before
        assert await sync_to_async(document.pages.count)() == 1

    async def test_null_on_required_inline_file_is_rejected(self):
        request = await superuser_request()
        document, (page,) = await make_document(pages=1)

        data = await call(
            handle_update,
            "document",
            {"id": document.pk, "inlines": {"documentpage": [{"id": page.pk, "data": {"scan": None}}]}},
            request,
        )

        assert data.get("code") == "inline_error", data
        entry = data["inlines"]["errors"][0]
        assert field_errors({"code": "validation_error", **entry}, "scan") == ["This field is required."]
        assert (await reload(page)).scan.name == page.scan.name


@pytest.mark.asyncio
@pytest.mark.django_db
class TestAuditLog:
    """File content must never reach the admin LogEntry; filename and size do."""

    CONTENT = b"SECRET-FILE-BODY-" * 4

    def assert_summarised(self, messages, filename):
        assert len(messages) == 1
        message = messages[0]
        assert b64(self.CONTENT) not in message
        assert b64(self.CONTENT)[:12] not in message
        assert "content_base64" not in message
        assert filename in message
        assert str(len(self.CONTENT)) in message

    async def test_create_logs_filename_and_size_only(self):
        request = await superuser_request()

        data = await call(
            handle_create,
            "document",
            {"data": {"title": "Manual", "file": upload("../secret.pdf", self.CONTENT)}},
            request,
        )

        assert data.get("success") is True, data
        document = await sync_to_async(Document.objects.get)(pk=data["id"])
        messages = await log_messages(document)
        self.assert_summarised(messages, "secret.pdf")
        assert "../" not in messages[0]

    async def test_update_logs_filename_and_size_only(self):
        request = await superuser_request()
        document, _ = await make_document()

        data = await call(
            handle_update,
            "document",
            {"id": document.pk, "data": {"file": upload("secret.pdf", self.CONTENT)}},
            request,
        )

        assert data.get("success") is True, data
        self.assert_summarised(await log_messages(document), "secret.pdf")

    async def test_bulk_update_logs_filename_and_size_only(self):
        request = await superuser_request()
        document, _ = await make_document()
        items = [{"id": document.pk, "data": {"file": upload("secret.pdf", self.CONTENT)}}]

        data = await call(handle_bulk, "document", {"operation": "update", "items": items}, request)

        assert len(data["results"]["success"]) == 1, data
        self.assert_summarised(await log_messages(document), "secret.pdf")

    async def test_serializer_summarises_any_upload_shaped_value(self):
        logged = json.loads(
            _serialize_data_for_log(
                {
                    "title": "t",
                    "file": upload("dir/secret.pdf", self.CONTENT, content_type="application/pdf"),
                    "broken": {"content_base64": "@@@@", "filename": 5},
                }
            )
        )

        assert logged["title"] == "t"
        assert logged["file"] == {"filename": "secret.pdf", "size": len(self.CONTENT)}
        assert set(logged["broken"]) == {"filename", "size"}
        assert "@@@@" not in json.dumps(logged)

    async def test_small_upload_is_not_logged_verbatim(self):
        # Short enough to survive the log's length limit untouched
        logged = _serialize_data_for_log({"file": {"filename": "a.txt", "content_base64": "aGk="}})

        assert "aGk=" not in logged
        assert json.loads(logged) == {"file": {"filename": "a.txt", "size": 2}}


@pytest.mark.asyncio
@pytest.mark.django_db
class TestUploadDocumentation:
    async def test_write_tool_descriptions_explain_the_upload_shape(self):
        tools = {tool.name: tool for tool in await sync_to_async(get_model_tools)(Document)}

        for name in ("create_document", "update_document", "bulk_document"):
            description = tools[name].description
            assert "content_base64" in description, name
            assert "filename" in description, name
        assert "null" in tools["update_document"].description

    async def test_models_without_file_fields_are_not_told_about_uploads(self):
        tools = {tool.name: tool for tool in await sync_to_async(get_model_tools)(Article)}

        for name in ("create_article", "update_article", "bulk_article"):
            assert "content_base64" not in tools[name].description

    async def test_describe_reports_upload_shape_for_file_fields(self, settings):
        settings.MCP_UPLOAD_MAX_FILE_BYTES = 1234
        request = await superuser_request()

        data = await call(handle_describe, "document", {}, request)

        fields = {field["name"]: field for field in data["fields"]}
        for name in ("file", "appendix"):
            hint = fields[name]["upload"]
            assert set(hint["value"]) == {"filename", "content_base64", "content_type"}
            assert hint["max_bytes"] == 1234
        assert fields["file"]["upload"]["clearable"] is False
        assert fields["appendix"]["upload"]["clearable"] is True
        assert "upload" not in fields["title"]
