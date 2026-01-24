# Tools Overview

Django Admin MCP generates tools dynamically based on your exposed models. This page provides an overview of all available tools.

## Tool Categories

Tools are organized into five categories:

| Category | Tools | Description |
|----------|-------|-------------|
| **CRUD** | `list_*`, `get_*`, `create_*`, `update_*`, `delete_*` | Basic data operations |
| **Actions** | `actions_*`, `action_*`, `bulk_*` | Admin actions and bulk operations |
| **Introspection** | `describe_*`, `find_models` | Model discovery and schema |
| **Relationships** | `related_*`, `history_*`, `autocomplete_*` | Related data and history |

## Tool Naming Convention

Tools follow a consistent naming pattern:

```
<operation>_<model_name>
```

For example, for an `Article` model:

- `list_article` - List articles
- `get_article` - Get a single article
- `create_article` - Create an article
- `update_article` - Update an article
- `delete_article` - Delete an article

## Global Tools

One tool is available regardless of model configuration:

### find_models

Discovers all registered models and their available tools.

```json
{
  "method": "tools/call",
  "name": "find_models",
  "arguments": {}
}
```

Optional parameter:

- `query` (string): Filter models by name

Response:

```json
{
  "models": [
    {
      "name": "article",
      "verbose_name": "Article",
      "app_label": "blog",
      "tools_exposed": true,
      "tools": ["list_article", "get_article", "create_article", ...]
    }
  ]
}
```

## Per-Model Tools

For each model with `mcp_expose = True`, 12 tools are generated:

### CRUD Operations (5 tools)

| Tool | Permission | Description |
|------|------------|-------------|
| `list_<model>` | view | List instances with pagination, filtering, search |
| `get_<model>` | view | Get single instance by ID |
| `create_<model>` | add | Create new instance |
| `update_<model>` | change | Update existing instance |
| `delete_<model>` | delete | Delete instance |

See [CRUD Operations](crud.md) for details.

### Admin Actions (3 tools)

| Tool | Permission | Description |
|------|------------|-------------|
| `actions_<model>` | view | List available admin actions |
| `action_<model>` | varies | Execute an admin action |
| `bulk_<model>` | varies | Bulk create/update/delete |

See [Admin Actions](actions.md) for details.

### Introspection (1 tool)

| Tool | Permission | Description |
|------|------------|-------------|
| `describe_<model>` | view | Get field definitions and metadata |

See [Model Introspection](introspection.md) for details.

### Relationships (3 tools)

| Tool | Permission | Description |
|------|------------|-------------|
| `related_<model>` | view | Get related objects |
| `history_<model>` | view | View change history |
| `autocomplete_<model>` | view | Search suggestions |

See [Relationships](relationships.md) for details.

## Tool Schema

Each tool has a JSON Schema defining its input parameters:

```json
{
  "name": "list_article",
  "description": "List all Article instances with pagination and filtering",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "description": "Maximum number of results",
        "default": 25
      },
      "offset": {
        "type": "integer",
        "description": "Number of results to skip",
        "default": 0
      },
      "search": {
        "type": "string",
        "description": "Search query"
      },
      "ordering": {
        "type": "string",
        "description": "Field to order by (prefix with - for descending)"
      },
      "filters": {
        "type": "object",
        "description": "Field filters"
      }
    }
  }
}
```

## Response Format

All tools return responses in MCP TextContent format:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{ ... JSON data ... }"
    }
  ]
}
```

Error responses include `isError: true`:

```json
{
  "content": [
    {
      "type": "text",
      "text": "Permission denied: blog.add_article"
    }
  ],
  "isError": true
}
```

## Permission Requirements

Each tool requires specific Django permissions:

| Operation | Permission Pattern |
|-----------|-------------------|
| Read operations | `<app>.view_<model>` |
| Create | `<app>.add_<model>` |
| Update | `<app>.change_<model>` |
| Delete | `<app>.delete_<model>` |
| Actions | Varies by action |

## Next Steps

- [CRUD Operations](crud.md) - Basic data operations
- [Admin Actions](actions.md) - Actions and bulk operations
- [Model Introspection](introspection.md) - Schema discovery
- [Relationships](relationships.md) - Related data access
