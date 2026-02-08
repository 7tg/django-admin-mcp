# 🔗 Relationships

Django Admin MCP provides tools for traversing relationships, viewing change history, and autocomplete functionality.

## 🔗 related_\<model\>

Fetches related objects through foreign key, many-to-many, or reverse relations.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `relation` | string | Relation name to traverse | Yes |
| `limit` | integer | Maximum results | No (default: 100) |
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
  "total_count": 3
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
  "total_count": 8
}
```

### 🔍 Discovering Relations

Use `describe_*` to find available relations:

```json
{
  "relationships": {
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

## 📜 history_\<model\>

Views the Django admin change history (LogEntry records) for an instance.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `id` | integer | Instance primary key | Yes |
| `limit` | integer | Maximum results | No (default: 50) |

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
      "change_message": "Changed title and content.",
      "object_repr": "Getting Started with Django"
    },
    {
      "action": "created",
      "action_flag": 1,
      "action_time": "2024-01-15T10:00:00Z",
      "user": "admin",
      "user_id": 1,
      "change_message": "Created via MCP",
      "object_repr": "Getting Started with Django"
    }
  ]
}
```

### 🏷️ Action Types

| Action | Description |
|--------|-------------|
| `created` | Record was created |
| `changed` | Record was modified |
| `deleted` | Record was deleted |

### 📋 History Requirements

History is recorded when:

- Changes are made through Django admin
- Changes are made through Django Admin MCP
- `LogEntry` is manually created

!!! note "History Availability"
    History is only available for changes made through Django admin or MCP. Direct database modifications are not tracked.

---

## 🔎 autocomplete_\<model\>

Provides search suggestions for foreign key and many-to-many fields.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `term` | string | Search term | Yes |
| `limit` | integer | Maximum results | No (default: 10) |

### Example

```json
{
  "method": "tools/call",
  "name": "autocomplete_author",
  "arguments": {
    "term": "jane"
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

### ⚙️ Requirements

Autocomplete requires `search_fields` to be defined:

```python title="admin.py"
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    search_fields = ['name', 'email']  # Required for autocomplete
```

### 💡 Use Cases

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

## 🔄 Traversing Deep Relationships

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

## 🔒 Permission Requirements

| Tool | Required Permission |
|------|---------------------|
| `related_*` | `view_<model>` |
| `history_*` | `view_<model>` |
| `autocomplete_*` | `view_<model>` |

---

## ❌ Error Handling

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

## 🔗 Next Steps

- [CRUD Operations](crud.md) — Basic data operations
- [Examples](../examples/conversations.md) — See real conversations
