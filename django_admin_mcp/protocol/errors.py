"""
MCP error code constants following JSON-RPC 2.0 specification.
"""


class MCPErrorCode:
    """Standard JSON-RPC 2.0 error codes for MCP protocol."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
