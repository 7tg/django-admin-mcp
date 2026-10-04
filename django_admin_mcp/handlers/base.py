"""
Base handler utilities for django-admin-mcp.

This module provides shared utilities extracted from the mixin module
for use across handler implementations.
"""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.admin.sites import site
from django.contrib.messages.storage.base import BaseStorage
from django.core.exceptions import FieldDoesNotExist, FieldError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError, models
from django.db.models.fields.files import FieldFile
from django.forms import FileField as FileFormField
from django.forms import ModelForm, MultiWidget
from django.forms.models import model_to_dict, modelform_factory
from django.http import HttpRequest
from django.utils.datastructures import MultiValueDict
from django.utils.text import slugify
from pydantic import TypeAdapter

from django_admin_mcp.protocol.types import TextContent

logger = logging.getLogger("django_admin_mcp")

# Pydantic TypeAdapter for JSON serialization - reused across all json_response calls
_JSON_ADAPTER = TypeAdapter(dict[str, Any])


class MCPMessageStorage(BaseStorage):
    """
    In-memory messages storage for synthetic MCP requests (issue #100).

    Admin hooks commonly call ``ModelAdmin.message_user()``; without a storage
    on the request that raises ``MessageFailure`` and rolls back the write.
    Messages are collected in memory and discarded with the request.
    """

    def _get(self, *args, **kwargs):
        return [], True

    def _store(self, messages, response, *args, **kwargs):
        return []


def attach_messages_storage(request: HttpRequest) -> HttpRequest:
    """Give a synthetic request a messages storage so message_user() works."""
    request._messages = MCPMessageStorage(request)  # type: ignore[attr-defined]
    return request


class MCPRequest(HttpRequest):
    """
    Lightweight request object for MCP permission checks.

    Provides the minimal HttpRequest interface needed for Django admin
    permission methods without using test utilities.
    """

    def __init__(self, user=None):
        super().__init__()
        self.user = user
        self.method = "GET"
        self.path = "/"
        self.META = {"SCRIPT_NAME": ""}
        self.GET = {}
        self.POST = {}
        attach_messages_storage(self)


def json_response(data: dict) -> list[TextContent]:
    """
    Wrap response data in TextContent list.

    Args:
        data: Dictionary to serialize as JSON response.

    Returns:
        List containing a single TextContent with JSON-serialized data.
    """
    # Use Pydantic TypeAdapter for JSON serialization with better type safety.
    # fallback=str covers types pydantic can't serialize natively, notably
    # Django's lazy translation proxies (gettext_lazy verbose_names/fieldsets).
    json_bytes = _JSON_ADAPTER.dump_json(data, by_alias=True, fallback=str)
    return [TextContent(text=json_bytes.decode("utf-8"))]


def safe_error_message(exc: Exception) -> str:
    """Return a client-safe error message, logging the real error server-side."""
    logger.exception("Handler error: %s", exc)

    if isinstance(exc, DjangoValidationError):
        return "Validation error"
    if isinstance(exc, IntegrityError):
        return "Data integrity error: a constraint was violated"
    if isinstance(exc, FieldError):
        return "Invalid field in request"
    if isinstance(exc, OperationalError):
        return "A database error occurred"
    if isinstance(exc, ValueError | TypeError):
        return "Invalid input data"
    return "An internal error occurred"


# Key-name markers whose values are redacted from admin LogEntry messages.
SENSITIVE_KEY_MARKERS = ("password", "token", "secret", "api_key", "auth", "credential")


def _redact_sensitive(data: dict[str, Any], model_admin: Any = None) -> dict[str, Any]:
    """Replace values of sensitive-looking keys before audit logging.

    Fields hidden from MCP by the admin's visibility configuration are
    redacted too: history_* serves these messages to anyone with view
    permission, so a logged value would leak the hidden field.
    """
    redacted = {}
    for key, value in data.items():
        if any(marker in key.lower() for marker in SENSITIVE_KEY_MARKERS) or not is_field_visible(model_admin, key):
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _serialize_data_for_log(data: dict[str, Any], max_length: int = 500, model_admin: Any = None) -> str:
    """
    Serialize data for Django admin log message with size limit.

    Values of sensitive-looking keys (passwords, tokens, secrets, ...) and of
    fields hidden from MCP by ``model_admin`` are redacted so they never
    reach the audit trail.

    Args:
        data: Dictionary to serialize for logging.
        max_length: Maximum length of the serialized string (default 500).
        model_admin: Optional ModelAdmin whose hidden fields are redacted.

    Returns:
        Serialized JSON string, truncated if necessary with ellipsis.
    """
    adapter = TypeAdapter(dict[str, Any])
    data_json = adapter.dump_json(_redact_sensitive(data, model_admin), fallback=str).decode("utf-8")

    if len(data_json) > max_length:
        return data_json[: max_length - 3] + "..."

    return data_json


def _log_action(user: Any, obj: models.Model, action_flag: int, change_message: str = "") -> None:
    """
    Log an action to Django's admin LogEntry.

    Args:
        user: The Django User who performed the action.
        obj: The model instance that was affected.
        action_flag: ADDITION (1), CHANGE (2), or DELETION (3).
        change_message: Description of the change.
    """
    if user is None:
        return  # Can't log without a user

    # Deferred import: Django models require app registry to be ready
    from django.contrib.admin.models import LogEntry  # noqa: PLC0415
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    content_type = ContentType.objects.get_for_model(obj)

    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=content_type.pk,
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action_flag=action_flag,
        change_message=change_message,
    )


def sanitize_pydantic_errors(errors: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Strip internal details from Pydantic validation errors."""
    sanitized = []
    for error in errors:
        sanitized.append(
            {
                "field": ".".join(str(loc) for loc in error.get("loc", [])),
                "message": error.get("msg", "Invalid value"),
            }
        )
    return sanitized


def get_model_admin(model_name: str) -> tuple[type[models.Model] | None, Any | None]:
    """
    Find ModelAdmin by model name.

    Looks up the model in MCPAdminMixin._registered_models (populated at
    runtime when MCPAdminMixin-based admins are instantiated).

    Args:
        model_name: The lowercase model name to search for.

    Returns:
        Tuple of (Model, ModelAdmin) if found, or (None, None) if not found.
    """
    # First check MCPAdminMixin's registry (populated at runtime when admins are instantiated)
    # Late import to avoid circular dependency: mixin imports handlers, handlers need mixin
    from django_admin_mcp.mixin import MCPAdminMixin  # noqa: PLC0415

    if model_name in MCPAdminMixin._registered_models:
        info = MCPAdminMixin._registered_models[model_name]
        return info["model"], info.get("admin")

    return None, None


def validate_pagination(
    arguments: Mapping[str, Any],
    *,
    default_limit: int = 100,
    default_offset: int = 0,
) -> tuple[int, int, str | None]:
    """
    Validate and bound the limit/offset arguments of a paginated handler.

    Returns:
        (limit, offset, error): error is None when valid; limit is capped by
        MCP_MAX_LIST_LIMIT (issue #47) so no handler can be asked for an
        unbounded page (issue #94).
    """
    # Deferred import: settings access requires Django to be configured
    from django.conf import settings  # noqa: PLC0415

    limit = arguments.get("limit", default_limit)
    offset = arguments.get("offset", default_offset)
    if not isinstance(limit, int) or limit < 0:
        return 0, 0, "limit must be a non-negative integer"
    if not isinstance(offset, int) or offset < 0:
        return 0, 0, "offset must be a non-negative integer"
    max_limit = int(getattr(settings, "MCP_MAX_LIST_LIMIT", 1000))
    return min(limit, max_limit), offset, None


def is_missing_id(obj_id: Any) -> bool:
    """
    True when an id argument is absent (None or empty string).

    A falsy primary key like 0 is legitimate and must not be treated as
    missing (issue #110).
    """
    return obj_id is None or obj_id == ""


def resolve_registered_admin(model: type[models.Model]) -> Any | None:
    """
    Return the registered MCP admin for a model, or None.

    Guards against model_name collisions across apps / proxy mismatches by
    requiring the registered entry to share the model's concrete model.
    """
    registered_model, model_admin = get_model_admin(model._meta.model_name or "")
    if registered_model is not None and registered_model._meta.concrete_model is model._meta.concrete_model:
        return model_admin
    return None


def resolve_related_admin(model: type[models.Model]) -> Any | None:
    """
    Return the admin that governs access to a related model, or None.

    Prefers the MCP-registered admin and falls back to the default admin
    site's registration, so models reached through a relation are still
    subject to their admin's permissions and field configuration even when
    they were never exposed to MCP themselves.
    """
    model_admin = resolve_registered_admin(model)
    if model_admin is not None:
        return model_admin
    return site._registry.get(model)


def check_related_view_permission(request: HttpRequest, related_admin: Any | None) -> bool:
    """
    Check view permission on a model reached through a relation.

    Fails closed: a related model without any admin has no permission
    surface to consult, so its rows are not served.
    """
    # If no user is set on request, skip permission checks (backwards compat)
    if getattr(request, "user", None) is None:
        return True
    if related_admin is None:
        return False
    return check_permission(request, related_admin, "view")


class OperationDenied(Exception):
    """An operation was refused after its target objects were resolved."""

    def __init__(self, error: str, code: str = "permission_denied"):
        super().__init__(error)
        self.payload = {"error": error, "code": code}


def check_object_permission(request: HttpRequest, model_admin: Any, action: str, obj: models.Model) -> bool:
    """
    Check Django admin object-level permission for action.

    The admin's change/delete/detail views call ``has_*_permission(request,
    obj)`` with the target row; admins that restrict access per object rely
    on that call, so row handlers must make it too.
    """
    if model_admin is None or getattr(request, "user", None) is None:
        return True

    method_name = {
        "view": "has_view_permission",
        "change": "has_change_permission",
        "delete": "has_delete_permission",
    }[action]
    return bool(getattr(model_admin, method_name)(request, obj))


def require_object_permission(
    request: HttpRequest, model_admin: Any, action: str, obj: models.Model, model_name: str
) -> None:
    """Raise OperationDenied unless the object-level permission is granted."""
    if not check_object_permission(request, model_admin, action, obj):
        raise OperationDenied(f"Permission denied: cannot {action} {model_name}")


def require_deletable(request: HttpRequest, model_admin: Any, objs: Any, model_name: str) -> None:
    """
    Raise OperationDenied unless the admin's delete views would delete objs.

    Mirrors ``delete_view`` / ``delete_selected``: deletion is refused when
    the cascade reaches related objects the user may not delete, or objects
    protected by ``on_delete=PROTECT``.
    """
    if model_admin is None or getattr(request, "user", None) is None:
        return

    for obj in objs:
        require_object_permission(request, model_admin, "delete", obj, model_name)

    _deleted, _counts, perms_needed, protected = model_admin.get_deleted_objects(objs, request)
    if perms_needed:
        names = ", ".join(sorted(str(name) for name in perms_needed))
        raise OperationDenied(
            f"Permission denied: deleting {model_name} would also delete related objects you cannot delete ({names})"
        )
    if protected:
        raise OperationDenied(f"Cannot delete {model_name}: protected related objects reference it", code="protected")


def create_mock_request(user=None) -> HttpRequest:
    """
    Create a mock request object for permission checking.

    Args:
        user: Django User instance or None.

    Returns:
        HttpRequest with user set (None if not provided).
    """
    return MCPRequest(user)


def check_permission(request: HttpRequest, model_admin: Any, action: str) -> bool:
    """
    Check Django admin permission for action (synchronous version).

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    if model_admin is None:
        return True  # No admin = no permission restrictions

    # If no user is set on request, skip permission checks (backwards compat)
    user = getattr(request, "user", None)
    if user is None:
        return True

    permission_methods = {
        "view": "has_view_permission",
        "add": "has_add_permission",
        "change": "has_change_permission",
        "delete": "has_delete_permission",
    }

    method_name = permission_methods.get(action)
    if not method_name:
        return True  # Unknown action = allow by default

    permission_method = getattr(model_admin, method_name, None)
    if permission_method and callable(permission_method):
        return permission_method(request)

    return True


async def async_check_permission(request: HttpRequest, model_admin: Any, action: str) -> bool:
    """
    Check Django admin permission for action (async version).

    Wraps the synchronous permission check to be safe in async context.

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    return await sync_to_async(check_permission)(request, model_admin, action)


def check_module_permission(request: HttpRequest, model_admin: Any) -> bool:
    """
    Check Django admin module-level permission (synchronous version).

    Mirrors the admin index behavior: a ModelAdmin whose
    ``has_module_permission()`` returns False is hidden entirely.

    Args:
        request: HttpRequest with user set.
        model_admin: The ModelAdmin instance to check permissions against.

    Returns:
        True if the module is visible to the user, False otherwise.
    """
    if model_admin is None:
        return True  # No admin = no permission restrictions

    # If no user is set on request, skip permission checks (backwards compat)
    user = getattr(request, "user", None)
    if user is None:
        return True

    permission_method = getattr(model_admin, "has_module_permission", None)
    if permission_method and callable(permission_method):
        return bool(permission_method(request))

    return True


async def async_check_module_permission(request: HttpRequest, model_admin: Any) -> bool:
    """Async wrapper around check_module_permission for use in handlers."""
    return await sync_to_async(check_module_permission)(request, model_admin)


def get_exposed_models() -> list[tuple[str, Any]]:
    """
    Get all models registered via MCPAdminMixin that have mcp_expose=True.

    Returns:
        List of (model_name, model_admin) tuples for exposed models.
    """
    from django_admin_mcp.mixin import MCPAdminMixin  # noqa: PLC0415

    return [
        (name, info.get("admin"))
        for name, info in MCPAdminMixin._registered_models.items()
        if getattr(info.get("admin"), "mcp_expose", False)
    ]


def resolve_field_visibility(model_admin: Any) -> tuple[list | None, list | None]:
    """
    Resolve the (include, exclude) field name lists for a ModelAdmin.

    Resolution order (shared by serialization and every schema surface,
    issue #102):
    1. mcp_fields: MCP-specific list of fields to include (takes precedence)
    2. mcp_exclude_fields: MCP-specific list of fields to exclude (takes precedence)
    3. fields: Django admin's fields list (fallback if mcp_fields not set)
    4. exclude: Django admin's exclude list (fallback if mcp_exclude_fields not set)

    Grouped (tupled) entries — a valid admin layout choice like
    ``fields = [("name", "email")]`` — are flattened so name comparisons
    against them work (issue #107).

    Returns:
        Tuple of (fields_to_include, fields_to_exclude); each is None when
        no configuration applies.
    """
    # Deferred import: admin utils require the app registry to be ready
    from django.contrib.admin.utils import flatten  # noqa: PLC0415

    fields_to_include = None
    fields_to_exclude = None

    if model_admin is not None:
        if hasattr(model_admin, "mcp_fields") and model_admin.mcp_fields is not None:
            fields_to_include = model_admin.mcp_fields
        elif hasattr(model_admin, "fields") and model_admin.fields is not None:
            fields_to_include = model_admin.fields

        if hasattr(model_admin, "mcp_exclude_fields") and model_admin.mcp_exclude_fields is not None:
            fields_to_exclude = model_admin.mcp_exclude_fields
        elif hasattr(model_admin, "exclude") and model_admin.exclude is not None:
            fields_to_exclude = model_admin.exclude

    if fields_to_include is not None:
        fields_to_include = flatten(fields_to_include)
    if fields_to_exclude is not None:
        fields_to_exclude = flatten(fields_to_exclude)

    return fields_to_include, fields_to_exclude


def is_field_visible(model_admin: Any, field_name: str) -> bool:
    """True when ``resolve_field_visibility()`` leaves the field exposed to MCP."""
    fields_to_include, fields_to_exclude = resolve_field_visibility(model_admin)
    if fields_to_exclude is not None and field_name in fields_to_exclude:
        return False
    return fields_to_include is None or field_name in fields_to_include


def serialize_instance(instance: models.Model, model_admin: Any = None) -> dict:
    """
    Serialize a Django model instance to dict with field filtering.

    Field visibility follows ``resolve_field_visibility()`` (mcp_fields /
    mcp_exclude_fields with admin fields/exclude fallbacks). Field filtering
    prevents sensitive data exposure in MCP responses.

    When ``model_admin`` is omitted, looks up the registered MCP admin for the
    instance's model so list/related/inline call sites still apply excludes.

    Fields defined with ``choices`` additionally get a ``<name>_display``
    sidecar carrying their human-readable label (issue #113). Sidecars are
    only added for fields that survived visibility filtering, and never
    shadow a real model field of the same name.

    Args:
        instance: The Django model instance to serialize.
        model_admin: Optional ModelAdmin with field configuration.

    Returns:
        Dictionary representation of the model instance with filtered fields.
    """
    if model_admin is None:
        model_admin = resolve_registered_admin(type(instance))

    fields_to_include, fields_to_exclude = resolve_field_visibility(model_admin)

    # Use model_to_dict with fields/exclude parameters
    obj_dict = model_to_dict(instance, fields=fields_to_include, exclude=fields_to_exclude)

    # Convert non-serializable fields
    serialized = {}
    for key, value in obj_dict.items():
        if isinstance(value, models.Model):
            # Related object - convert to PK
            serialized[key] = value.pk
        elif isinstance(value, list | models.QuerySet):
            # M2M fields - convert to list of PKs
            serialized[key] = [item.pk if isinstance(item, models.Model) else item for item in value]
        elif isinstance(value, FieldFile):
            # FileField/ImageField - .name is JSON-safe; .url raises ValueError when empty
            serialized[key] = value.name or ""
        else:
            serialized[key] = value

    # Choice fields: attach "<name>_display" label sidecars (issue #113).
    # Only fields already present survived visibility filtering, so hidden
    # fields can never leak through their label.
    model_field_names = {f.name for f in instance._meta.get_fields()}
    for field in instance._meta.concrete_fields:
        if field.is_relation or not field.choices or field.name not in serialized:
            continue
        display_key = f"{field.name}_display"
        # A real model field of the same name always wins
        if display_key in serialized or display_key in model_field_names:
            continue
        serialized[display_key] = getattr(instance, f"get_{field.name}_display")()

    return serialized


def get_model_name(model: type[models.Model]) -> str:
    """
    Get lowercase model name from model class.

    Args:
        model: Django model class.

    Returns:
        The lowercase model name from model._meta.model_name.
    """
    # model_name is always a string for concrete models
    return model._meta.model_name or ""


def get_admin_queryset(
    model: type[models.Model],
    model_admin: Any | None,
    request: HttpRequest,
) -> models.QuerySet:
    """
    Return the queryset MCP handlers should use for a model's row lookups.

    By default this mirrors Django admin changelists by calling
    ``model_admin.get_queryset(request)``. Set ``mcp_use_admin_queryset = False``
    on the ModelAdmin to fall back to ``model.objects.all()``.

    Security scoping in ``get_queryset`` should key off the user / permissions
    on ``request``, not changelist URL shape — MCP requests use a synthetic path.
    """
    if model_admin is None:
        return model.objects.all()  # type: ignore[attr-defined]
    if getattr(model_admin, "mcp_use_admin_queryset", True) is False:
        return model.objects.all()  # type: ignore[attr-defined]
    return model_admin.get_queryset(request)


def get_admin_form_class(
    model: type[models.Model],
    model_admin: Any,
    request: HttpRequest,
    obj: models.Model | None = None,
) -> type:
    """
    Get the form class to use for a model.

    Uses ModelAdmin's get_form() method if available, which respects
    the admin's form, fields, exclude, and readonly_fields attributes.
    Falls back to modelform_factory for auto-generated form.

    Args:
        model: The Django model class.
        model_admin: The ModelAdmin instance (may be None).
        request: HttpRequest for form customization.
        obj: Existing instance for update operations (None for create).

    Returns:
        Form class to use for validation.
    """
    if model_admin is not None:
        # Check if request.user is valid (has has_perm method)
        user = getattr(request, "user", None)
        if user is not None and hasattr(user, "has_perm"):
            try:
                return model_admin.get_form(request, obj=obj)
            except (AttributeError, TypeError):
                # Fall back if get_form fails
                pass

        # If ModelAdmin has a custom form class, use it directly
        form_class = getattr(model_admin, "form", None)
        if form_class is not None:
            if form_class is not ModelForm and issubclass(form_class, ModelForm):
                return form_class

    return modelform_factory(model, fields="__all__")


def _field_was_sent(field: Any, data: dict, key: str) -> bool:
    """Whether the caller supplied a value for a form field, under any key its widget reads."""
    if key in data:
        return True
    widget = field.widget
    if isinstance(widget, MultiWidget):
        return not widget.value_omitted_from_data(data, MultiValueDict(), key)
    # Widgets reading keys of their own (e.g. SelectDateWidget). Checkbox-style
    # widgets answer False for "absent", which is not a caller-supplied value.
    value = widget.value_from_datadict(data, MultiValueDict(), key)
    return value is not None and value is not False


def _split_for_multiwidget(form: Any, name: str, field: Any, value: Any) -> list:
    """
    Turn one caller-supplied value into the per-subwidget values of a MultiWidget.

    The model field parses the value (e.g. an ISO 8601 string into a datetime)
    and the widget's own ``decompress()`` splits it, so this works for any
    MultiWidget rather than only ``AdminSplitDateTime``. A value that cannot be
    parsed is handed to every subwidget so the form reports the format error.
    """
    widget = field.widget
    size = len(widget.widgets)
    if isinstance(value, (list, tuple)) and len(value) == size:
        return list(value)
    try:
        model = getattr(getattr(form, "_meta", None), "model", None)
        if model is not None:
            try:
                value = model._meta.get_field(name).to_python(value)
            except FieldDoesNotExist:
                pass
        parts = list(widget.decompress(value))
    except Exception:
        return [value] * size
    return parts if len(parts) == size else [value] * size


def _shape_sent_value(form: Any, name: str, field: Any, data: dict, key: str) -> None:
    """Rewrite a caller-supplied value into the shape the field's widget reads from POST data."""
    value = data.get(key)
    if value is None:
        # Sent through the widget's own keys, or an explicit null
        return
    widget = field.widget
    if isinstance(widget, MultiWidget):
        suffixes = getattr(widget, "widgets_names", None) or [f"_{i}" for i in range(len(widget.widgets))]
        del data[key]
        for suffix, part in zip(suffixes, _split_for_multiwidget(form, name, field, value), strict=True):
            data[key + suffix] = part
    elif not isinstance(value, str):
        # Python value -> widget value (e.g. JSONField dumps a dict, so that an
        # empty container is not mistaken for an empty submission)
        data[key] = field.prepare_value(value)


def _keep_stored_value(field: Any) -> None:
    """
    Make an update form field keep the instance's value instead of reading POST data.

    A disabled field is cleaned from the form's initial value — the instance's
    Python value — so the widget never has to round-trip it. It is not the
    caller's to fill in, so ``required`` is lifted, and the widget's display
    precision does not apply to a value that is not displayed.
    """
    if isinstance(field, FileFormField):
        # Without an upload a file field already cleans to its initial value;
        # disabling it would make Django open the stored file to validate it.
        return
    field.disabled = True
    field.required = False
    field.widget.supports_microseconds = True


def get_prepopulated_fields(model_admin: Any, request: HttpRequest) -> dict[str, Any]:
    """Return the admin's ``prepopulated_fields`` for an add form ({} without an admin)."""
    if model_admin is None:
        return {}
    try:
        return dict(model_admin.get_prepopulated_fields(request))
    except Exception:
        return dict(getattr(model_admin, "prepopulated_fields", None) or {})


def _prepopulate(form: Any, data: dict, prepopulated_fields: Mapping[str, Any]) -> None:
    """
    Fill omitted or empty prepopulated fields from their source fields (issue #115).

    The admin does this in the browser; here the caller-supplied source values
    are slugified, joined, and trimmed to the target field's max_length.
    """
    for target, sources in prepopulated_fields.items():
        field = form.fields.get(target)
        key = form.add_prefix(target)
        if field is None or data.get(key) not in (None, ""):
            continue
        values = [data.get(form.add_prefix(source)) for source in sources]
        text = " ".join(str(value) for value in values if value not in (None, ""))
        slug = slugify(text, allow_unicode=getattr(field, "allow_unicode", False))
        max_length = getattr(field, "max_length", None)
        if max_length:
            slug = slug[:max_length].rstrip("-_")
        if slug:
            data[key] = slug


def build_admin_form(
    form_class: type,
    data: dict,
    instance: models.Model | None = None,
    prepopulated_fields: Mapping[str, Any] | None = None,
) -> Any:
    """
    Bind an admin form to API-shaped data (issues #114, #115).

    ``data`` maps field names to JSON values, which is not the POST shape admin
    widgets read: ``AdminSplitDateTime`` reads ``<name>_0``/``<name>_1``, and
    form fields treat empty Python containers as "nothing submitted". Rather
    than patching each type, this works through the form's own fields:

    - fields the caller sent are reshaped for their widget: a single value is
      split across a ``MultiWidget`` by the widget's ``decompress()``, other
      non-string values go through the field's ``prepare_value()``;
    - on update (``instance`` given), every field the caller did not send is
      disabled, so Django cleans it from the instance's value and the update
      changes only the fields that were sent;
    - on create, ``prepopulated_fields`` targets left out or empty are derived
      from their sources, and every other omitted field that has an initial
      value (the model default) is submitted with it, as the admin add form
      does. Such a default is validated like any submitted value.

    Args:
        form_class: ModelForm class, typically from ``get_admin_form_class()``.
        data: Field name -> value pairs supplied by the caller.
        instance: Existing object for updates, None for creates.
        prepopulated_fields: Admin ``prepopulated_fields`` mapping, used on create.

    Returns:
        A bound, not yet validated form instance.
    """
    post = dict(data)
    form = form_class(data=post) if instance is None else form_class(data=post, instance=instance)
    form.data = post

    if instance is None and prepopulated_fields:
        _prepopulate(form, post, prepopulated_fields)

    for name, field in form.fields.items():
        key = form.add_prefix(name)
        if _field_was_sent(field, post, key):
            _shape_sent_value(form, name, field, post, key)
        elif instance is not None:
            _keep_stored_value(field)
        elif form.get_initial_for_field(field, name) is not None:
            # Omitted on create: a disabled field is cleaned from its initial
            # value, i.e. the model default (issue #115)
            field.disabled = True

    return form


def normalize_fk_fields(model: type[models.Model], data: dict) -> dict:
    """
    Normalize foreign key field names for form compatibility.

    Converts field_id (database column names) to field (model field names)
    for foreign key fields, enabling backward compatibility with clients
    that use the _id suffix.

    Args:
        model: The Django model class.
        data: Dictionary of field:value pairs.

    Returns:
        New dictionary with normalized field names.
    """
    # Get FK field names and their db column names
    fk_fields = {}
    for field in model._meta.get_fields():
        if hasattr(field, "attname") and hasattr(field, "name"):
            # FK fields have attname like 'author_id' and name like 'author'
            if field.attname != field.name:
                fk_fields[field.attname] = field.name

    # Normalize the data
    normalized = {}
    for key, value in data.items():
        if key in fk_fields:
            # Convert field_id to field
            normalized[fk_fields[key]] = value
        else:
            normalized[key] = value

    return normalized


def format_form_errors(form_errors: dict) -> dict:
    """
    Format Django form errors into a structured JSON-serializable format.

    Args:
        form_errors: The form.errors dictionary (ErrorDict).

    Returns:
        Dictionary with:
        - errors: list of error dicts with 'field' and 'messages' keys
        - error_count: total number of errors
        - fields_with_errors: list of field names that have errors
    """
    errors_list = []
    for field, messages in form_errors.items():
        errors_list.append(
            {
                "field": field,
                "messages": [str(msg) for msg in messages],
            }
        )

    return {
        "errors": errors_list,
        "error_count": sum(len(e["messages"]) for e in errors_list),
        "fields_with_errors": list(form_errors.keys()),
    }


def check_inline_permission(
    inline_class: type,
    parent_admin: Any,
    request: HttpRequest,
    parent_obj: models.Model,
    action: str,
) -> bool:
    """
    Check permission for inline operations (synchronous version).

    Instantiates the inline class and calls its permission methods.
    Inline permission methods take the parent object as context.

    Args:
        inline_class: The inline class from parent_admin.inlines.
        parent_admin: The parent ModelAdmin instance.
        request: HttpRequest with user set.
        parent_obj: The parent model instance being edited.
        action: One of 'view', 'add', 'change', 'delete'.

    Returns:
        True if permission granted, False otherwise.
    """
    if inline_class is None or parent_admin is None:
        return True

    # If no user is set on request, skip permission checks (backwards compat)
    user = getattr(request, "user", None)
    if user is None:
        return True

    permission_methods = {
        "view": "has_view_permission",
        "add": "has_add_permission",
        "change": "has_change_permission",
        "delete": "has_delete_permission",
    }

    method_name = permission_methods.get(action)
    if not method_name:
        return True

    try:
        # Instantiate the inline class with parent model and admin site
        inline_instance = inline_class(parent_admin.model, site)
        permission_method = getattr(inline_instance, method_name, None)
        if permission_method and callable(permission_method):
            # Inline permission methods take (request, obj) where obj is parent
            return permission_method(request, parent_obj)
    except Exception:
        # If instantiation or permission check fails, deny access for safety
        return False

    return True
