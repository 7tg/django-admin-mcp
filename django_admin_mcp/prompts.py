"""
MCP Prompts support for django-admin-mcp.

Prompts are reusable instruction templates that guide MCP clients through
common Django admin workflows (discovery, CRUD, bulk operations).
Served via the ``prompts/list`` and ``prompts/get`` JSON-RPC methods.
"""

from typing import Any


class PromptError(ValueError):
    """Raised for unknown prompts or missing required arguments."""


def _explore_models_text(arguments: dict[str, Any]) -> str:
    return (
        "You are working with a Django admin instance exposed over MCP.\n\n"
        "To discover what is available:\n"
        "1. Call the `find_models` tool (optionally with a `query` filter) to list "
        "the models you can access. Models hidden by permissions do not appear.\n"
        "2. For each interesting model, call `describe_<model>` to get its fields, "
        "types, constraints, relationships, and admin configuration.\n"
        "3. Use `list_<model>` with `limit`/`offset`, `filters`, `search`, and "
        "`order_by` to browse data. Filters support exact, contains, icontains, "
        "gt, gte, lt, lte, in, and isnull lookups on direct fields.\n"
        "4. Use `actions_<model>` to see the admin actions you can execute.\n\n"
        "Start with `find_models` before assuming a model exists."
    )


def _understand_model_text(arguments: dict[str, Any]) -> str:
    model_name = arguments["model_name"]
    return (
        f"Build a complete picture of the `{model_name}` model:\n\n"
        f"1. Call `describe_{model_name}` and study the response:\n"
        "   - `fields`: names, types, whether they are required, defaults, and choices\n"
        "   - `relationships`: FK/M2M links to other models and their accessors\n"
        "   - `admin_config`: list_display, search_fields, ordering, readonly_fields, "
        "and inlines — readonly fields cannot be updated via MCP\n"
        f"2. Sample real data with `list_{model_name}` (small `limit` first) to see "
        "actual value shapes.\n"
        f"3. Fetch one row with `get_{model_name}` using `include_inlines: true` and "
        "`include_related: true` to see nested structures.\n"
        f"4. Check `actions_{model_name}` for bulk operations the admin provides.\n\n"
        "Respect constraints you observe: required fields must be provided on create, "
        "and FK fields take the related object's primary key."
    )


def _crud_guide_text(arguments: dict[str, Any]) -> str:
    model_name = arguments["model_name"]
    return (
        f"Safely create, update, and delete `{model_name}` objects:\n\n"
        f"- **Create**: call `create_{model_name}` with a `data` dict. Run "
        f"`describe_{model_name}` first to learn required fields. Validation errors "
        "come back under `validation_errors` — fix the listed fields and retry.\n"
        f"- **Update**: call `update_{model_name}` with `id` and a partial `data` "
        "dict; only include the fields you change. Readonly fields are rejected. "
        "Inline children can be edited in the same call via `inlines`: items with "
        "`data` are created, items with `id` + `data` are updated, and items with "
        "`id` + `_delete: true` are removed. min_num/max_num limits are enforced.\n"
        f"- **Delete**: call `delete_{model_name}` with `id`. This cascades per the "
        "model's on_delete rules — check relationships first if unsure.\n\n"
        "Every write is validated through the model's admin form and logged to the "
        "Django admin history."
    )


def _bulk_operations_guide_text(arguments: dict[str, Any]) -> str:
    return (
        "For operating on many objects at once:\n\n"
        "- `bulk_<model>` with `operation` create/update/delete and an `items` list "
        "processes each item independently and reports per-item successes and errors.\n"
        "- `action_<model>` executes a Django admin action on selected `ids`. "
        "Discover actions with `actions_<model>` first.\n"
        "- If an action responds with `requires_confirmation: true`, review the "
        "included confirmation page, then call `action_<model>` again with "
        "`confirm: true` (plus any extra form fields under `confirmation_data`) "
        "to execute it.\n\n"
        "Prefer `filters` on `list_<model>` to find the target ids rather than "
        "paging through everything."
    )


_PROMPTS: dict[str, dict[str, Any]] = {
    "explore_models": {
        "description": "Guide for discovering the Django admin models exposed over MCP",
        "arguments": [],
        "builder": _explore_models_text,
    },
    "understand_model": {
        "description": "Deep dive into a specific model's fields, constraints, and admin config",
        "arguments": [
            {"name": "model_name", "description": "Lowercase model name (from find_models)", "required": True}
        ],
        "builder": _understand_model_text,
    },
    "crud_guide": {
        "description": "Best practices for creating, updating, and deleting objects of a model",
        "arguments": [
            {"name": "model_name", "description": "Lowercase model name (from find_models)", "required": True}
        ],
        "builder": _crud_guide_text,
    },
    "bulk_operations_guide": {
        "description": "How to efficiently perform bulk operations and admin actions",
        "arguments": [],
        "builder": _bulk_operations_guide_text,
    },
}


def list_prompts() -> list[dict[str, Any]]:
    """Return prompt metadata for the prompts/list response."""
    return [
        {"name": name, "description": info["description"], "arguments": info["arguments"]}
        for name, info in _PROMPTS.items()
    ]


def get_prompt(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Build a prompt for the prompts/get response.

    Raises:
        PromptError: For an unknown prompt name or missing required arguments.
    """
    info = _PROMPTS.get(name or "")
    if info is None:
        raise PromptError(f"Unknown prompt: {name}")

    for argument in info["arguments"]:
        if argument.get("required") and not arguments.get(argument["name"]):
            raise PromptError(f"Missing required argument '{argument['name']}' for prompt '{name}'")

    text = info["builder"](arguments)
    return {
        "description": info["description"],
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }
