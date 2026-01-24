"""
JSON-RPC 2.0 message types for MCP protocol.
"""

from typing import Any, Literal

from pydantic import BaseModel


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request message."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response message."""

    model_config = {"extra": "forbid"}

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcError | None = None

    def model_dump(self, **kwargs):
        """Override to exclude None values by default."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)
