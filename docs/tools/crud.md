# CRUD Operations

Django Admin MCP provides full CRUD (Create, Read, Update, Delete) operations for exposed models.

## list_\<model\>

Lists model instances with support for pagination, filtering, search, and ordering.

### Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `limit` | integer | Maximum results to return | 25 |
| `offset` | integer | Number of results to skip | 0 |
| `search` | string | Search query (uses `search_fields`) | - |
| `ordering` | string | Field to order by | Model default |
| `filters` | object | Field filters | - |

### Examples

**Basic listing:**

```json
{
  "method": "tools/call",
  "name": "list_article",
  "arguments": {
    "limit": 10
  }
}
```

**With pagination:**

```json
{
  "method": "tools/call",
  "name": "list_article",
  "arguments": {
    "limit": 10,
    "offset": 20
  }
}
```

**With search:**

```json
{
  "method": "tools/call",
  "name": "list_article",
  "arguments": {
    "search": "django tutorial"
  }
}
```

**With ordering:**

```json
{
  "method": "tools/call",
  "name": "list_article",
  "arguments": {
    "ordering": "-created_at"
  }
}
```

**With filters:**

```json
{
  "method": "tools/call",
  "name": "list_article",
  "arguments": {
    "filters": {
      "published": true,
      "author_id": 5
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
      "published": true,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "count": 1,
  "total": 42
}
```

| Field | Description |
|-------|-------------|
| `results` | Array of model instances |
| `count` | Number of results in this page |
| `total` | Total number of matching records |

---

## get_\<model\>

Retrieves a single model instance by ID.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `include_inlines` | boolean | Include inline model data | No |

### Examples

**Basic get:**

```json
{
  "method": "tools/call",
  "name": "get_article",
  "arguments": {
    "id": 42
  }
}
```

**With inlines:**

```json
{
  "method": "tools/call",
  "name": "get_article",
  "arguments": {
    "id": 42,
    "include_inlines": true
  }
}
```

### Response

```json
{
  "id": 42,
  "title": "Getting Started with Django",
  "content": "This tutorial covers...",
  "author": {
    "id": 5,
    "name": "Jane Doe"
  },
  "published": true,
  "created_at": "2024-01-15T10:00:00Z",
  "comments": [
    {"id": 1, "text": "Great article!"},
    {"id": 2, "text": "Very helpful"}
  ]
}
```

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
  "name": "create_article",
  "arguments": {
    "data": {
      "title": "New Article",
      "content": "Article content here...",
      "author_id": 5
    }
  }
}
```

**With related fields:**

```json
{
  "method": "tools/call",
  "name": "create_article",
  "arguments": {
    "data": {
      "title": "New Article",
      "author_id": 5,
      "categories": [1, 2, 3]
    }
  }
}
```

### Response

```json
{
  "id": 43,
  "message": "Article created successfully"
}
```

### Validation Errors

If validation fails:

```json
{
  "error": "Validation failed",
  "errors": {
    "title": ["This field is required."],
    "author_id": ["Select a valid choice."]
  }
}
```

---

## update_\<model\>

Updates an existing model instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `data` | object | Field values to update | Yes |

### Examples

**Partial update:**

```json
{
  "method": "tools/call",
  "name": "update_article",
  "arguments": {
    "id": 42,
    "data": {
      "title": "Updated Title"
    }
  }
}
```

**Full update:**

```json
{
  "method": "tools/call",
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
```

### Response

```json
{
  "message": "Article updated successfully"
}
```

### Readonly Fields

Attempts to update readonly fields are silently ignored:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    readonly_fields = ['created_at', 'view_count']
```

```json
{
  "id": 42,
  "data": {
    "created_at": "2020-01-01T00:00:00Z",
    "title": "New Title"
  }
}
```

Only `title` will be updated; `created_at` is ignored.

---

## delete_\<model\>

Deletes a model instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |

### Example

```json
{
  "method": "tools/call",
  "name": "delete_article",
  "arguments": {
    "id": 42
  }
}
```

### Response

```json
{
  "message": "Article deleted successfully"
}
```

!!! warning "Cascade Deletes"
    Deletion follows Django's cascade rules. Related objects with `on_delete=CASCADE` will also be deleted.

---

## Foreign Key Handling

Foreign keys can be specified in two ways:

**By ID (recommended):**

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

Both are normalized internally to use the correct database column.

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

### Not Found

```json
{
  "content": [{"type": "text", "text": "Article with id 999 not found"}],
  "isError": true
}
```

### Permission Denied

```json
{
  "content": [{"type": "text", "text": "Permission denied: blog.add_article"}],
  "isError": true
}
```

### Validation Error

```json
{
  "content": [{"type": "text", "text": "{\"error\": \"Validation failed\", \"errors\": {...}}"}],
  "isError": true
}
```

## Next Steps

- [Admin Actions](actions.md) - Execute admin actions
- [Model Introspection](introspection.md) - Discover model schemas
