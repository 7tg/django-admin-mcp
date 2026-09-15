"""
MCP Resources support for django-admin-mcp.

Resources expose read-only data through URI schemes, complementing the
action-oriented tools. Served via the ``resources/list``,
``resources/templates/list``, and ``resources/read`` JSON-RPC methods.

URI schemes:
- ``models://{model_name}/schema`` — field metadata and admin configuration
- ``data://{model_name}/`` — paginated instance list
- ``data://{model_name}/{id}`` — a single instance
"""

import json
from typing import Any

from django.http import HttpRequest

from django_admin_mcp.handlers import handle_describe, handle_get, handle_list
from django_admin_mcp.handlers.base import (
    async_check_module_permission,
    async_check_permission,
    get_exposed_models,
)

# Page size for data://{model_name}/ list resources
_LIST_RESOURCE_LIMIT = 50


class ResourceError(ValueError):
    """Raised when a resource URI is unknown or cannot be read."""


async def list_resources(request: HttpRequest) -> list[dict[str, Any]]:
    """
    List readable resources, filtered by the requesting user's permissions.

    Mirrors find_models visibility: models hidden by module permission or
    lacking view permission are omitted entirely.
    """
    resources = []
    for model_name, model_admin in get_exposed_models():
        if not await async_check_module_permission(request, model_admin):
            continue
        if not await async_check_permission(request, model_admin, "view"):
            continue
        resources.append(
            {
                "uri": f"models://{model_name}/schema",
                "name": f"{model_name} schema",
                "description": f"Field metadata and admin configuration for {model_name}",
                "mimeType": "application/json",
            }
        )
        resources.append(
            {
                "uri": f"data://{model_name}/",
                "name": f"{model_name} data",
                "description": f"Paginated list of {model_name} instances (first {_LIST_RESOURCE_LIMIT})",
                "mimeType": "application/json",
            }
        )
    return resources


def list_resource_templates() -> list[dict[str, Any]]:
    """List URI templates for dynamically addressable resources."""
    return [
        {
            "uriTemplate": "models://{model_name}/schema",
            "name": "Model schema",
            "description": "Field metadata and admin configuration for a model",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "data://{model_name}/",
            "name": "Model instance list",
            "description": f"Paginated list of model instances (first {_LIST_RESOURCE_LIMIT})",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "data://{model_name}/{id}",
            "name": "Model instance",
            "description": "A single model instance by primary key",
            "mimeType": "application/json",
        },
    ]


async def read_resource(uri: str, request: HttpRequest) -> dict[str, Any]:
    """
    Read one resource by URI, reusing the permission-checked tool handlers.

    Returns:
        A contents entry dict with uri, mimeType, and text.

    Raises:
        ResourceError: For unknown URIs or unreadable resources (missing
            model, missing instance, or denied permission).
    """
    scheme, separator, rest = (uri or "").partition("://")
    if not separator or not rest:
        raise ResourceError(f"Unknown resource URI: {uri}")

    model_name, _, tail = rest.partition("/")

    if scheme == "models" and tail == "schema":
        result = await handle_describe(model_name, {}, request)
    elif scheme == "data" and tail == "":
        result = await handle_list(model_name, {"limit": _LIST_RESOURCE_LIMIT}, request)
    elif scheme == "data" and "/" not in tail:
        result = await handle_get(model_name, {"id": tail}, request)
    else:
        raise ResourceError(f"Unknown resource URI: {uri}")

    text = result[0].text

    # Handlers report failures (missing model/instance, permission denied) as
    # error JSON; surface those as resource errors instead of resource content
    payload = json.loads(text)
    if isinstance(payload, dict) and payload.get("error"):
        raise ResourceError(str(payload["error"]))

    return {"uri": uri, "mimeType": "application/json", "text": text}
