"""
Decorators for django-admin-mcp handlers.
"""

from functools import wraps

from django_admin_mcp.handlers.base import async_check_permission, get_model_admin, json_response


def require_registered_model(fn):
    """Resolve model_name to model/model_admin, returning an error if not registered."""

    @wraps(fn)
    async def wrapper(model_name, arguments, request):
        model, model_admin = get_model_admin(model_name)
        if model is None:
            return json_response({"error": f"Model '{model_name}' not found"})
        return await fn(model_name, arguments, request, model=model, model_admin=model_admin)

    return wrapper


def require_permission(action):
    """Check model admin permission before executing handler.

    Must be stacked after @require_registered_model so model_admin is available.

    Usage:
        @require_registered_model
        @require_permission("view")
        async def handle_something(model_name, arguments, request, *, model, model_admin):
            ...
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(model_name, arguments, request, **kwargs):
            model_admin = kwargs.get("model_admin")
            if not await async_check_permission(request, model_admin, action):
                return json_response(
                    {
                        "error": f"Permission denied: cannot {action} {model_name}",
                        "code": "permission_denied",
                    }
                )
            return await fn(model_name, arguments, request, **kwargs)

        return wrapper

    return decorator
