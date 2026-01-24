# HTTP API Reference

Django Admin MCP exposes a single HTTP endpoint for the MCP protocol.

## Endpoint

```
POST /mcp/
```

All operations are performed via POST requests to this endpoint.

## Authentication

All requests require Bearer token authentication:

```http
Authorization: Bearer YOUR_TOKEN_HERE
```

Tokens are created in Django admin at `/admin/django_admin_mcp/mcptoken/`.

### Authentication Errors

| Status | Response | Cause |
|--------|----------|-------|
| 401 | `{"error": "Invalid or missing authentication token"}` | Missing or invalid token |
| 401 | `{"error": "Token has expired"}` | Token past expiration date |
| 401 | `{"error": "Token is inactive"}` | Token disabled |

---

## Request Format

All requests use JSON with this structure:

```json
{
  "method": "tools/list" | "tools/call",
  "name": "tool_name",           // Required for tools/call
  "arguments": {}                 // Required for tools/call
}
```

### Content-Type

```http
Content-Type: application/json
```

---

## Methods

### tools/list

Lists all available MCP tools.

**Request:**

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'
```

**Response:**

```json
{
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
      "description": "List all Article instances",
      "inputSchema": {
        "type": "object",
        "properties": {
          "limit": {"type": "integer"},
          "offset": {"type": "integer"},
          "search": {"type": "string"},
          "ordering": {"type": "string"},
          "filters": {"type": "object"}
        }
      }
    }
  ]
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
    "method": "tools/call",
    "name": "list_article",
    "arguments": {"limit": 10}
  }'
```

**Response:**

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"results\": [...], \"count\": 10, \"total\": 42}"
    }
  ]
}
```

---

## Response Format

### Success Response

```json
{
  "content": [
    {
      "type": "text",
      "text": "JSON-encoded result data"
    }
  ]
}
```

The `text` field contains JSON-encoded data specific to each tool.

### Error Response

```json
{
  "content": [
    {
      "type": "text",
      "text": "Error message"
    }
  ],
  "isError": true
}
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success (check `isError` for tool-level errors) |
| 400 | Invalid request format |
| 401 | Authentication failed |
| 405 | Method not allowed (use POST) |
| 500 | Server error |

---

## Example Requests

### List Tools

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'
```

### Find Models

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "find_models",
    "arguments": {}
  }'
```

### List Articles

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "list_article",
    "arguments": {
      "limit": 10,
      "offset": 0,
      "ordering": "-created_at",
      "filters": {"published": true}
    }
  }'
```

### Get Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "get_article",
    "arguments": {"id": 42}
  }'
```

### Create Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "create_article",
    "arguments": {
      "data": {
        "title": "New Article",
        "content": "Article content...",
        "author_id": 5
      }
    }
  }'
```

### Update Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "update_article",
    "arguments": {
      "id": 42,
      "data": {"published": true}
    }
  }'
```

### Delete Article

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "delete_article",
    "arguments": {"id": 42}
  }'
```

### Execute Action

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "action_article",
    "arguments": {
      "action": "mark_as_published",
      "ids": [1, 2, 3]
    }
  }'
```

### Bulk Update

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "bulk_article",
    "arguments": {
      "operation": "update",
      "ids": [10, 11, 12],
      "data": {"status": "archived"}
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

- **nginx**: Use `limit_req` directive
- **Django**: Use `django-ratelimit` package
- **Cloudflare**: Use rate limiting rules

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
