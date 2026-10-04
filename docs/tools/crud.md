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

`order_by` accepts direct field names only, with an optional `-` prefix for descending order. Unknown fields return `{"error": "Invalid order_by — unknown fields: ..."}`.

### Supported filter lookups

Only the following lookups are allowed in `filters`:

| Lookup | Example key | Meaning |
|--------|-------------|---------|
| (none) / `exact` | `"published"` or `"published__exact"` | Exact match |
| `iexact` | `"title__iexact"` | Case-insensitive exact match |
| `contains` / `icontains` | `"title__icontains"` | Substring (case-sensitive / insensitive) |
| `startswith` / `istartswith` | `"title__startswith"` | Prefix |
| `endswith` / `iendswith` | `"title__iendswith"` | Suffix |
| `gt` / `gte` | `"created_at__gte"` | Greater than (or equal) |
| `lt` / `lte` | `"created_at__lt"` | Less than (or equal) |
| `in` | `"status__in"` | Value in a list (the value must be a list) |
| `range` | `"price__range"` | Between two values (the value must be a two-item list) |
| `isnull` | `"author__isnull"` | Null check (the value must be `true` or `false`) |
| `year` / `month` / `day` | `"created_at__year"` | Date part, on date and datetime fields |
| `date` | `"created_at__date"` | Date of a datetime field |

A date part may be followed by one comparison (`exact`, `gt`, `gte`, `lt`, `lte`, `in`, `range`), e.g. `"created_at__year__gte"`.

### What can be filtered

`filters` reproduces what the admin changelist offers through `list_filter` and `date_hierarchy`:

| Filter key | Allowed when |
|------------|--------------|
| A field of the model (`"status"`, `"author"`) | The field is visible over MCP (not hidden by `mcp_fields` / `mcp_exclude_fields`) |
| A relation path (`"category__slug"`, `"customer__is_staff"`) | The exact path is declared in the admin's `list_filter` — as a string or as a `(field, FilterClass)` tuple — or is its `date_hierarchy` |
| The related primary key (`"author__id"`, `"author__id__exact"`) | The relation itself may be filtered; this is the form the admin's own related filters use |
| A `SimpleListFilter` parameter (`"band"`) | The filter class is in `list_filter`; the key is its `parameter_name` and the value must be one of its `lookups()` |

```python
class PriceBandFilter(admin.SimpleListFilter):
    title = "price band"
    parameter_name = "band"

    def lookups(self, request, model_admin):
        return [("cheap", "Under 10"), ("pricey", "10 and over")]

    def queryset(self, request, queryset):
        if self.value() == "cheap":
            return queryset.filter(price__lt=10)
        if self.value() == "pricey":
            return queryset.filter(price__gte=10)
        return queryset


class ProductAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_filter = ["category__slug", "customer__is_staff", PriceBandFilter]
    date_hierarchy = "release_date"
```

```json
{"filters": {"category__slug": "toys", "release_date__year": 2026, "band": "cheap"}}
```

`list_filter` is read through `ModelAdmin.get_list_filter(request)`, so per-request filter sets are honored. `describe_<model>` lists every usable filter under `admin_config.filters`.

Rules that keep filters from becoming a side channel:

- A declared path allows that path only. `list_filter = ["customer__is_staff"]` does not allow `customer__email`, and a declared path cannot be extended to further relations.
- Hidden fields stay unfilterable even when declared: a path is rejected if any field along it is hidden by `mcp_fields` / `mcp_exclude_fields` on the admin of the model that owns it (including the terminal field on the related model's admin).
- A `SimpleListFilter` is applied through its own `queryset()` and takes no lookups (`band__in` is rejected). A value outside its `lookups()` is an error, because such filters typically ignore values they do not recognize.
- Filters that traverse a many-to-many or reverse relation return each row once.

!!! warning "Invalid filters are rejected"
    Any filter with an unknown or hidden field, a disallowed lookup (`regex`, `search`, `week_day`, ...), a malformed value, or an undeclared relation path (e.g. `author__email`) is **rejected with an error response** naming every offending key — the query never runs partially filtered.

Filters use **model field names**, not database column names: `{"author": 5}` filters by the FK, while `{"author_id": 5}` is rejected as an unknown field (the `_id` suffix works in `create_*` data but not in filters).

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
      "created_at": "2024-01-15T10:00:00Z",
      "_computed": {
        "word_count": 1250,
        "is_recent": false
      }
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

Each result contains the model's visible fields, including non-editable ones (`editable=False` fields such as UUIDs, `auto_now`/`auto_now_add` timestamps) — the same set `describe_<model>` lists.

#### Computed columns (`_computed`)

`list_display` entries that are not model fields — admin methods, model methods/properties, callables — are evaluated per row and returned under a separate `_computed` key, so they cannot collide with or be mistaken for writable fields:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ['title', 'author', 'word_count', 'is_recent']

    def word_count(self, obj):
        return len(obj.content.split())

    @admin.display(boolean=True)
    def is_recent(self, obj):
        return obj.created_at > timezone.now() - timedelta(days=7)
```

Computed values are served only when all of the following hold:

- the entry is declared on the admin (resolved through `get_list_display(request)`); nothing is looked up by a caller-supplied name
- it is not a model field, FK column (`author_id`), `pk`, or relation accessor — fields are returned as regular keys under the visibility rules, never through `_computed`
- its name does not contain `__` (`__str__` and relation traversals such as `author__email` are skipped)
- its name passes the same visibility rules as fields: `mcp_exclude_fields` hides it, and an allowlist (`mcp_fields`, or the admin's `fields` fallback) must name it

Values are evaluated the way the admin does (`django.contrib.admin.utils.lookup_field`): admin methods, model methods/properties, and bare callables (keyed by the function's `__name__`). Numbers, booleans, dates, and UUIDs keep their type; everything else (HTML from `format_html`, model instances, ...) is returned as `str(value)`. A callable that raises yields `null` for its key and is logged server-side — it never fails the response. `_computed` is omitted when there is nothing to report. Computed values are read-only: they are not accepted by `create_*`/`update_*`.

!!! warning "Computed values bypass per-field hiding"
    A method that returns data derived from a hidden field (for example a `token_preview` built from an excluded `token_key`) is served like any other computed value. Add the method's name to `mcp_exclude_fields` to hide it.

Computed columns run once per returned row; a method that queries the database adds a query per row, exactly as it does in the admin changelist.

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

Foreign keys serialize as bare primary keys (`"author": 5`), never as nested objects. Many-to-many fields serialize as lists of primary keys. Non-editable fields (`editable=False`, `auto_now`/`auto_now_add`) are returned like any other field, subject to the same `mcp_fields`/`mcp_exclude_fields` visibility rules.

Fields defined with `choices` keep their raw stored value and additionally get a `<field>_display` sidecar with the human-readable label (`"status": 2, "status_display": "Active"`). The sidecar follows the field's visibility rules and is skipped when the model has a real field of that name.

```json
{
  "id": 42,
  "title": "Getting Started with Django",
  "content": "This tutorial covers...",
  "author": 5,
  "categories": [1, 2],
  "status": 2,
  "status_display": "Active",
  "published": true,
  "created_at": "2024-01-15T10:00:00Z",
  "_computed": {
    "word_count": 1250
  },
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
| `_computed` | Present when the admin's `readonly_fields` (resolved through `get_readonly_fields(request, obj)`) contain computed entries — admin methods, model methods/properties, callables. Maps each entry's name to its value. Follows the same rules as [`list_*` computed columns](#computed-columns-_computed), with `readonly_fields` in place of `list_display`. Rows under `_inlines` / `_related` carry no `_computed`. |
| `_inlines` | Present with `include_inlines: true`. Maps each inline model name (from the admin's `inlines`) to a list of serialized instances. |
| `_related` | Present with `include_related: true` (and only if there is any data). Maps each reverse-relation accessor name to a list of serialized instances, hard-capped at **10 objects per relation**. Use `related_<model>` for full pagination. |

---

## create_\<model\>

Creates a new model instance with validation.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `data` | object | Field values for the new instance | Yes |
| `inlines` | object | Inline rows to create with the instance | No |

`data` keys are the fields of the admin's add form. Foreign keys may be sent under the field name or its `_id` alias (`author` or `author_id`). Date and datetime fields take a single ISO 8601 string (`"2026-03-01T09:30:00Z"`), whatever widget the admin form uses.

A key the form will not consume is **rejected**, never dropped: see [Rejected fields](#rejected-fields).

`inlines` has the same shape as on [`update_*`](#inline-behavior), restricted to new rows (`{"data": {...}}`). The instance and its inline rows are created together or not at all.

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

**With inline rows:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "create_article",
    "arguments": {
      "data": {"title": "New Article", "author_id": 5},
      "inlines": {
        "comment": [
          {"data": {"text": "First!"}},
          {"data": {"text": "Second"}}
        ]
      }
    }
  }
}
```

The response then carries an `inlines` key, as for [`update_*`](#response-3).

When a `ModelAdmin` is registered, creation follows the admin's add view: `get_form()` → `save_form()` → `save_model()` → `save_related()`, which saves many-to-many data and then each inline formset through `save_formset()`. Overrides of any of these hooks run. A `LogEntry` is written for the addition.

Messages the admin queues with `self.message_user()` during the call are returned in a `messages` list of `{"level", "message"}` objects (levels are Django's `debug`, `info`, `success`, `warning`, `error`); the key is omitted when there are none, or when the admin sets [`mcp_return_messages = False`](../reference/settings.md#mcp_return_messages). The same applies to `update_*` and `delete_*`:

```json
{
  "success": true,
  "id": 43,
  "object": {"id": 43, "title": "New Article"},
  "messages": [
    {"level": "info", "message": "Welcome mail queued"}
  ]
}
```

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

Only `id` is required, and only the fields sent in `data` change. `data` keys are the fields of the admin's change form, with the same conventions as `create_*`: `_id` aliases for foreign keys, a single ISO 8601 string for datetimes. A key the form will not consume is rejected: see [Rejected fields](#rejected-fields).

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

Inline rows are validated with the admin's own formsets (`InlineModelAdmin.get_formset()`), so the inline's form, `fields`/`exclude`, `get_readonly_fields()` and formset-level validation all apply, and they are saved through `ModelAdmin.save_formset()`.

- **All or nothing.** The parent and every inline operation are validated first and saved in one transaction. Any inline error rejects the whole call: the parent change is not saved either, and the response is an [inline error](#inline-errors) instead of a success.
- Each operation is checked against the inline's own `add`/`change`/`delete` permission (`"code": "permission_denied"`).
- Existing rows are looked up within the parent; an `id` belonging to another parent is `"code": "not_found"`.
- The inline's `min_num`/`max_num` are enforced on the resulting object count (`"code": "max_num_exceeded"` / `"code": "min_num_violated"`).
- An inline name the admin does not declare is `"code": "unknown_inline"`.
- Inline `data` follows the same rules as top-level `data`: read-only and unknown keys are rejected, datetimes take one ISO 8601 string. The foreign key to the parent is set automatically.
- Rows you do not name are left untouched.
- The success response includes an `inlines` key with `created`, `updated`, `deleted`, and an always-empty `errors` list.

### Inline errors

```json
{
  "error": "Inline operations failed; nothing was saved",
  "code": "inline_error",
  "inlines": {
    "errors": [
      {
        "model": "comment",
        "id": null,
        "index": 1,
        "error": "Validation failed",
        "validation_errors": {
          "errors": [{"field": "rating", "messages": ["Ensure this value is less than or equal to 5."]}],
          "error_count": 1,
          "fields_with_errors": ["rating"]
        }
      }
    ]
  }
}
```

Each entry names the inline `model`, the row `id` (`null` for a new row), the `index` of the operation in the list you sent, an `error`, and — depending on the failure — a `code`, `validation_errors`, `readonly_fields` or `invalid_fields`. The same response shape is returned by `create_*`.

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

When a `ModelAdmin` is registered, the update follows the admin's change view: `get_form()` → `save_form()` → `save_model()` → `save_related()` (many-to-many data, then each inline formset through `save_formset()`). A `LogEntry` is written for the change. Messages queued with `message_user()` are returned in `messages`, as for `create_*`.

### Rejected fields

`create_*`, `update_*` and `bulk_*` never drop a field silently. A key the admin form will not consume fails the call (or, in bulk, that item) and nothing is saved.

Read-only fields are resolved through `get_readonly_fields(request, obj)`, so dynamic rules apply:

```python
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    readonly_fields = ['created_at', 'view_count']
```

```json
{
  "error": "Cannot update readonly fields: view_count",
  "readonly_fields": ["view_count"]
}
```

(`create_*` words it `Cannot set readonly fields: ...`.)

Any other key the form does not read — a typo, a model field with `editable=False`, a field left out by the admin's `fields`/`exclude`, a field the form disables — is reported as:

```json
{
  "error": "Invalid field: internal_code",
  "invalid_fields": ["internal_code"]
}
```

What is accepted is derived from the admin form itself, not from the model, so these all work:

- foreign key `_id` aliases (`author_id`)
- form fields that are not model fields (the stock `UserAdmin` add form takes `password1` / `password2`)
- the sub-keys of a multi-widget (`starts_at_0` / `starts_at_1`), although a single ISO 8601 string under the field name is simpler
- a file field's name with an upload object, and its `<name>-clear` checkbox — see [File Uploads](#file-uploads)

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

When a `ModelAdmin` is registered, deletion routes through `ModelAdmin.delete_model()`, and a `LogEntry` is written before the deletion (so the audit trail retains the object's representation). Messages queued with `message_user()` are returned in `messages`, as for `create_*`.

!!! warning "Cascade Deletes"
    Deletion follows Django's cascade rules. Related objects with `on_delete=CASCADE` will also be deleted.

---

## Foreign Key Handling

In `create_*`, `update_*` and `bulk_*` data, foreign keys can be specified in two ways:

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

Filters in `list_*` require model field names (`{"author": 5}`); `author_id` there is rejected as an unknown field.

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

## File Uploads

In `create_*`, `update_*` and `bulk_*` data, and in inline rows, a `FileField` / `ImageField` takes the file as a JSON object:

```json
{
  "title": "Manual",
  "file": {
    "filename": "manual.pdf",
    "content_base64": "JVBERi0xLjQK...",
    "content_type": "application/pdf"
  }
}
```

| Key | Type | Description | Required |
|-----|------|-------------|----------|
| `filename` | string | Name of the file. Reduced to its base name: any directory part (`../`, `C:\...`) is dropped | Yes |
| `content_base64` | string | The file content, base64-encoded (line breaks are tolerated) | Yes |
| `content_type` | string | MIME type. Guessed from the filename when absent, `application/octet-stream` when it cannot be guessed | No |

The object is decoded into an uploaded file and handed to the admin form the way a browser upload is, so the form field validates it: `required`, the model field's validators (`FileExtensionValidator`, ...), `ImageField`'s image check, and `max_length` on the file name. The file is stored by the field's storage under its `upload_to`, and responses keep returning the stored name (`"file": "documents/manual.pdf"`).

| Value sent for a file field | Effect |
|-----------------------------|--------|
| upload object | The file is stored and replaces the current one |
| field left out | On update the stored file is kept; on create the field is empty |
| `null` | Clears an optional file (same as `"<name>-clear": true`). On a required field: `This field is required.` |
| a string, number, array, ... | Validation error. Referencing an existing storage path is not supported |

The decoded content may not exceed [`MCP_UPLOAD_MAX_FILE_BYTES`](../reference/settings.md#mcp_upload_max_file_bytes) (default 5 MiB). The size is computed from the base64 length, so an oversized file is refused without being decoded.

A file value that cannot be used is a validation error on that field, in the same shape as any other form error:

```json
{
  "error": "Validation failed",
  "code": "validation_error",
  "validation_errors": {
    "errors": [
      {"field": "file", "messages": ["content_base64 is not valid base64."]}
    ],
    "error_count": 1,
    "fields_with_errors": ["file"]
  }
}
```

| Cause | Message |
|-------|---------|
| Not an object | `A file must be sent as an object {...}, not a string. Referencing an existing storage path is not supported.` |
| Extra key | `Unknown key in file object: url. Allowed keys: content_base64, content_type, filename.` |
| `filename` missing, empty or not a file name | `filename is required and must be a non-empty file name.` |
| `content_base64` missing or not a string | `content_base64 is required and must be a base64 string.` |
| Invalid base64 | `content_base64 is not valid base64.` |
| `content_type` not a non-empty string | `content_type must be a non-empty string when given.` |
| Too large | `File is too large: N bytes exceeds MCP_UPLOAD_MAX_FILE_BYTES (M bytes).` |
| Upload sent together with `<name>-clear: true` | Django's `Please either submit a file or check the clear checkbox, not both.` |

In an inline row the same `validation_errors` object appears on that row's entry in `inlines.errors`.

!!! note "Audit log"
    The `LogEntry` written for a create or update records an upload as `{"filename": ..., "size": ...}`. File content is never written to the log.

!!! note "Files and rollback"
    As in the Django admin, the file is written to storage when the object is saved. If a later step of the same call fails and the database transaction rolls back, the stored file is not removed.

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
