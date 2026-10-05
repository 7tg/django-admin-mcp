# Model Introspection

Django Admin MCP provides tools to discover models and inspect their structure programmatically.

## find_models

Discovers all registered models. Results are filtered by `has_module_permission()` first — hidden modules are excluded entirely, mirroring the Django admin index — then by the token's `view` permission.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `query` | string | Filter models by name | No |

### Examples

**List all models:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "find_models",
    "arguments": {}
  }
}
```

**Filter by name:**

```json
{
  "method": "tools/call",
  "params": {
    "name": "find_models",
    "arguments": {
      "query": "article"
    }
  }
}
```

### Response

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

### Response Fields

| Field | Description |
|-------|-------------|
| `count` | Number of models returned |
| `model_name` | Model name (lowercase) |
| `verbose_name` | Human-readable singular name |
| `verbose_name_plural` | Human-readable plural name |
| `app_label` | Django app containing the model |
| `tools_exposed` | Whether per-model tools are generated (reflects the admin's `mcp_expose` flag; discoverable-only models report `false`) |

---

## describe_\<model\>

Returns detailed field definitions and metadata for a model.

### Parameters

None required.

### Example

```json
{
  "method": "tools/call",
  "params": {
    "name": "describe_article",
    "arguments": {}
  }
}
```

### Response

Every field with a `related_model` (forward FK/M2M **and** reverse relations) is listed under `relationships`; all other concrete fields go under `fields`.

```json
{
  "model_name": "article",
  "verbose_name": "article",
  "verbose_name_plural": "articles",
  "app_label": "blog",
  "fields": [
    {
      "name": "id",
      "type": "AutoField",
      "verbose_name": "ID",
      "required": false,
      "primary_key": true,
      "unique": true,
      "editable": true
    },
    {
      "name": "title",
      "type": "CharField",
      "verbose_name": "title",
      "required": true,
      "max_length": 200,
      "editable": true
    },
    {
      "name": "status",
      "type": "CharField",
      "verbose_name": "status",
      "required": false,
      "max_length": 20,
      "choices": [
        {"value": "draft", "label": "Draft"},
        {"value": "published", "label": "Published"}
      ],
      "default": "draft",
      "editable": true
    },
    {
      "name": "published",
      "type": "BooleanField",
      "verbose_name": "published",
      "required": false,
      "default": false,
      "editable": true
    },
    {
      "name": "created_at",
      "type": "DateTimeField",
      "verbose_name": "created at",
      "required": false,
      "editable": false
    }
  ],
  "relationships": [
    {
      "name": "author",
      "type": "ForeignKey",
      "verbose_name": "author",
      "required": true,
      "related_model": "author",
      "related_app": "blog",
      "on_delete": "CASCADE",
      "editable": true
    },
    {
      "name": "categories",
      "type": "ManyToManyField",
      "verbose_name": "categories",
      "required": false,
      "related_model": "category",
      "related_app": "blog",
      "editable": true
    },
    {
      "name": "comment",
      "type": "Unknown",
      "verbose_name": "comment",
      "required": false,
      "related_model": "comment",
      "related_app": "blog",
      "on_delete": "CASCADE"
    }
  ],
  "admin_config": {
    "list_display": ["title", "author", "published", "created_at"],
    "list_filter": ["published", "created_at"],
    "filters": [
      {"name": "published", "kind": "field", "type": "BooleanField"},
      {"name": "created_at", "kind": "field", "type": "DateTimeField"}
    ],
    "search_fields": ["title", "content"],
    "ordering": ["-created_at"],
    "readonly_fields": ["created_at", "updated_at"]
  }
}
```

`relationships` is a **flat list** of the same field-metadata dicts as `fields` — there is no `forward`/`reverse` grouping and no `related_name` key. `type` values are Django internal types (`ForeignKey`, `ManyToManyField`, `OneToOneField`); reverse relations (which have no internal type) get `"type": "Unknown"`.

`admin_config` always emits `list_display`, `list_filter`, `filters`, `search_fields`, `ordering`, and `readonly_fields`. It conditionally includes `fieldsets` (as `[{"name", "fields", "classes"}]`), `date_hierarchy`, and `inlines` (as `[{"model", "fk_name"}]`). Non-string entries (callables, filter classes) are stringified to dotted paths.

### File fields

An editable `FileField` / `ImageField` carries an `upload` key describing how to send a file in `create_*` / `update_*` / `bulk_*` data (see [File Uploads](crud.md#file-uploads)):

```json
{
  "name": "file",
  "type": "FileField",
  "verbose_name": "file",
  "required": true,
  "max_length": 100,
  "editable": true,
  "upload": {
    "value": {
      "filename": "string, required; reduced to its base name",
      "content_base64": "string, required; the file content, base64-encoded",
      "content_type": "string, optional; guessed from the filename when absent"
    },
    "max_bytes": 5242880,
    "clearable": false
  }
}
```

`max_bytes` is the current `MCP_UPLOAD_MAX_FILE_BYTES`; `clearable` is true for an optional (`blank=True`) field, which `null` clears.

### Usable filters

`admin_config.list_filter` echoes the admin's declaration (via `get_list_filter(request)`). `admin_config.filters` lists what `list_<model>` actually accepts from it, in declaration order, followed by the `date_hierarchy` field:

```json
"filters": [
  {"name": "size", "kind": "field", "type": "CharField",
   "choices": [{"value": "s", "label": "Small"}, {"value": "l", "label": "Large"}]},
  {"name": "category__slug", "kind": "field", "type": "SlugField"},
  {"name": "band", "kind": "parameter", "title": "price band",
   "choices": [{"value": "cheap", "label": "Under 10"}, {"value": "pricey", "label": "10 and over"}]},
  {"name": "release_date", "kind": "field", "type": "DateField", "date_hierarchy": true}
]
```

| Key | Presence | Description |
|-----|----------|-------------|
| `name` | always | The key to use in `filters` |
| `kind` | always | `field` (a field or relation path; takes the [standard lookups](crud.md#supported-filter-lookups)) or `parameter` (a `SimpleListFilter`; exact value only) |
| `type` | `field` only | Django internal type of the terminal field |
| `title` | `parameter` only | The filter's title |
| `choices` | when known | `[{"value", "label"}]`: the field's `choices`, or the filter's `lookups()`; capped at 100 entries, with `"choices_truncated": true` beyond that |
| `date_hierarchy` | only when `true` | The field is the admin's `date_hierarchy` |

Declared entries that cannot be used over MCP are omitted: fields hidden by `mcp_fields` / `mcp_exclude_fields`, and filter classes that are not `SimpleListFilter` subclasses. The model's own visible fields remain filterable whether or not they appear here.

### Field Properties

Field metadata keys, as emitted by the handler:

| Property | Presence | Description |
|----------|----------|-------------|
| `name` | always | Field name |
| `type` | always | Django internal field type (`"Unknown"` for reverse relations) |
| `verbose_name` | always | Human-readable name |
| `required` | always | `true` when the field has no `null`, no `blank`, and no default |
| `editable` | if the field has the attribute | Whether the field is editable |
| `unique` | only when `true` | Unique constraint |
| `primary_key` | only when `true` | Primary key flag |
| `max_length` | when set | Maximum length (CharField etc.) |
| `help_text` | when set | Field help text |
| `choices` | when set | List of `{"value", "label"}` objects; grouped (optgroup) choices are flattened so every choice is listed |
| `default` | non-callable defaults only | Default value |
| `has_default` | callable defaults only | `true` when the default is a callable |
| `related_model` | FK/M2M/reverse | Bare related model name (e.g. `"author"`) |
| `related_app` | FK/M2M/reverse | App label of the related model (e.g. `"blog"`) |
| `on_delete` | FK/reverse FK | `on_delete` behavior name (e.g. `"CASCADE"`) |

There are no `readonly`, `description`, or `auto_now`/`auto_now_add` keys.

### Field Types

Common field types returned:

| Type | Django Field |
|------|--------------|
| `AutoField` | Auto-incrementing primary key |
| `CharField` | Text with max length |
| `TextField` | Unlimited text |
| `IntegerField` | Integer |
| `FloatField` | Floating point number |
| `DecimalField` | Decimal number |
| `BooleanField` | True/False |
| `DateField` | Date only |
| `DateTimeField` | Date and time |
| `TimeField` | Time only |
| `EmailField` | Email address |
| `URLField` | URL |
| `FileField` | File upload |
| `ImageField` | Image upload |
| `ForeignKey` | Foreign key relation |
| `ManyToManyField` | Many-to-many relation |
| `OneToOneField` | One-to-one relation |

---

## Use Cases

### Schema Discovery

Before creating records, discover required fields:

```python
# 1. Describe the model
describe_article() -> fields with required=true

# 2. Create with required fields
create_article(data={"title": "...", "author_id": 5})
```

!!! note "Required FK fields live under relationships"
    Required foreign key fields appear in the `relationships` list, not in `fields`. To discover all required inputs for `create_*`, read `required` from **both** lists.

### Dynamic Form Generation

Use field metadata to generate forms. FK/M2M fields are in `relationships`, not `fields` — a loop over `fields` will never see a `ForeignKey`:

```javascript
const description = await callTool('describe_article');

for (const field of description.fields) {
  if (field.type === 'CharField') {
    createTextInput(field.name, field.max_length);
  } else if (field.type === 'BooleanField') {
    createCheckbox(field.name, field.default);
  }
}

for (const rel of description.relationships) {
  if (rel.type === 'ForeignKey') {
    createSelect(rel.name, `${rel.related_app}.${rel.related_model}`);
  }
}
```

### Relationship Mapping

Discover how models are connected. `related_model` is the bare model name, with the app label in a separate `related_app` key:

```json
{
  "relationships": [
    {"name": "author", "type": "ForeignKey", "related_model": "author", "related_app": "blog"},
    {"name": "categories", "type": "ManyToManyField", "related_model": "category", "related_app": "blog"},
    {"name": "comment", "type": "Unknown", "related_model": "comment", "related_app": "blog"}
  ]
}
```

### Understanding Admin Configuration

See how the admin is configured:

```json
{
  "admin_config": {
    "list_display": ["title", "author", "published"],
    "list_filter": ["published"],
    "search_fields": ["title", "content"],
    "ordering": ["-created_at"],
    "readonly_fields": []
  }
}
```

---

## Permission Requirements

| Tool | Required Permission |
|------|---------------------|
| `find_models` | Filters results by `has_module_permission()` and `view_<model>` |
| `describe_*` | `view_<model>` |

## Next Steps

- [Relationships](relationships.md) — Access related data
- [CRUD Operations](crud.md) — Work with data
