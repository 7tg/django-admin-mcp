# Client Setup

This guide covers configuring MCP clients to connect to Django Admin MCP.

## MCP Client

Any MCP-compatible client can interact with Django Admin MCP.

### Configuration File Locations

MCP clients typically look for configuration in these locations:

| Location | Scope | Priority |
|----------|-------|----------|
| `.mcp.json` | Project | Highest |
| `~/.claude/claude_desktop_config.json` | Global | Lower |

### Project Configuration

Create `.mcp.json` in your project root:

```json title=".mcp.json"
{
  "mcpServers": {
    "django-admin": {
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

### Global Configuration

For a single Django project across all sessions:

```json title="~/.claude/claude_desktop_config.json"
{
  "mcpServers": {
    "django-admin": {
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN_HERE"
      }
    }
  }
}
```

### Multiple Servers

Configure multiple Django projects:

```json
{
  "mcpServers": {
    "blog-admin": {
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "Authorization": "Bearer BLOG_TOKEN"
      }
    },
    "shop-admin": {
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

Test with curl:

```bash
# List available tools
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'

# Call a tool
curl -X POST http://localhost:8000/mcp/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "tools/call",
    "name": "find_models",
    "arguments": {}
  }'
```

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
    json={"method": "tools/list"}
)
tools = response.json()["tools"]

# Call a tool
response = requests.post(
    BASE_URL,
    headers=headers,
    json={
        "method": "tools/call",
        "name": "list_article",
        "arguments": {"limit": 10}
    }
)
result = response.json()
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
      method: "tools/call",
      name,
      arguments: args,
    }),
  });
  return response.json();
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
- Check the URL and port are correct
- Ensure no firewall is blocking the connection

### Authentication Failed

```
{"error": "Invalid or missing authentication token"}
```

- Verify the token is correct
- Check the token is active (`is_active=True`)
- Ensure the token hasn't expired

### Permission Denied

```
{"error": "Permission denied: blog.view_article"}
```

- Token lacks required permissions
- Add the permission to the token or its groups

### No Tools Available

If `tools/list` returns an empty list:

- No models have `MCPAdminMixin`
- No models have `mcp_expose = True`
- Check your admin configuration

## Next Steps

- [Tools Overview](../tools/overview.md) - Learn about available tools
- [Examples](../examples/conversations.md) - See example interactions
