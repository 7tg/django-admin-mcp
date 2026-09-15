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
  "params": {
    "name": "actions_article",
    "arguments": {}
  }
}
```

### Response

```json
{
  "model": "article",
  "count": 4,
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

Executes an admin action on selected records. Requires `change` permission; `delete_selected` additionally requires `delete` permission.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `action` | string | Action name from `actions_*` | Yes |
| `ids` | array | List of record IDs to act on | Yes |
| `confirm` | boolean | Confirm and execute an action that reported `requires_confirmation` | No |
| `confirmation_data` | object | Extra form fields for the action's confirmation step | No |

The selected rows are scoped to the admin queryset: `get_admin_queryset(...).filter(pk__in=ids)`, so proxy filters, soft-delete scoping, etc. apply. Actions are resolved via `ModelAdmin.get_actions(request)`, which includes globally registered actions and honors each action's `allowed_permissions`.

### Examples

**Mark articles as published:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "action_article",
    "arguments": {
      "action": "mark_as_published",
      "ids": [1, 2, 3, 4, 5]
    }
  }
}
```

**Delete selected:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "action_article",
    "arguments": {
      "action": "delete_selected",
      "ids": [10, 11, 12]
    }
  }
}
```

### Response

On success, custom actions return:

```json
{
  "success": true,
  "action": "mark_as_published",
  "affected_count": 5,
  "message": "Executed mark_as_published on 5 objects",
  "result": "Marked 5 articles as published"
}
```

`result` is the serialized return value of the action function: `null` for actions returning `None`, a file payload for download responses (see [File downloads](#file-downloads)), and `str(value)` for anything else.

`delete_selected` is special-cased: it bypasses Django's HTML confirmation page and calls `queryset.delete()` directly, returning:

```json
{
  "success": true,
  "action": "delete_selected",
  "affected_count": 3,
  "message": "Deleted 3 articles"
}
```

!!! note "delete_selected caveats"
    `delete_selected` requires `delete` permission in addition to `change`, and does **not** write `LogEntry` rows for the deleted objects (unlike `delete_*`).

### Confirmation flow

Custom actions written for the admin changelist sometimes render an intermediate HTML confirmation page instead of executing directly. When that happens, the tool returns:

```json
{
  "success": false,
  "requires_confirmation": true,
  "action": "publish_and_notify",
  "message": "Action 'publish_and_notify' requires confirmation. Call again with confirm=true (and optional confirmation_data for extra form fields) to execute.",
  "confirmation_page": {
    "content_type": "text/html",
    "content": "<!DOCTYPE html>..."
  }
}
```

`confirmation_page.content` is the rendered HTML, truncated to 4000 characters.

Re-calling with `confirm: true` injects the standard Django confirmation markers `post="yes"`, `confirm="yes"`, and `apply="yes"` — plus any `confirmation_data` fields (stringified) — into `request.POST`, so Django-style two-step actions execute instead of rendering their intermediate page again.

### File downloads

Actions that return an `HttpResponse` or `StreamingHttpResponse` (e.g. CSV/PDF exports) are converted into a structured file payload under `result`:

```json
{
  "success": true,
  "action": "export_to_csv",
  "affected_count": 5,
  "message": "Executed export_to_csv on 5 objects",
  "result": {
    "type": "file",
    "content_type": "text/csv",
    "filename": "articles.csv",
    "size": 1024,
    "status_code": 200,
    "content_disposition": "attachment; filename=\"articles.csv\"",
    "encoding": "utf-8",
    "content": "id,title\n1,Getting Started with Django\n..."
  }
}
```

- Text-like content types (`text/*`, `application/json`, `application/xml`, `application/javascript`, CSV variants) are inlined as UTF-8 text with `"encoding": "utf-8"`; all other types are base64-encoded with `"encoding": "base64"`.
- `filename` is parsed from the `Content-Disposition` header (RFC 5987 `filename*` is preferred over plain `filename`), falling back to `"download"`.
- `content_disposition` is included only when the header is present.
- Bodies are capped at `MCP_ACTION_MAX_FILE_BYTES` (default 5 MiB). Larger responses return `{"error": "Action file response exceeds MCP_ACTION_MAX_FILE_BYTES (N bytes)"}`.

Non-response return values are stringified via `str(result)`.

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

Performs bulk operations on multiple records. Uses the `items` parameter for all operations.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `operation` | string | One of: `create`, `update`, `delete` | Yes |
| `items` | array | Items to process (format varies by operation) | Yes |

### Bulk Create

Create multiple records at once. Each item in `items` is a data object:

```json
{
  "method": "tools/call",
  "params": {
    "name": "bulk_article",
    "arguments": {
      "operation": "create",
      "items": [
        {"title": "Article 1", "author_id": 5},
        {"title": "Article 2", "author_id": 5},
        {"title": "Article 3", "author_id": 5}
      ]
    }
  }
}
```

### Bulk Update

Update multiple records. Each item in `items` contains an `id` and `data`:

```json
{
  "method": "tools/call",
  "params": {
    "name": "bulk_article",
    "arguments": {
      "operation": "update",
      "items": [
        {"id": 10, "data": {"status": "archived"}},
        {"id": 11, "data": {"status": "archived"}},
        {"id": 12, "data": {"status": "archived"}}
      ]
    }
  }
}
```

`id` is required per item; items without one fail with `{"index": i, "error": "id is required for update"}`.

### Bulk Delete

Delete multiple records. `items` is an array of IDs:

```json
{
  "method": "tools/call",
  "params": {
    "name": "bulk_article",
    "arguments": {
      "operation": "delete",
      "items": [100, 101, 102]
    }
  }
}
```

### Bulk Response Format

All bulk operations return a standardized response:

```json
{
  "operation": "create",
  "total_items": 3,
  "success_count": 2,
  "error_count": 1,
  "results": {
    "success": [
      {"index": 0, "id": 44, "created": true},
      {"index": 1, "id": 45, "created": true}
    ],
    "errors": [
      {
        "index": 2,
        "error": "Validation failed",
        "validation_errors": {
          "errors": [
            {"field": "title", "messages": ["This field is required."]}
          ],
          "error_count": 1,
          "fields_with_errors": ["title"]
        }
      }
    ]
  }
}
```

Missing objects in update/delete yield `{"index": i, "error": "Object with id X not found"}`.

### Bulk Semantics

- Each item runs in its own `transaction.atomic()` block: partial success is possible, and there is **no cross-item rollback** — items that succeeded stay committed even if later items fail.
- Bulk operations use `form.save()` / `obj.delete()` directly, **bypassing** `ModelAdmin.save_model()`/`delete_model()` and admin-queryset scoping (unlike `create_*`/`update_*`/`delete_*`). Objects are fetched via `model.objects.get(pk=...)`.
- An unknown operation returns `{"error": "operation must be 'create', 'update', or 'delete'"}`.

---

## Permission Requirements

| Operation | Required Permission |
|-----------|---------------------|
| `actions_*` (list) | `view_<model>` |
| `action_*` (execute) | `change_<model>` (plus `delete_<model>` for `delete_selected`) |
| `bulk_*` create | `add_<model>` |
| `bulk_*` update | `change_<model>` |
| `bulk_*` delete | `delete_<model>` |

---

## Error Handling

All errors are returned with HTTP 200 as JSON inside the JSON-RPC `result.content[0].text` — there is no `isError` flag.

### Unknown Action

```json
{
  "error": "Action 'nonexistent_action' not found"
}
```

### Empty Selection

Missing `ids`:

```json
{
  "error": "ids parameter is required"
}
```

No matching objects (within the admin queryset):

```json
{
  "error": "No objects found with the provided IDs"
}
```

Missing `action`:

```json
{
  "error": "action parameter is required"
}
```

### Permission Denied

```json
{
  "error": "Permission denied: cannot change article",
  "code": "permission_denied"
}
```

For `delete_selected` without delete permission:

```json
{
  "error": "Permission denied: cannot delete article",
  "code": "permission_denied"
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
bulk_article(operation="update", items=[{"id": 1, "data": {"status": "archived"}}, ...])
```

### Validate Before Bulk Operations

Use `list_*` to verify records before bulk operations:

```
1. list_article(filters={"status": "draft", "created_at__lt": "2023-01-01"})
2. Review the results
3. bulk_article(operation="delete", items=[15, 18, ...])
```

## Next Steps

- [Model Introspection](introspection.md) — Discover model schemas
- [Relationships](relationships.md) — Access related data
