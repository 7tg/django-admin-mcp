# Client Setup

This guide covers configuring MCP clients to connect to Django Admin MCP.

## MCP Client

Any MCP-compatible client can interact with Django Admin MCP.

### Project Configuration (Claude Code)

Create `.mcp.json` in your project root:

```json title=".mcp.json"
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

!!! tip "Project-Specific Tokens"
    Use project configuration for project-specific tokens. Add `.mcp.json` to `.gitignore` to avoid committing tokens.

### Multiple Servers

Configure multiple Django projects:

```json
{
  "mcpServers": {
    "blog-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer BLOG_TOKEN"
      }
    },
    "shop-admin": {
      "type": "http",
      "url": "http://localhost:8001/mcp/",
      "headers": {
        "Authorization": "Bearer SHOP_TOKEN"
      }
    }
  }
}
```

### Applying Configuration

After editing the configuration:

1. Restart your MCP client
2. The MCP server should connect automatically
3. Tools will be available for use

### Verifying Connection

Ask the agent to list available tools:

```
User: What Django admin tools are available?
Agent: [calls tools/list]
I have access to the following Django admin tools:
- find_models: Discover available Django models
- list_article: List Article instances
- get_article: Get a single Article
...
```

## Other MCP Clients

Django Admin MCP works with any MCP-compatible client that supports HTTP transport.

### Generic HTTP Client

The endpoint speaks JSON-RPC 2.0: `tools/call` takes `name` and `arguments` nested under `params`. Test with curl:

```bash
# Initialize (MCP handshake)
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize"}'

# List available tools
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}'

# Call a tool
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": "find_models", "arguments": {}}
  }'
```

The server also supports `prompts/list`, `prompts/get`, `resources/list`, `resources/templates/list`, and `resources/read` — see [Prompts & Resources](prompts-resources.md).

### Python Client

Using the `requests` library:

```python
import requests

BASE_URL = "http://localhost:8000/mcp/"
TOKEN = "your-token-here"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# List tools
response = requests.post(
    BASE_URL,
    headers=headers,
    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
)
tools = response.json()["result"]["tools"]

# Call a tool
response = requests.post(
    BASE_URL,
    headers=headers,
    json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "list_article", "arguments": {"limit": 10}},
    },
)
result = response.json()["result"]  # {"content": [{"type": "text", "text": "<json>"}]}
```

### JavaScript/TypeScript Client

```typescript
const BASE_URL = "http://localhost:8000/mcp/";
const TOKEN = "your-token-here";

async function callTool(name: string, args: object = {}) {
  const response = await fetch(BASE_URL, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: { name, arguments: args },
    }),
  });
  const body = await response.json();
  return body.result; // {"content": [{"type": "text", "text": "<json>"}]}
}

// Usage
const articles = await callTool("list_article", { limit: 10 });
```

## Environment-Specific Setup

### Development

```json title=".mcp.json"
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer DEV_TOKEN"
      }
    }
  }
}
```

### Staging/Production

```json title=".mcp.json"
{
  "mcpServers": {
    "django-admin": {
      "type": "http",
      "url": "https://staging.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer STAGING_TOKEN"
      }
    }
  }
}
```

!!! warning "Production Security"
    Always use HTTPS in production to protect tokens in transit.

## Troubleshooting

### Connection Refused

```
Error: Connection refused
```

- Verify Django server is running
- Check the URL and port are correct — `curl http://localhost:8000/mcp/health/` should return `{"status": "ok", "service": "django-admin-mcp"}` without a token
- Ensure no firewall is blocking the connection

### Authentication Failed

```
{"error": "Invalid or missing authentication token"}
```

- Verify the token is correct
- Check the token is active (`is_active=True`)
- Ensure the token hasn't expired

### Unauthorized with MCP Inspector (OAuth discovery 404s)

If you connect with `npx @modelcontextprotocol/inspector` and see a `401` on
`/mcp/` followed by requests to `/.well-known/oauth-protected-resource`,
`/.well-known/oauth-authorization-server`, and `/register` returning `404`:

```
Unauthorized: /mcp/
Not Found: /.well-known/oauth-protected-resource
Not Found: /.well-known/oauth-authorization-server
Not Found: /register
```

This is expected. Django Admin MCP uses **static Bearer tokens**, not OAuth —
after a `401`, the Inspector automatically tries OAuth discovery, which this
server doesn't implement. To fix it, pass the token explicitly:

1. In the Inspector sidebar, select transport **Streamable HTTP** and enter
   your server URL (e.g. `http://localhost:8000/mcp/`)
2. Open **Authentication** and set **Header Name** to `Authorization` and
   **Bearer Token** to your token (`mcp_...`)
3. Click **Connect**

The `/.well-known/*` 404 messages disappear once the Bearer token is sent
with each request.

### Permission Denied

Tool calls that fail a permission check return HTTP 200 with an error object inside the JSON-RPC result:

```json
{"error": "Permission denied: cannot view article", "code": "permission_denied"}
```

- The token lacks the required permission
- Grant the permission to the token (via its `permissions` or `groups` fields in the MCP Token admin)

### No Tools Available

`tools/list` always includes `find_models`, even with zero exposed models — so a truly empty tool list means the request itself failed. If only `find_models` appears:

- No models have `MCPAdminMixin` with `mcp_expose = True`
- Check your admin configuration

## Next Steps

- [Tools Overview](../tools/overview.md) — Learn about available tools
- [Examples](../examples/conversations.md) — See example interactions
