# CRUD Operations

Django Admin MCP provides full CRUD (Create, Read, Update, Delete) operations for exposed models.

## list_\<model\>

Lists model instances with support for pagination, filtering, search, and ordering.

### Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Maximum results to return (must be a non-negative integer) | 100 |
| `offset` | integer | Number of results to skip (must be a non-negative integer) | 0 |
| `search` | string | Search query (uses `search_fields`) | — |
| `order_by` | array | Fields to order by (prefix with `-` for descending) | Model default |
| `filters` | object | Field filters | — |

`limit` is capped server-side at `MCP_MAX_LIST_LIMIT` (default 1000) via `min(limit, MCP_MAX_LIST_LIMIT)`. Passing a negative value or a non-integer returns `{"error": "limit must be a non-negative integer"}` (and the equivalent for `offset`).

`order_by` accepts direct field names only, with an optional `-` prefix for descending order. Invalid entries are silently dropped.

### Supported filter lookups

Only the following lookups are allowed in `filters`:

| Lookup | Example key | Meaning |
|--------|-------------|---------|
| (none) / `exact` | `"published"` or `"published__exact"` | Exact match |
| `contains` | `"title__contains"` | Case-sensitive substring |
| `icontains` | `"title__icontains"` | Case-insensitive substring |
| `gt` / `gte` | `"created_at__gte"` | Greater than (or equal) |
| `lt` / `lte` | `"created_at__lt"` | Less than (or equal) |
| `in` | `"status__in"` | Value in a list |
| `isnull` | `"author__isnull"` | Null check |

Filters apply to **direct model fields only**.

!!! warning "Invalid filters are silently skipped"
    Any filter with an unknown field, a disallowed lookup (`regex`, `startswith`, `__year`, ...), or relation traversal (e.g. `author__email`) is **silently skipped** — the query runs without that filter, so you may get more results than expected instead of an error.

Filters use **model field names**, not database column names: `{"author": 5}` filters by the FK, while `{"author_id": 5}` is silently dropped (the `_id` suffix works in `create_*` data but not in filters).

### Examples

**Basic listing:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {
      "limit": 10
    }
  }
}
```

**With pagination:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {
      "limit": 10,
      "offset": 20
    }
  }
}
```

**With search:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {
      "search": "django tutorial"
    }
  }
}
```

**With ordering:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {
      "order_by": ["-created_at"]
    }
  }
}
```

**With filters:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "list_article",
    "arguments": {
      "filters": {
        "published": true,
        "author": 5
      }
    }
  }
}
```

### Response

```json
{
  "results": [
    {
      "id": 1,
      "title": "Getting Started with Django",
      "author": 5,
      "published": true,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "count": 1,
  "total_count": 42
}
```

| Field | Description |
|-------|-------------|
| `results` | Array of model instances |
| `count` | Number of results in this page |
| `total_count` | Total number of matching records |

---

## get_\<model\>

Retrieves a single model instance by ID.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer or string | Instance primary key | Yes |
| `include_inlines` | boolean | Include inline model data under `_inlines` | No |
| `include_related` | boolean | Include reverse relations under `_related` | No |

The schema accepts `id` as an integer or a string. `id=0` (or any falsy value) is rejected as missing: `{"error": "id parameter is required"}`.

### Examples

**Basic get:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "get_article",
    "arguments": {
      "id": 42
    }
  }
}
```

**With inlines:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "get_article",
    "arguments": {
      "id": 42,
      "include_inlines": true,
      "include_related": true
    }
  }
}
```

### Response

Foreign keys serialize as bare primary keys (`"author": 5`), never as nested objects. Many-to-many fields serialize as lists of primary keys.

```json
{
  "id": 42,
  "title": "Getting Started with Django",
  "content": "This tutorial covers...",
  "author": 5,
  "categories": [1, 2],
  "published": true,
  "created_at": "2024-01-15T10:00:00Z",
  "_inlines": {
    "comment": [
      {"id": 1, "article": 42, "text": "Great article!"},
      {"id": 2, "article": 42, "text": "Very helpful"}
    ]
  },
  "_related": {
    "comments": [
      {"id": 1, "article": 42, "text": "Great article!"},
      {"id": 2, "article": 42, "text": "Very helpful"}
    ]
  }
}
```

| Key | Description |
|-----|-------------|
| `_inlines` | Present with `include_inlines: true`. Maps each inline model name (from the admin's `inlines`) to a list of serialized instances. |
| `_related` | Present with `include_related: true` (and only if there is any data). Maps each reverse-relation accessor name to a list of serialized instances, hard-capped at **10 objects per relation**. Use `related_<model>` for full pagination. |

---

## create_\<model\>

Creates a new model instance with validation.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `data` | object | Field values for the new instance | Yes |

### Examples

**Basic create:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "create_article",
    "arguments": {
      "data": {
        "title": "New Article",
        "content": "Article content here...",
        "author_id": 5
      }
    }
  }
}
```

**With related fields:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "create_article",
    "arguments": {
      "data": {
        "title": "New Article",
        "author_id": 5,
        "categories": [1, 2, 3]
      }
    }
  }
}
```

### Response

```json
{
  "success": true,
  "id": 43,
  "object": {
    "id": 43,
    "title": "New Article",
    "content": "Article content here...",
    "author": 5,
    "published": false
  }
}
```

When a `ModelAdmin` is registered, creation goes through `ModelAdmin.save_model()` and a `LogEntry` is written for the addition.

### Validation Errors

If validation fails:

```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "validation_errors": {
    "errors": [
      {"field": "title", "messages": ["This field is required."]},
      {"field": "author", "messages": ["Select a valid choice. That choice is not one of the available choices."]}
    ],
    "error_count": 2,
    "fields_with_errors": ["title", "author"]
  }
}
```

---

## update_\<model\>

Updates an existing model instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer or string | Instance primary key | Yes |
| `data` | object | Field values to update | No (defaults to `{}`) |
| `inlines` | object | Inline add/update/delete operations | No |

Only `id` is required. `data` keys must be **model field names**: `author_id` is rejected with `{"error": "Invalid field: author_id"}` (unlike `create_*`, which normalizes `_id` suffixes).

The `inlines` parameter maps inline model names to lists of operations:

```json
{
  "inlines": {
    "comment": [
      {"id": 1, "data": {"text": "Updated comment"}},
      {"data": {"text": "New comment"}},
      {"id": 2, "_delete": true}
    ]
  }
}
```

- `{"id": X, "data": {...}}` — update an existing inline object
- `{"data": {...}}` — add a new inline object (the FK to the parent is set automatically)
- `{"id": X, "_delete": true}` — delete an inline object

### Inline behavior

- Each operation is checked against the inline's own `add`/`change`/`delete` permission; denied items land in `errors` with `"code": "permission_denied"`.
- The inline's `min_num`/`max_num` are enforced on the resulting object count **before any item is applied**. A violation rejects that inline model's whole batch with an error carrying `"code": "max_num_exceeded"` or `"code": "min_num_violated"`.
- The success response includes an `inlines` key with `created`, `updated`, `deleted`, and `errors` lists.

### Examples

**Partial update:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "update_article",
    "arguments": {
      "id": 42,
      "data": {
        "title": "Updated Title"
      }
    }
  }
}
```

**Full update:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "update_article",
    "arguments": {
      "id": 42,
      "data": {
        "title": "Updated Title",
        "content": "Updated content...",
        "published": true
      }
    }
  }
}
```

### Response

```json
{
  "success": true,
  "object": {
    "id": 42,
    "title": "Updated Title",
    "content": "Updated content...",
    "author": 5,
    "published": true
  }
}
```

With inline operations, the response also contains:

```json
{
  "success": true,
  "object": {"id": 42, "title": "Updated Title"},
  "inlines": {
    "created": [{"model": "comment", "id": 7}],
    "updated": [{"model": "comment", "id": 1}],
    "deleted": [{"model": "comment", "id": 2}],
    "errors": []
  }
}
```

When a `ModelAdmin` is registered, the update goes through `ModelAdmin.save_model()` and a `LogEntry` is written for the change.

### Readonly Fields

Attempts to update readonly fields return an error:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    readonly_fields = ['created_at', 'view_count']
```

```json
{
  "error": "Cannot update readonly fields: created_at",
  "readonly_fields": ["created_at"]
}
```

---

## delete_\<model\>

Deletes a model instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer or string | Instance primary key | Yes |

### Example

```json
{
  "method": "tools/call",
  "params": {
    "name": "delete_article",
    "arguments": {
      "id": 42
    }
  }
}
```

### Response

```json
{
  "success": true,
  "message": "article deleted successfully"
}
```

When a `ModelAdmin` is registered, deletion routes through `ModelAdmin.delete_model()`, and a `LogEntry` is written before the deletion (so the audit trail retains the object's representation).

!!! warning "Cascade Deletes"
    Deletion follows Django's cascade rules. Related objects with `on_delete=CASCADE` will also be deleted.

---

## Foreign Key Handling

In `create_*` data, foreign keys can be specified in two ways:

**By ID (`_id` suffix):**

```json
{
  "author_id": 5
}
```

**By field name:**

```json
{
  "author": 5
}
```

Both are normalized internally to the model field name.

`update_*` accepts **only model field names**: sending `author_id` returns `{"error": "Invalid field: author_id"}`. Filters in `list_*` also require model field names (`{"author": 5}`); `author_id` there is silently dropped.

---

## Many-to-Many Handling

Many-to-many relationships accept arrays of IDs:

```json
{
  "categories": [1, 2, 3],
  "tags": [10, 20, 30]
}
```

---

## Error Handling

All errors are returned with HTTP 200 as JSON inside the JSON-RPC `result.content[0].text` — there is no `isError` flag.

### Not Found

```json
{
  "error": "article not found"
}
```

The requested id is not included in the message.

### Permission Denied

```json
{
  "error": "Permission denied: cannot add article",
  "code": "permission_denied"
}
```

### Validation Error

```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "validation_errors": {
    "errors": [
      {"field": "title", "messages": ["This field is required."]}
    ],
    "error_count": 1,
    "fields_with_errors": ["title"]
  }
}
```

!!! note "Queryset scoping asymmetry"
    `list_*` and `get_*` use the admin queryset (`ModelAdmin.get_queryset()`, unless `mcp_use_admin_queryset = False`), but `update_*` and `delete_*` fetch the object with `model.objects.get(pk=...)`. A row hidden from the list by a scoped `get_queryset()` can therefore still be updated or deleted by id.

## Next Steps

- [Admin Actions](actions.md) — Execute admin actions
- [Model Introspection](introspection.md) — Discover model schemas
