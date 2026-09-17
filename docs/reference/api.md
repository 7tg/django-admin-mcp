# HTTP API Reference

Django Admin MCP routes three HTTP endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp/` | POST | MCP protocol over JSON-RPC 2.0 |
| `/mcp/health/` | GET | Health check (no authentication) |
| `/mcp/mcp_<key>.<secret>/` | POST | Same as `/mcp/`, token read from the path — `404` unless [`MCP_ALLOW_URL_TOKEN`](settings.md#mcp_allow_url_token) is enabled |

!!! note "URL prefix"
    The `/mcp/` prefix depends on where your project mounts `include('django_admin_mcp.urls')` — the paths above assume `path('mcp/', include('django_admin_mcp.urls'))`.

The codebase also contains a legacy class-based view (`MCPHTTPView`) that returns bare JSON responses, but it is **not routed** by `django_admin_mcp.urls` — only the JSON-RPC endpoint and the health check are.

## Authentication

All requests to the MCP endpoint require Bearer token authentication:

```http
Authorization: Bearer mcp_yourkey.yoursecret
```

Tokens are created in Django admin at `/admin/django_admin_mcp/mcptoken/`. Each authenticated request updates the token's `last_used_at` timestamp.

Clients that cannot send headers can pass the same token in the path instead — see [`MCP_ALLOW_URL_TOKEN`](settings.md#mcp_allow_url_token).

### Authentication Errors

| Status | Response | Cause |
|--------|----------|-------|
| 401 | `{"error": "Invalid or missing authentication token"}` | Missing, invalid, expired, or inactive token |

---

## Request Format

All requests are JSON-RPC 2.0 messages. For `tools/call`, the tool name and arguments are nested under `params`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {"limit": 10}
  }
}
```

!!! warning "No flat request shape"
    A flat top-level `name`/`arguments` shape (without `params`) is rejected with HTTP 400 and a body like `{"error": "Invalid request", "details": [...]}`.

### Content-Type

```http
Content-Type: application/json
```

---

## Response Format

Responses use the JSON-RPC 2.0 envelope. A successful `tools/call` returns:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\": [...], \"count\": 10, \"total_count\": 42}"
      }
    ]
  }
}
```

The `text` field contains JSON-encoded data specific to each tool. Fields that are `None` are stripped from the envelope.

### Tool-Level Errors

Tool-level errors (permission denied, object not found, validation failure) arrive with HTTP 200 as a JSON error object inside `result.content[0].text` — there is no `isError` flag:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"error\": \"Permission denied: cannot delete article\", \"code\": \"permission_denied\"}"
      }
    ]
  }
}
```

Common tool-level error shapes:

| Error | Body (inside `text`) |
|-------|----------------------|
| Permission denied | `{"error": "Permission denied: cannot <action> <model_name>", "code": "permission_denied"}` |
| Not found | `{"error": "<model_name> not found"}` |
| Validation failed | `{"error": "Validation failed", "code": "validation_error", "validation_errors": {...}}` |

### Protocol-Level Errors

Some failures use the JSON-RPC `error` member instead of `result`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "uri parameter is required"
  }
}
```

| JSON-RPC code | HTTP status | Cause |
|---------------|-------------|-------|
| -32700 | 200 | Body is not a valid JSON-RPC request (parse error) |
| -32601 | 200 | `Method not found: x` (unsupported method) |
| -32602 | 200 | Malformed `tools/call` or `tools/list` params (sanitized details in `error.data`), unknown `prompts/get` name, or missing `resources/read` uri |
| -32002 | 200 | Resource error (e.g. unknown resource URI) |
| -32000 | 200 | `Invalid JSON in tool result` or `No result from tool` |

`notifications/initialized` returns an empty HTTP 202 response (notifications get no JSON-RPC body). Transport-level failures still return bare (non-JSON-RPC) error bodies:

| HTTP status | Body | Cause |
|-------------|------|-------|
| 401 | `{"error": "Invalid or missing authentication token"}` | Auth failure |
| 405 | `{"error": "Method not allowed"}` | Non-POST request to the MCP endpoint |

---

## Methods

The endpoint supports nine JSON-RPC methods:

| Method | Purpose |
|--------|---------|
| `initialize` | MCP handshake; returns protocol version, server info, capabilities |
| `notifications/initialized` | Client acknowledgement after initialize |
| `tools/list` | List all available tools |
| `tools/call` | Execute a tool |
| `prompts/list` | List available prompts |
| `prompts/get` | Get a prompt by name |
| `resources/list` | List available resources |
| `resources/templates/list` | List resource URI templates |
| `resources/read` | Read a resource by URI |

### initialize

**Request:**

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}'
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "serverInfo": {
      "name": "django-admin-mcp",
      "version": "0.3.2"
    },
    "capabilities": {
      "tools": {},
      "prompts": {},
      "resources": {}
    }
  }
}
```

`serverInfo.version` reflects the installed `django-admin-mcp` package version.

The client then sends `notifications/initialized` to complete the handshake:

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
```

The server answers with an empty HTTP 202 response (notifications carry no `id` and get no JSON-RPC body).

### tools/list

Lists all available MCP tools.

**Request:**

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "find_models",
        "description": "Discover available Django models",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "Optional search query"
            }
          }
        }
      },
      {
        "name": "list_article",
        "description": "List article instances with filtering, searching, ordering, and pagination...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "limit": {"type": "integer"},
            "offset": {"type": "integer"},
            "search": {"type": "string"},
            "order_by": {"type": "array"},
            "filters": {"type": "object"}
          }
        }
      }
    ]
  }
}
```

### tools/call

Executes a specific tool.

**Request:**

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_article",
      "arguments": {"limit": 10}
    }
  }'
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"results\": [...], \"count\": 10, \"total_count\": 42}"
      }
    ]
  }
}
```

### prompts/list and prompts/get

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "prompts/list"}'
```

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "prompts/get",
    "params": {"name": "explore_models", "arguments": {}}
  }'
```

An unknown prompt name returns a JSON-RPC error with code `-32602`.

### resources/list, resources/templates/list, and resources/read

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}'
```

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "resources/templates/list"}'
```

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "resources/read",
    "params": {"uri": "models://article/schema"}
  }'
```

A missing `uri` returns a JSON-RPC error with code `-32602`; a resource error returns code `-32002`.

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success — including tool-level errors, which arrive as an `{"error": ..., "code": ...}` JSON object embedded in `result.content[0].text`, and JSON-RPC errors `-32602`/`-32002` |
| 400 | Invalid request body, invalid `tools/call` params, or unknown method |
| 401 | Authentication failed |
| 405 | Method not allowed (the MCP endpoint only accepts POST) |
| 500 | Server error — JSON-RPC error code `-32000` (`Invalid JSON in tool result` or `No result from tool`) |

---

## Example Requests

### Find Models

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "find_models",
      "arguments": {}
    }
  }'
```

### List Articles

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "list_article",
      "arguments": {
        "limit": 10,
        "offset": 0,
        "order_by": ["-created_at"],
        "filters": {"published": true}
      }
    }
  }'
```

### Get Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_article",
      "arguments": {"id": 42}
    }
  }'
```

### Create Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "create_article",
      "arguments": {
        "data": {
          "title": "New Article",
          "content": "Article content...",
          "author_id": 5
        }
      }
    }
  }'
```

### Update Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "update_article",
      "arguments": {
        "id": 42,
        "data": {"published": true}
      }
    }
  }'
```

### Delete Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 6,
    "method": "tools/call",
    "params": {
      "name": "delete_article",
      "arguments": {"id": 42}
    }
  }'
```

### Execute Action

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 7,
    "method": "tools/call",
    "params": {
      "name": "action_article",
      "arguments": {
        "action": "mark_as_published",
        "ids": [1, 2, 3]
      }
    }
  }'
```

### Bulk Update

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 8,
    "method": "tools/call",
    "params": {
      "name": "bulk_article",
      "arguments": {
        "operation": "update",
        "items": [
          {"id": 10, "data": {"status": "archived"}},
          {"id": 11, "data": {"status": "archived"}},
          {"id": 12, "data": {"status": "archived"}}
        ]
      }
    }
  }'
```

---

## Health Check

A separate endpoint provides health status:

```
GET /mcp/health/
```

**Response:**

```json
{
  "status": "ok",
  "service": "django-admin-mcp"
}
```

This endpoint does not require authentication.

---

## Rate Limiting

Django Admin MCP does not implement rate limiting by default. Implement rate limiting at the web server or Django level if needed:

- **nginx** — Use `limit_req` directive
- **Django** — Use `django-ratelimit` package
- **Cloudflare** — Use rate limiting rules

---

## CORS

If accessing from browsers, configure CORS headers:

```python title="settings.py"
INSTALLED_APPS = [
    'corsheaders',
    # ...
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    # ...
]

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
```
