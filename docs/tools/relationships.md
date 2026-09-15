# Relationships

Django Admin MCP provides tools for traversing relationships, viewing change history, and autocomplete functionality.

## related_\<model\>

Fetches related objects through foreign key, many-to-many, or reverse relations.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer or string | Instance primary key | Yes |
| `relation` | string | Relation name to traverse | Yes |
| `limit` | integer | Maximum results (many relations) | No (default: 100) |
| `offset` | integer | Results to skip (many relations) | No (default: 0) |

### Examples

**Get article's author (ForeignKey):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "related_article",
    "arguments": {
      "id": 42,
      "relation": "author"
    }
  }
}
```

Single relations (FK, OneToOne) return a `type: "single"` wrapper — never a bare object. Nested foreign keys inside `result` serialize as primary keys:

```json
{
  "relation": "author",
  "type": "single",
  "result": {
    "id": 5,
    "name": "Jane Doe",
    "email": "jane@example.com",
    "bio": "Tech writer and Django enthusiast"
  }
}
```

**Get article's categories (ManyToMany):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "related_article",
    "arguments": {
      "id": 42,
      "relation": "categories"
    }
  }
}
```

Many relations (ManyToMany, reverse FK) return a `type: "many"` wrapper:

```json
{
  "relation": "categories",
  "type": "many",
  "count": 3,
  "total_count": 3,
  "results": [
    {"id": 1, "name": "Python"},
    {"id": 2, "name": "Django"},
    {"id": 3, "name": "Web Development"}
  ]
}
```

**Get article's comments (Reverse FK):**

```json
{
  "method": "tools/call",
  "params": {
    "name": "related_article",
    "arguments": {
      "id": 42,
      "relation": "comments",
      "limit": 10
    }
  }
}
```

Response:

```json
{
  "relation": "comments",
  "type": "many",
  "count": 2,
  "total_count": 8,
  "results": [
    {"id": 1, "article": 42, "text": "Great article!", "created_at": "2024-01-15T10:30:00Z"},
    {"id": 2, "article": 42, "text": "Very helpful", "created_at": "2024-01-15T11:00:00Z"}
  ]
}
```

Only actual relations (forward FK/O2O/M2M fields and reverse accessors) can be fetched. Passing a plain field, property, or method name returns an error:

```json
{
  "error": "Relation 'title' not found on model"
}
```

### Discovering Relations

Use `describe_*` to find available relations — `relationships` is a flat list of field-metadata dicts (reverse relations get `"type": "Unknown"`):

```json
{
  "relationships": [
    {"name": "author", "type": "ForeignKey", "related_model": "author", "related_app": "blog"},
    {"name": "categories", "type": "ManyToManyField", "related_model": "category", "related_app": "blog"},
    {"name": "comment", "type": "Unknown", "related_model": "comment", "related_app": "blog"}
  ]
}
```

!!! warning "No admin-queryset scoping or related-model permission checks"
    `related_*` and `autocomplete_*` query `model.objects` directly — `ModelAdmin.get_queryset()` scoping is not applied. Only the **parent** model's `view` permission is checked; the related model's permissions are not. Rows hidden from `list_*` by a scoped admin queryset can still be reached through a relation.

---

## history_\<model\>

Views the Django admin change history (LogEntry records) for an instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer or string | Instance primary key | Yes |
| `limit` | integer | Maximum results | No (default: 50) |

`limit` is applied as a plain queryset slice; it is not capped by `MCP_MAX_LIST_LIMIT`.

### Example

```json
{
  "method": "tools/call",
  "params": {
    "name": "history_article",
    "arguments": {
      "id": 42,
      "limit": 10
    }
  }
}
```

### Response

```json
{
  "model": "article",
  "object_id": 42,
  "current_repr": "Getting Started with Django",
  "count": 2,
  "history": [
    {
      "action": "changed",
      "action_flag": 2,
      "action_time": "2024-01-15T14:30:00Z",
      "user": "admin",
      "user_id": 1,
      "change_message": "Changed via MCP: {\"title\": \"Getting Started with Django\"}",
      "object_repr": "Getting Started with Django"
    },
    {
      "action": "created",
      "action_flag": 1,
      "action_time": "2024-01-15T10:00:00Z",
      "user": "admin",
      "user_id": 1,
      "change_message": "Created via MCP: {\"title\": \"Getting Started with Django\"}",
      "object_repr": "Getting Started with Django"
    }
  ]
}
```

### Action Types

| Action | Description |
|--------|-------------|
| `created` | Record was created |
| `changed` | Record was modified |
| `deleted` | Record was deleted |

### History Requirements

History is recorded when:

- Changes are made through Django admin
- Changes are made through Django Admin MCP with an authenticated user
- `LogEntry` is manually created

MCP writes `LogEntry` rows only when `request.user` is set and authenticated — token-less or anonymous requests are not logged. In MCP change messages, values of sensitive-looking keys (containing `password`, `token`, `secret`, `api_key`, `auth`, or `credential`) are redacted to `***REDACTED***`, and the serialized data is truncated to 500 characters.

!!! note "History Availability"
    History is only available for changes made through Django admin or MCP. Direct database modifications are not tracked.

---

## autocomplete_\<model\>

Provides search suggestions for foreign key and many-to-many fields.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `term` | string | Search term | No (default: `""`, returns the first N objects unfiltered) |
| `limit` | integer | Maximum results | No (default: 10) |

### Example

```json
{
  "method": "tools/call",
  "params": {
    "name": "autocomplete_author",
    "arguments": {
      "term": "jane"
    }
  }
}
```

### Response

```json
{
  "model": "author",
  "term": "jane",
  "count": 2,
  "results": [
    {"id": 5, "text": "Jane Doe"},
    {"id": 12, "text": "Jane Smith"}
  ]
}
```

### Requirements

`search_fields` is **not** required. When the admin defines it, those fields are searched:

```python title="admin.py"
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['name', 'email']
```

Without `search_fields`, the handler falls back to searching the first 3 `CharField`/`TextField` fields on the model. Calling without a `term` returns the first `limit` objects unfiltered.

### Use Cases

**Finding authors when creating articles:**

```
1. autocomplete_author(term="john") -> [{"id": 3, "text": "John Doe"}]
2. create_article(data={"title": "...", "author_id": 3})
```

**Finding categories:**

```
1. autocomplete_category(term="python") -> [{"id": 1, "text": "Python"}]
2. update_article(id=42, data={"categories": [1, 2, 3]})
```

---

## Traversing Deep Relationships

For complex queries, chain multiple calls:

**Get all comments by a specific author's articles:**

```
1. list_article(filters={"author": 5}) -> articles [1, 2, 3]
2. related_article(id=1, relation="comments") -> comments
3. related_article(id=2, relation="comments") -> more comments
...
```

**Get author's articles and their categories:**

```
1. related_author(id=5, relation="articles") -> articles
2. For each article: related_article(id=X, relation="categories")
```

---

## Permission Requirements

| Tool | Required Permission |
|------|---------------------|
| `related_*` | `view_<model>` (parent model only) |
| `history_*` | `view_<model>` |
| `autocomplete_*` | `view_<model>` |

---

## Error Handling

All errors are returned with HTTP 200 as JSON inside the JSON-RPC `result.content[0].text` — there is no `isError` flag.

### Unknown Relation

```json
{
  "error": "Relation 'nonexistent' not found on model"
}
```

### Instance Not Found

```json
{
  "error": "article not found"
}
```

The requested id is not included in the message.

### Missing Parameters

```json
{
  "error": "id parameter is required"
}
```

```json
{
  "error": "relation parameter is required"
}
```

## Next Steps

- [CRUD Operations](crud.md) — Basic data operations
- [Examples](../examples/conversations.md) — See real conversations
