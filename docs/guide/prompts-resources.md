# Prompts & Resources

Beyond tools, Django Admin MCP implements two more MCP primitives on the
JSON-RPC endpoint: **Prompts** (reusable workflow guides) and **Resources**
(read-only data access via URIs).

## Prompts

Prompts help agents work with your admin effectively.

| Prompt | Arguments | Purpose |
|--------|-----------|---------|
| `explore_models` | — | How to discover models and browse data |
| `understand_model` | `model_name` | Deep dive into one model's fields and admin config |
| `crud_guide` | `model_name` | Safe create/update/delete practices, including inlines |
| `bulk_operations_guide` | — | Bulk tools, admin actions, and the confirmation flow |

```bash
# List prompts
curl -X POST https://example.com/mcp/ \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "prompts/list"}'

# Get a prompt with arguments
curl -X POST https://example.com/mcp/ \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "prompts/get",
       "params": {"name": "understand_model", "arguments": {"model_name": "article"}}}'
```

An unknown prompt name or a missing required argument returns JSON-RPC error `-32602`. Prompts without arguments ignore any arguments passed.

## Resources

Resources expose read-only data through URI schemes. Listings are filtered
by the token user's module and view permissions, and reads go through the
same permission checks as the tools.

| URI | Content |
|-----|---------|
| `models://{model_name}/schema` | Field metadata and admin configuration |
| `data://{model_name}/` | Paginated instance list (first 50) |
| `data://{model_name}/{id}` | A single instance by primary key |

```bash
# List available resources
curl -X POST https://example.com/mcp/ \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "resources/list"}'

# Read a model schema
curl -X POST https://example.com/mcp/ \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "resources/read",
       "params": {"uri": "models://article/schema"}}'
```

Dynamic URIs are advertised via `resources/templates/list`.

Notes:

- `resources/list` only advertises `mcp_expose = True` models, but `resources/read` resolves any mixin-registered model (permission checks still apply) — mirroring how `tools/list` and `tools/call` behave.
- The `{id}` segment of `data://{model}/{id}` is passed through as a string; extra path segments produce an error.
- A missing `uri` parameter returns JSON-RPC error `-32602`; read failures (unknown model, not found, permission denied) return `-32002`.

## Action Confirmation Flow

Admin actions that render an intermediate confirmation page are supported
with a two-step workflow:

1. Call `action_<model>` normally. If the action needs confirmation, the
   response contains `requires_confirmation: true` and the page content.
2. Call again with `confirm: true` — the standard Django confirmation
   markers (`post`, `confirm`, `apply`) are set in `request.POST`. Extra
   form fields go in `confirmation_data`.

```json
{
  "action": "archive_selected",
  "ids": [1, 2, 3],
  "confirm": true,
  "confirmation_data": {"reason": "cleanup"}
}
```
