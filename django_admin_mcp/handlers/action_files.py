"""
File-download serialization for admin action results.

Converts the HttpResponse/StreamingHttpResponse a download action returns
into a structured MCP payload (UTF-8 text or base64), parsing filename and
charset headers and enforcing a configurable size cap.
"""

import base64
import re
from typing import Any
from urllib.parse import unquote

from django.http import HttpResponse, StreamingHttpResponse

# RFC 5987 / 6266: filename*=charset'lang'value (prefer over plain filename=).
_FILENAME_STAR_RE = re.compile(
    r"""filename\*=([^']*)'[^']*'([^;\n]+)""",
    re.IGNORECASE,
)
_FILENAME_RE = re.compile(
    r"""filename=(?!\*)["']?([^";\n]+)["']?""",
    re.IGNORECASE,
)

_TEXT_CONTENT_TYPE_PREFIXES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
)

_TEXT_CONTENT_TYPE_EXACT = frozenset({"text/csv", "text/tsv", "application/csv"})

# Default cap for buffering download bodies into MCP JSON (override via settings).
_DEFAULT_MAX_ACTION_FILE_BYTES = 5 * 1024 * 1024


class ActionFileTooLargeError(ValueError):
    """Raised when an action file response exceeds MCP_ACTION_MAX_FILE_BYTES."""


def _max_action_file_bytes() -> int:
    from django.conf import settings  # noqa: PLC0415

    return int(getattr(settings, "MCP_ACTION_MAX_FILE_BYTES", _DEFAULT_MAX_ACTION_FILE_BYTES))


def _filename_from_content_disposition(disposition: str) -> str | None:
    """Parse a filename from a Content-Disposition header value.

    Prefers RFC 5987 ``filename*`` (percent-decoded) over plain ``filename``.
    """
    if not disposition:
        return None
    star = _FILENAME_STAR_RE.search(disposition)
    if star:
        charset = star.group(1).strip() or "utf-8"
        raw = star.group(2).strip().strip("\"'")
        try:
            return unquote(raw, encoding=charset, errors="strict")
        except (LookupError, UnicodeDecodeError):
            return unquote(raw, encoding="utf-8", errors="replace")
    match = _FILENAME_RE.search(disposition)
    if not match:
        return None
    return match.group(1).strip().strip("\"'")


def _is_text_content_type(content_type: str) -> bool:
    """Return True when content should be returned as text (not base64) to MCP clients."""
    lowered = (content_type or "").split(";")[0].strip().lower()
    if any(lowered.startswith(prefix) for prefix in _TEXT_CONTENT_TYPE_PREFIXES):
        return True
    return lowered in _TEXT_CONTENT_TYPE_EXACT


def _charset_from_content_type(content_type: str) -> str | None:
    """Extract a charset parameter from a Content-Type header value."""
    if not content_type:
        return None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            return part.split("=", 1)[1].strip().strip("\"'") or None
    return None


def _decode_text_body(
    body: bytes,
    content_type: str,
    response_charset: str | None = None,
) -> str:
    """Decode a text download body using Content-Type / response charset."""
    charset = _charset_from_content_type(content_type) or response_charset or "utf-8"
    return body.decode(charset)


def _ensure_bytes(chunk: Any) -> bytes:
    if isinstance(chunk, memoryview):
        return chunk.tobytes()
    if isinstance(chunk, bytes):
        return chunk
    return bytes(chunk)


def _http_response_body(response: HttpResponse | StreamingHttpResponse) -> bytes:
    """Read the full body from an HttpResponse or StreamingHttpResponse.

    Raises ActionFileTooLargeError if the body exceeds MCP_ACTION_MAX_FILE_BYTES.
    Closes streaming responses after buffering so file-backed iterators release FDs.
    """
    max_bytes = _max_action_file_bytes()
    streaming_content = getattr(response, "streaming_content", None)
    try:
        if streaming_content is not None:
            chunks: list[bytes] = []
            total = 0
            for chunk in streaming_content:
                data = _ensure_bytes(chunk)
                total += len(data)
                if total > max_bytes:
                    raise ActionFileTooLargeError(
                        f"Action file response exceeds MCP_ACTION_MAX_FILE_BYTES ({max_bytes} bytes)"
                    )
                chunks.append(data)
            return b"".join(chunks)

        content = _ensure_bytes(response.content)
        if len(content) > max_bytes:
            raise ActionFileTooLargeError(f"Action file response exceeds MCP_ACTION_MAX_FILE_BYTES ({max_bytes} bytes)")
        return content
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _response_header(response: HttpResponse | StreamingHttpResponse, name: str) -> str:
    """Read a response header across Django HttpResponse variants."""
    value = response.get(name, "") or ""
    if value:
        return value
    headers = getattr(response, "headers", None)
    if headers is not None:
        return headers.get(name, "") or ""
    return ""


def serialize_action_result(result: Any) -> Any:
    """
    Serialize an admin action return value for MCP JSON responses.

    Download actions typically return ``HttpResponse`` / ``StreamingHttpResponse``.
    Those are converted to a structured file payload (UTF-8 text or base64) with
    metadata. Other values fall back to ``str(result)``; ``None`` stays ``None``.
    """
    if result is None:
        return None

    if isinstance(result, (HttpResponse, StreamingHttpResponse)):
        disposition = _response_header(result, "Content-Disposition")
        content_type = (
            _response_header(result, "Content-Type")
            or getattr(result, "content_type", None)
            or "application/octet-stream"
        )
        body = _http_response_body(result)
        filename = _filename_from_content_disposition(disposition) or "download"
        payload: dict[str, Any] = {
            "type": "file",
            "content_type": content_type,
            "filename": filename,
            "size": len(body),
            "status_code": getattr(result, "status_code", 200),
        }
        if disposition:
            payload["content_disposition"] = disposition

        if _is_text_content_type(content_type):
            try:
                # encoding=utf-8 means JSON text content (not base64), regardless of
                # the HTTP charset used to decode the bytes into Unicode.
                payload["encoding"] = "utf-8"
                payload["content"] = _decode_text_body(
                    body,
                    content_type,
                    getattr(result, "charset", None),
                )
                return payload
            except (LookupError, UnicodeDecodeError):
                pass

        payload["encoding"] = "base64"
        payload["content"] = base64.b64encode(body).decode("ascii")
        return payload

    return str(result)
