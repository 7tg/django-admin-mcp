# MCP Integration Guide

## What is MCP?

MCP (Model Context Protocol) is a protocol that allows AI assistants and other clients to interact with data sources and tools through a standardized interface. This package enables Django admin models to be accessible through MCP, allowing programmatic access to your Django admin interface.

## Architecture

```
┌─────────────────┐
│   MCP Client    │ (e.g., Claude Desktop, AI Assistant)
└────────┬────────┘
         │ MCP Protocol (stdio)
         │
┌────────▼────────┐
│   MCP Server    │ (django-admin-mcp)
└────────┬────────┘
         │
┌────────▼────────┐
│  Django Admin   │ (Your ModelAdmin classes)
└────────┬────────┘
         │
┌────────▼────────┐
│    Database     │ (PostgreSQL, MySQL, SQLite, etc.)
└─────────────────┘
```

## How It Works

1. **Mixin Registration**: When you add `MCPAdminMixin` to a `ModelAdmin` class during Django startup, it registers the model with the MCP server.

2. **Tool Generation**: For each registered model, 5 CRUD tools are automatically generated:
   - `list_<model>`: Retrieve multiple instances
   - `get_<model>`: Retrieve a single instance by ID
   - `create_<model>`: Create a new instance
   - `update_<model>`: Update an existing instance
   - `delete_<model>`: Delete an instance

3. **Schema Generation**: Tool schemas are automatically generated from Django model fields, including field types and requirements.

4. **Request Handling**: When an MCP client calls a tool:
   - The request is received via stdio
   - The tool name is parsed to identify the operation and model
   - The appropriate handler performs the database operation
   - Results are serialized and returned to the client

## Tool Schema Example

For an `Article` model with fields `title`, `content`, and `author_id`, the generated tool schemas would look like:

### list_article
```json
{
  "name": "list_article",
  "description": "List all Article instances with optional pagination",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "description": "Maximum number of items to return",
        "default": 100
      },
      "offset": {
        "type": "integer",
        "description": "Number of items to skip",
        "default": 0
      }
    }
  }
}
```

### create_article
```json
{
  "name": "create_article",
  "description": "Create a new Article",
  "inputSchema": {
    "type": "object",
    "properties": {
      "data": {
        "type": "object",
        "description": "The data for the new Article"
      }
    },
    "required": ["data"]
  }
}
```

## Response Format

All tools return JSON responses in the following format:

### Successful List Response
```json
{
  "count": 2,
  "results": [
    {
      "id": 1,
      "title": "First Article",
      "content": "Content here",
      "author_id": 1
    },
    {
      "id": 2,
      "title": "Second Article",
      "content": "More content",
      "author_id": 1
    }
  ]
}
```

### Successful Create/Update Response
```json
{
  "success": true,
  "id": 1,
  "object": {
    "id": 1,
    "title": "New Article",
    "content": "Content",
    "author_id": 1
  }
}
```

### Error Response
```json
{
  "error": "Article not found"
}
```

## Configuration with Claude Desktop

To use this server with Claude Desktop, add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "django-admin": {
      "command": "python",
      "args": ["/path/to/your/project/manage.py", "run_mcp_server"],
      "env": {
        "DJANGO_SETTINGS_MODULE": "your_project.settings"
      }
    }
  }
}
```

## Security Considerations

1. **Authentication**: This package does not include authentication. Consider adding authentication layers if exposing to untrusted clients.

2. **Permissions**: The MCP server has full access to registered models. Use Django's permission system in your admin classes to restrict access.

3. **Data Validation**: Django's model validation is applied during create/update operations.

4. **SQL Injection**: Django's ORM provides protection against SQL injection attacks.

## Advanced Usage

### Custom Querysets

Override `get_queryset` in your ModelAdmin to control which objects are accessible:

```python
@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(is_published=True)
```

### Field Filtering

Use Django's admin options to control which fields are exposed:

```python
@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    exclude = ['internal_notes']
    readonly_fields = ['created_at', 'updated_at']
```

## Troubleshooting

### Models Not Registered

If models aren't showing up, ensure:
1. The admin class inherits from both `MCPAdminMixin` and `admin.ModelAdmin`
2. The mixin comes first in the inheritance order: `MCPAdminMixin, admin.ModelAdmin`
3. Django has loaded all apps before starting the MCP server

### Tool Calls Failing

If tool calls fail:
1. Check the error message in the response
2. Verify field names match your model definition
3. Ensure required fields are provided
4. Check Django logs for database errors

### Server Not Starting

If the server won't start:
1. Verify Django settings are correct
2. Check that all migrations are applied
3. Ensure the MCP package is installed correctly
