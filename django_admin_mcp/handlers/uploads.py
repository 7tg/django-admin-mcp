"""
File uploads for ``FileField`` / ``ImageField`` values (issue #120).

MCP carries JSON only, so a file travels inside ``data`` as an object::

    {"filename": "x.pdf", "content_base64": "...", "content_type": "application/pdf"}

``bind_upload()`` turns that object into an uploaded file and puts it into the
form's ``files``, which is where a file field reads its value from. It is
called from ``shape_admin_form()``, the one place every write path (create,
update, bulk, inline rows) shapes its forms, so the form field's own
validation (required, validators, image checks, ``max_length``) applies
everywhere.
"""

import base64
import binascii
import mimetypes
from collections.abc import MutableMapping
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

# Default cap on the decoded size of one uploaded file (override via settings).
_DEFAULT_MAX_UPLOAD_FILE_BYTES = 5 * 1024 * 1024

_REQUIRED_KEYS = ("filename", "content_base64")
_UPLOAD_KEYS = frozenset({*_REQUIRED_KEYS, "content_type"})
_DEFAULT_CONTENT_TYPE = "application/octet-stream"

_JSON_TYPE_NAMES = {str: "a string", bool: "a boolean", int: "a number", float: "a number", list: "an array"}

# The upload shape, as shown to callers in tool descriptions and describe_*
UPLOAD_SHAPE = '{"filename": "x.pdf", "content_base64": "<base64 content>", "content_type": "application/pdf"}'


class UploadError(ValueError):
    """A file value that cannot be turned into an upload; the message is safe to return."""


def max_upload_file_bytes() -> int:
    """Largest decoded size accepted for one uploaded file (``MCP_UPLOAD_MAX_FILE_BYTES``)."""
    from django.conf import settings  # noqa: PLC0415

    return int(getattr(settings, "MCP_UPLOAD_MAX_FILE_BYTES", _DEFAULT_MAX_UPLOAD_FILE_BYTES))


def _basename(filename: Any) -> str:
    """Reduce a caller-supplied filename to its last path component ('' when there is none)."""
    if not isinstance(filename, str):
        return ""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "" if name in {".", ".."} else name


def _decoded_size(encoded: str) -> int:
    """Size the base64 text decodes to, computed from its length alone."""
    return len(encoded) * 3 // 4 - encoded[-2:].count("=")


def decode_upload(value: Any) -> SimpleUploadedFile:
    """
    Turn a caller-supplied file object into an uploaded file.

    Args:
        value: ``{"filename": str, "content_base64": str, "content_type": str (optional)}``.

    Returns:
        The uploaded file, named by the basename of ``filename``.

    Raises:
        UploadError: ``value`` is not such an object, the base64 is invalid,
            or the content exceeds ``MCP_UPLOAD_MAX_FILE_BYTES``.
    """
    if not isinstance(value, dict):
        got = _JSON_TYPE_NAMES.get(type(value), "another value")
        hint = " Referencing an existing storage path is not supported." if isinstance(value, str) else ""
        raise UploadError(f"A file must be sent as an object {UPLOAD_SHAPE}, not {got}.{hint}")

    unknown = sorted(str(key) for key in set(value) - _UPLOAD_KEYS)
    if unknown:
        raise UploadError(
            f"Unknown key in file object: {', '.join(unknown)}. Allowed keys: {', '.join(sorted(_UPLOAD_KEYS))}."
        )

    filename = _basename(value.get("filename"))
    if not filename:
        raise UploadError("filename is required and must be a non-empty file name.")

    encoded = value.get("content_base64")
    if not isinstance(encoded, str):
        raise UploadError("content_base64 is required and must be a base64 string.")

    content_type = value.get("content_type")
    if content_type is None:
        content_type = mimetypes.guess_type(filename)[0] or _DEFAULT_CONTENT_TYPE
    elif not isinstance(content_type, str) or not content_type.strip():
        raise UploadError("content_type must be a non-empty string when given.")

    # Line-wrapped base64 is common; the size is judged without the wrapping
    encoded = "".join(encoded.split())
    limit = max_upload_file_bytes()
    size = _decoded_size(encoded)
    if size > limit:
        # Refused from the encoded length: an oversized body is never decoded
        raise UploadError(f"File is too large: {size} bytes exceeds MCP_UPLOAD_MAX_FILE_BYTES ({limit} bytes).")

    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise UploadError("content_base64 is not valid base64.") from None

    return SimpleUploadedFile(filename, content, content_type=content_type.strip())


def _reject(field: Any, message: str) -> None:
    """Make a form field fail validation with ``message``, whatever it is bound to."""

    def clean(*args: Any, **kwargs: Any) -> Any:
        raise ValidationError(message)

    # form.fields holds per-form copies, so only this form is affected. The
    # error surfaces through form.errors like any other field error.
    field.clean = clean


def bind_upload(form: Any, field: Any, post: MutableMapping[str, Any], key: str) -> None:
    """
    Move a file field's caller-supplied value from the form's data into its files.

    - a file object is decoded and bound as the field's upload;
    - ``null`` clears the field through the widget's clear checkbox, which
      only an optional field has: on a required field it is the field's
      "required" error;
    - anything else is reported as a validation error on the field.

    Args:
        form: The bound form; ``form.files`` receives the upload.
        field: The form's file field (a per-form copy).
        post: The form's mutable data dict; ``key`` is removed from it.
        key: The field's prefixed name in ``post``.
    """
    value = post.pop(key)

    if value is None:
        clear_checkbox_name = getattr(field.widget, "clear_checkbox_name", None)
        if field.required:
            _reject(field, field.error_messages["required"])
        elif not callable(clear_checkbox_name):
            _reject(field, "This file field cannot be cleared.")
        else:
            post[clear_checkbox_name(key)] = True
        return

    try:
        upload = decode_upload(value)
    except UploadError as e:
        _reject(field, str(e))
        return

    if not isinstance(form.files, MutableMapping):
        form.files = {}
    form.files[key] = upload


def is_upload_value(value: Any) -> bool:
    """Whether a value looks like a file object, valid or not."""
    return isinstance(value, dict) and "content_base64" in value


def summarize_uploads(value: Any) -> Any:
    """
    Replace every file object in ``value`` with its filename and size.

    Used for the audit log: file content must never be written there. The
    size is derived from the base64 length, so nothing is decoded.
    """
    if is_upload_value(value):
        encoded = value["content_base64"]
        size = _decoded_size("".join(encoded.split())) if isinstance(encoded, str) else None
        return {"filename": _basename(value.get("filename")) or None, "size": size}
    if isinstance(value, dict):
        return {key: summarize_uploads(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [summarize_uploads(item) for item in value]
    return value


def describe_upload(required: bool) -> dict[str, Any]:
    """The ``upload`` hint describe_* attaches to a file field."""
    return {
        "value": {
            "filename": "string, required; reduced to its base name",
            "content_base64": "string, required; the file content, base64-encoded",
            "content_type": "string, optional; guessed from the filename when absent",
        },
        "max_bytes": max_upload_file_bytes(),
        "clearable": not required,
    }


def upload_doc() -> str:
    """One paragraph for write tool descriptions of models that have file fields."""
    return (
        f"File and image fields take an object {UPLOAD_SHAPE} "
        "(content_type is optional and guessed from the filename; "
        f"decoded content is limited to {max_upload_file_bytes()} bytes). "
        "null clears an optional file; a field left out keeps its stored file. "
        "A plain string (e.g. a storage path) is rejected."
    )
