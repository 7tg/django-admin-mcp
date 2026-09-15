# Tools Overview

Django Admin MCP generates tools dynamically based on your exposed models. This page provides an overview of all available tools.

## Tool Categories

Tools are organized into four categories:

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

- `list_article` — List articles
- `get_article` — Get a single article
- `create_article` — Create an article
- `update_article` — Update an article
- `delete_article` — Delete an article

## Global Tools

One tool is available regardless of model configuration:

### find_models

Discovers all registered models and their available tools. Results are filtered by `has_module_permission()` first (hidden modules are excluded entirely, mirroring the Django admin index), then by the token's `view` permission.

```json
{
  "method": "tools/call",
  "params": {
    "name": "find_models",
    "arguments": {}
  }
}
```

Optional parameter:

- `query` (string) — Filter models by name

Response:

```json
{
  "count": 2,
  "models": [
    {
      "model_name": "article",
      "verbose_name": "article",
      "verbose_name_plural": "articles",
      "app_label": "blog",
      "tools_exposed": true
    },
    {
      "model_name": "author",
      "verbose_name": "author",
      "verbose_name_plural": "authors",
      "app_label": "blog",
      "tools_exposed": false
    }
  ]
}
```

`tools_exposed` reflects the admin's `mcp_expose` flag: models registered with an `MCPAdminMixin` admin but without `mcp_expose = True` are discoverable here yet report `tools_exposed: false`, because no per-model tools are generated for them.

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
| `action_<model>` | change (plus delete for `delete_selected`) | Execute an admin action |
| `bulk_<model>` | add / change / delete per sub-operation | Bulk create/update/delete |

Custom actions that render an intermediate HTML page trigger a two-step confirmation flow: the first call returns `requires_confirmation: true`, and re-calling with `confirm: true` (plus optional `confirmation_data`) executes the action. Actions that return file downloads (`HttpResponse`/`StreamingHttpResponse`) are converted into a structured file payload. See [Admin Actions](actions.md#confirmation-flow) and [file downloads](actions.md#file-downloads) for details.

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

Each tool has a JSON Schema defining its input parameters. The generated `list_*` description advertises the supported filter lookups and the model's fields:

```json
{
  "name": "list_article",
  "description": "List article instances with filtering, searching, ordering, and pagination.\n\nFilter lookups: field (exact), field__contains, field__icontains, field__gt, field__gte, field__lt, field__lte, field__in, field__isnull\n\nAvailable fields:\n  - id (AutoField)\n  - title (CharField) [required]\n  - author (ForeignKey) [required]\n  - published (BooleanField)",
  "inputSchema": {
    "type": "object",
    "properties": {
      "limit": {
        "type": "integer",
        "description": "Maximum number of items to return (default: 100)",
        "default": 100
      },
      "offset": {
        "type": "integer",
        "description": "Number of items to skip (default: 0)",
        "default": 0
      },
      "filters": {
        "type": "object",
        "description": "Filter criteria. Keys are field names with optional lookups (e.g., {'status': 'published', 'created_at__gte': '2024-01-01'})"
      },
      "search": {
        "type": "string",
        "description": "Search term to match against searchable fields"
      },
      "order_by": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Fields to order by. Prefix with '-' for descending (e.g., ['-created_at', 'title'])"
      }
    }
  }
}
```

## Response Format

The endpoint speaks JSON-RPC 2.0. A tool call request looks like:

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

Responses wrap the tool output as a JSON string inside `result.content[0].text`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"count\": 1, \"total_count\": 42, \"results\": [...]}"
      }
    ]
  }
}
```

There is no `isError` flag. Tool-level errors (permission denied, not found, validation failures) are returned with HTTP 200 as JSON inside `result.content[0].text`:

```json
{
  "error": "Permission denied: cannot add article",
  "code": "permission_denied"
}
```

## Permission Requirements

Each tool requires specific Django permissions, checked against the API token's effective permissions (its assigned permissions and groups, capped by the linked user's permissions):

| Operation | Permission Pattern |
|-----------|-------------------|
| Read operations (`list_*`, `get_*`, `describe_*`, `actions_*`, `related_*`, `history_*`, `autocomplete_*`) | `<app>.view_<model>` |
| Create | `<app>.add_<model>` |
| Update | `<app>.change_<model>` |
| Delete | `<app>.delete_<model>` |
| Actions (`action_*`) | `<app>.change_<model>`, plus `<app>.delete_<model>` when the action is `delete_selected` |
| Bulk (`bulk_*`) | `<app>.add_<model>` / `<app>.change_<model>` / `<app>.delete_<model>` matching the sub-operation |

## Next Steps

- [CRUD Operations](crud.md) — Basic data operations
- [Admin Actions](actions.md) — Actions and bulk operations
- [Model Introspection](introspection.md) — Schema discovery
- [Relationships](relationships.md) — Related data access
