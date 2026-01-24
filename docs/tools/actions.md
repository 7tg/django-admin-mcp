# Admin Actions

Django Admin MCP exposes Django admin actions through the MCP protocol, enabling execution of custom actions and bulk operations.

## actions_\<model\>

Lists all available admin actions for a model.

### Parameters

None required.

### Example

```json
{
  "method": "tools/call",
  "name": "actions_article",
  "arguments": {}
}
```

### Response

```json
{
  "actions": [
    {
      "name": "delete_selected",
      "description": "Delete selected articles"
    },
    {
      "name": "mark_as_published",
      "description": "Mark selected articles as published"
    },
    {
      "name": "mark_as_draft",
      "description": "Mark selected articles as draft"
    },
    {
      "name": "export_to_csv",
      "description": "Export selected articles to CSV"
    }
  ]
}
```

---

## action_\<model\>

Executes an admin action on selected records.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `action` | string | Action name from `actions_*` | Yes |
| `ids` | array | List of record IDs to act on | Yes |

### Examples

**Mark articles as published:**

```json
{
  "method": "tools/call",
  "name": "action_article",
  "arguments": {
    "action": "mark_as_published",
    "ids": [1, 2, 3, 4, 5]
  }
}
```

**Delete selected:**

```json
{
  "method": "tools/call",
  "name": "action_article",
  "arguments": {
    "action": "delete_selected",
    "ids": [10, 11, 12]
  }
}
```

### Response

```json
{
  "message": "Action 'mark_as_published' executed on 5 articles"
}
```

### Defining Custom Actions

In your Django admin:

```python title="admin.py"
@admin.action(description='Mark as published')
def mark_as_published(modeladmin, request, queryset):
    count = queryset.update(published=True)
    return f"Marked {count} articles as published"

@admin.action(description='Mark as draft')
def mark_as_draft(modeladmin, request, queryset):
    count = queryset.update(published=False)
    return f"Marked {count} articles as draft"

@admin.action(description='Feature selected articles')
def feature_articles(modeladmin, request, queryset):
    queryset.update(featured=True, featured_at=timezone.now())

class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    actions = [mark_as_published, mark_as_draft, feature_articles]
```

---

## bulk_\<model\>

Performs bulk operations on multiple records.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `operation` | string | One of: `create`, `update`, `delete` | Yes |
| `ids` | array | Record IDs (for update/delete) | Varies |
| `data` | object/array | Data for create/update | Varies |

### Bulk Create

Create multiple records at once:

```json
{
  "method": "tools/call",
  "name": "bulk_article",
  "arguments": {
    "operation": "create",
    "data": [
      {"title": "Article 1", "author_id": 5},
      {"title": "Article 2", "author_id": 5},
      {"title": "Article 3", "author_id": 5}
    ]
  }
}
```

Response:

```json
{
  "created": 3,
  "ids": [44, 45, 46]
}
```

### Bulk Update

Update multiple records with the same values:

```json
{
  "method": "tools/call",
  "name": "bulk_article",
  "arguments": {
    "operation": "update",
    "ids": [10, 11, 12, 13, 14, 15],
    "data": {
      "status": "archived",
      "archived_at": "2024-01-15T00:00:00Z"
    }
  }
}
```

Response:

```json
{
  "updated": 6
}
```

### Bulk Delete

Delete multiple records:

```json
{
  "method": "tools/call",
  "name": "bulk_article",
  "arguments": {
    "operation": "delete",
    "ids": [100, 101, 102]
  }
}
```

Response:

```json
{
  "deleted": 3
}
```

---

## Permission Requirements

| Operation | Required Permission |
|-----------|---------------------|
| `actions_*` (list) | `view_<model>` |
| `action_*` (execute) | Varies by action |
| `bulk_*` create | `add_<model>` |
| `bulk_*` update | `change_<model>` |
| `bulk_*` delete | `delete_<model>` |

### Action-Specific Permissions

Actions can require additional permissions. The default Django `delete_selected` action requires `delete_<model>` permission.

For custom permissions on actions:

```python title="admin.py"
@admin.action(description='Feature selected articles')
def feature_articles(modeladmin, request, queryset):
    if not request.user.has_perm('blog.feature_article'):
        raise PermissionDenied("Cannot feature articles")
    queryset.update(featured=True)
```

---

## Error Handling

### Unknown Action

```json
{
  "content": [{"type": "text", "text": "Unknown action: nonexistent_action"}],
  "isError": true
}
```

### Empty Selection

```json
{
  "content": [{"type": "text", "text": "No records selected for action"}],
  "isError": true
}
```

### Permission Denied

```json
{
  "content": [{"type": "text", "text": "Permission denied for action: delete_selected"}],
  "isError": true
}
```

### Partial Failure (Bulk Create)

```json
{
  "error": "Bulk create failed",
  "details": {
    "created": 2,
    "failed": 1,
    "errors": [
      {"index": 2, "error": {"title": ["This field is required."]}}
    ]
  }
}
```

---

## Best Practices

### Use Actions for Business Logic

Actions should encapsulate business logic:

```python
@admin.action(description='Publish and notify subscribers')
def publish_and_notify(modeladmin, request, queryset):
    # Update status
    queryset.update(published=True, published_at=timezone.now())

    # Send notifications
    for article in queryset:
        send_publication_notification(article)

    return f"Published {queryset.count()} articles and sent notifications"
```

### Prefer Bulk Operations for Data Changes

For simple data changes, use `bulk_*` instead of actions:

```
# Instead of a custom "archive all" action:
bulk_article(operation="update", ids=[...], data={"status": "archived"})
```

### Validate Before Bulk Operations

Use `list_*` to verify records before bulk operations:

```
1. list_article(filters={"status": "draft", "created_at__lt": "2023-01-01"})
2. Review the results
3. bulk_article(operation="delete", ids=[...])
```

## Next Steps

- [Model Introspection](introspection.md) - Discover model schemas
- [Relationships](relationships.md) - Access related data
