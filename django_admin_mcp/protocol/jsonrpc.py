"""
JSON-RPC 2.0 message types for MCP protocol.
"""

from pydantic import BaseModel
from typing import Literal, Any


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any | None = None


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request message."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response message."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int
    result: Any | None = None
    error: JsonRpcError | None = None
