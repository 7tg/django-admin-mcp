# 🔍 Model Introspection

Django Admin MCP provides tools to discover models and inspect their structure programmatically.

## 🌐 find_models

Discovers all registered models. Results are filtered by the token's `view` permission.

### Parameters

| Parameter | Type | Description | Required |
|-----------|------|-------------|----------|
| `query` | string | Filter models by name | No |

### Examples

**List all models:**

```json
{
  "method": "tools/call",
  "name": "find_models",
  "arguments": {}
}
```

**Filter by name:**

```json
{
  "method": "tools/call",
  "name": "find_models",
  "arguments": {
    "query": "article"
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
      "verbose_name": "Article",
      "verbose_name_plural": "Articles",
      "app_label": "blog",
      "tools_exposed": true
    },
    {
      "model_name": "author",
      "verbose_name": "Author",
      "verbose_name_plural": "Authors",
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
| `tools_exposed` | Whether CRUD tools are available |

---

## 📐 describe_\<model\>

Returns detailed field definitions and metadata for a model.

### Parameters

None required.

### Example

```json
{
  "method": "tools/call",
  "name": "describe_article",
  "arguments": {}
}
```

### Response

```json
{
  "model_name": "article",
  "verbose_name": "Article",
  "verbose_name_plural": "Articles",
  "app_label": "blog",
  "fields": [
    {
      "name": "id",
      "type": "AutoField",
      "required": false,
      "readonly": true,
      "primary_key": true,
      "description": "Primary key"
    },
    {
      "name": "title",
      "type": "CharField",
      "required": true,
      "readonly": false,
      "max_length": 200,
      "description": "Article title"
    },
    {
      "name": "content",
      "type": "TextField",
      "required": false,
      "readonly": false,
      "description": "Article content"
    },
    {
      "name": "author",
      "type": "ForeignKey",
      "required": true,
      "readonly": false,
      "related_model": "blog.author",
      "description": "Article author"
    },
    {
      "name": "categories",
      "type": "ManyToManyField",
      "required": false,
      "readonly": false,
      "related_model": "blog.category",
      "description": "Article categories"
    },
    {
      "name": "published",
      "type": "BooleanField",
      "required": false,
      "readonly": false,
      "default": false,
      "description": "Is published"
    },
    {
      "name": "created_at",
      "type": "DateTimeField",
      "required": false,
      "readonly": true,
      "auto_now_add": true,
      "description": "Creation timestamp"
    },
    {
      "name": "updated_at",
      "type": "DateTimeField",
      "required": false,
      "readonly": true,
      "auto_now": true,
      "description": "Last update timestamp"
    }
  ],
  "relationships": {
    "forward": [
      {
        "name": "author",
        "type": "ForeignKey",
        "related_model": "blog.author"
      },
      {
        "name": "categories",
        "type": "ManyToManyField",
        "related_model": "blog.category"
      }
    ],
    "reverse": [
      {
        "name": "comments",
        "type": "reverse_fk",
        "related_model": "blog.comment",
        "related_name": "article"
      }
    ]
  },
  "admin_config": {
    "list_display": ["title", "author", "published", "created_at"],
    "search_fields": ["title", "content"],
    "ordering": ["-created_at"],
    "readonly_fields": ["created_at", "updated_at"]
  }
}
```

### 📋 Field Properties

Each field includes relevant properties:

| Property | Description |
|----------|-------------|
| `name` | Field name |
| `type` | Django field type |
| `required` | Whether the field is required |
| `readonly` | Whether the field is read-only |
| `max_length` | Maximum length (CharField) |
| `choices` | Available choices (ChoiceField) |
| `related_model` | Related model (FK/M2M) |
| `default` | Default value |
| `description` | Field help text or verbose name |

### 🏷️ Field Types

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

## 💡 Use Cases

### 🔎 Schema Discovery

Before creating records, discover required fields:

```python
# 1. Describe the model
describe_article() -> fields with required=true

# 2. Create with required fields
create_article(data={"title": "...", "author_id": 5})
```

### 🖥️ Dynamic Form Generation

Use field metadata to generate forms:

```javascript
const description = await callTool('describe_article');

for (const field of description.fields) {
  if (field.type === 'CharField') {
    createTextInput(field.name, field.max_length);
  } else if (field.type === 'BooleanField') {
    createCheckbox(field.name, field.default);
  } else if (field.type === 'ForeignKey') {
    createSelect(field.name, field.related_model);
  }
}
```

### 🔗 Relationship Mapping

Discover how models are connected:

```json
{
  "relationships": {
    "forward": [
      {"name": "author", "related_model": "blog.author"}
    ],
    "reverse": [
      {"name": "comments", "related_model": "blog.comment"}
    ]
  }
}
```

### ⚙️ Understanding Admin Configuration

See how the admin is configured:

```json
{
  "admin_config": {
    "list_display": ["title", "author", "published"],
    "search_fields": ["title", "content"],
    "ordering": ["-created_at"]
  }
}
```

---

## 🔒 Permission Requirements

| Tool | Required Permission |
|------|---------------------|
| `find_models` | Filters results by `view_<model>` |
| `describe_*` | `view_<model>` |

## 🔗 Next Steps

- [Relationships](relationships.md) — Access related data
- [CRUD Operations](crud.md) — Work with data
