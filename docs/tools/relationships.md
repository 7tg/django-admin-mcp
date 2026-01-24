# Relationships

Django Admin MCP provides tools for traversing relationships, viewing change history, and autocomplete functionality.

## related_\<model\>

Fetches related objects through foreign key, many-to-many, or reverse relations.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `relation` | string | Relation name to traverse | Yes |
| `limit` | integer | Maximum results | No (default: 25) |
| `offset` | integer | Results to skip | No (default: 0) |

### Examples

**Get article's author (ForeignKey):**

```json
{
  "method": "tools/call",
  "name": "related_article",
  "arguments": {
    "id": 42,
    "relation": "author"
  }
}
```

Response:

```json
{
  "id": 5,
  "name": "Jane Doe",
  "email": "jane@example.com",
  "bio": "Tech writer and Django enthusiast"
}
```

**Get article's categories (ManyToMany):**

```json
{
  "method": "tools/call",
  "name": "related_article",
  "arguments": {
    "id": 42,
    "relation": "categories"
  }
}
```

Response:

```json
{
  "results": [
    {"id": 1, "name": "Python"},
    {"id": 2, "name": "Django"},
    {"id": 3, "name": "Web Development"}
  ],
  "count": 3,
  "total": 3
}
```

**Get article's comments (Reverse FK):**

```json
{
  "method": "tools/call",
  "name": "related_article",
  "arguments": {
    "id": 42,
    "relation": "comments",
    "limit": 10
  }
}
```

Response:

```json
{
  "results": [
    {"id": 1, "text": "Great article!", "created_at": "2024-01-15T10:30:00Z"},
    {"id": 2, "text": "Very helpful", "created_at": "2024-01-15T11:00:00Z"}
  ],
  "count": 2,
  "total": 8
}
```

### Discovering Relations

Use `describe_*` to find available relations:

```json
{
  "relations": {
    "forward": [
      {"name": "author", "type": "ForeignKey"},
      {"name": "categories", "type": "ManyToManyField"}
    ],
    "reverse": [
      {"name": "comments", "type": "reverse_fk"}
    ]
  }
}
```

---

## history_\<model\>

Views the Django admin change history (LogEntry records) for an instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `limit` | integer | Maximum results | No (default: 25) |

### Example

```json
{
  "method": "tools/call",
  "name": "history_article",
  "arguments": {
    "id": 42,
    "limit": 10
  }
}
```

### Response

```json
{
  "entries": [
    {
      "action_time": "2024-01-15T14:30:00Z",
      "user": "admin",
      "action": "change",
      "message": "Changed title and content."
    },
    {
      "action_time": "2024-01-15T10:00:00Z",
      "user": "admin",
      "action": "add",
      "message": "Added article."
    }
  ],
  "count": 2,
  "total": 2
}
```

### Action Types

| Action | Description |
|--------|-------------|
| `add` | Record was created |
| `change` | Record was modified |
| `delete` | Record was deleted |

### History Requirements

History is recorded when:

- Changes are made through Django admin
- Changes are made through Django Admin MCP
- `LogEntry` is manually created

!!! note "History Availability"
    History is only available for changes made through Django admin or MCP. Direct database modifications are not tracked.

---

## autocomplete_\<model\>

Provides search suggestions for foreign key and many-to-many fields.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `search` | string | Search query | Yes |
| `limit` | integer | Maximum results | No (default: 10) |

### Example

```json
{
  "method": "tools/call",
  "name": "autocomplete_author",
  "arguments": {
    "search": "jane"
  }
}
```

### Response

```json
{
  "results": [
    {"id": 5, "text": "Jane Doe"},
    {"id": 12, "text": "Jane Smith"}
  ],
  "count": 2
}
```

### Requirements

Autocomplete requires `search_fields` to be defined:

```python title="admin.py"
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['name', 'email']  # Required for autocomplete
```

### Use Cases

**Finding authors when creating articles:**

```
1. autocomplete_author(search="john") -> [{"id": 3, "text": "John Doe"}]
2. create_article(data={"title": "...", "author_id": 3})
```

**Finding categories:**

```
1. autocomplete_category(search="python") -> [{"id": 1, "text": "Python"}]
2. update_article(id=42, data={"categories": [1, 2, 3]})
```

---

## Traversing Deep Relationships

For complex queries, chain multiple calls:

**Get all comments by a specific author's articles:**

```
1. list_article(filters={"author_id": 5}) -> articles [1, 2, 3]
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
| `related_*` | `view_<model>` |
| `history_*` | `view_<model>` |
| `autocomplete_*` | `view_<model>` |

---

## Error Handling

### Unknown Relation

```json
{
  "content": [{"type": "text", "text": "Unknown relation: nonexistent"}],
  "isError": true
}
```

### Instance Not Found

```json
{
  "content": [{"type": "text", "text": "Article with id 999 not found"}],
  "isError": true
}
```

### No Search Fields

```json
{
  "content": [{"type": "text", "text": "Autocomplete not available: no search_fields defined"}],
  "isError": true
}
```

## Next Steps

- [CRUD Operations](crud.md) - Basic data operations
- [Examples](../examples/conversations.md) - See real conversations
