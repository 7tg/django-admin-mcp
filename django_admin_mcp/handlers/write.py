"""
The write pipeline shared by create, update and the bulk handlers.

Follows ``ModelAdmin._changeform_view()`` step for step, so the hooks a
project overrides run for MCP writes exactly as they do for admin writes
(issue #118):

1. bind and validate the admin form (``get_form()``)
2. ``save_form()`` builds the unsaved object
3. bind and validate the inline formsets (``get_formset()``)
4. ``save_model()``
5. ``save_related()``: the form's many-to-many data, then each inline formset
   through ``save_formset()``

Steps 4 and 5 run in one transaction and only when every form and formset is
valid, so a parent and its inline rows are written together or not at all.
"""

from typing import Any

from django.db import models, transaction
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    build_admin_form,
    format_form_errors,
    get_admin_form_class,
    get_prepopulated_fields,
    get_readonly_field_names,
    normalize_fk_fields,
    reject_unconsumed_keys,
)
from django_admin_mcp.handlers.inlines import prepare_inline_formsets


class WriteRejected(Exception):
    """A write was refused before anything was saved; ``payload`` is the error response."""

    def __init__(self, payload: dict[str, Any]):
        super().__init__(payload.get("error", "Write rejected"))
        self.payload = payload


def save_through_admin(
    model: type[models.Model],
    model_admin: Any,
    request: HttpRequest,
    data: Any,
    obj: models.Model | None = None,
    inlines: Any = None,
) -> tuple[models.Model, dict[str, list] | None]:
    """
    Create (``obj`` is None) or update an object the way the admin change form does.

    Args:
        model: The Django model class.
        model_admin: The ModelAdmin instance (may be None: plain ModelForm save).
        request: HttpRequest handed to every admin hook.
        data: Field name -> value pairs supplied by the caller.
        obj: The instance to update, already permission-checked; None to create.
        inlines: Inline operations, ``{inline model name: [operation, ...]}``.

    Returns:
        ``(saved object, inline results)``; inline results are None when no
        inline operations were requested.

    Raises:
        WriteRejected: A key the form will not consume, a validation error, or
            any inline error. Nothing has been saved.
    """
    change = obj is not None
    if not isinstance(data, dict):
        raise WriteRejected({"error": "data must be an object"})

    # Normalize FK field names (convert field_id to field)
    normalized_data = normalize_fk_fields(model, data)
    form_class = get_admin_form_class(model, model_admin, request, obj=obj)
    # Sent values are shaped for the admin widgets; on update the fields the
    # caller did not send keep the instance's values (issues #114, #115)
    form = build_admin_form(
        form_class,
        normalized_data,
        instance=obj,
        prepopulated_fields=None if change else get_prepopulated_fields(model_admin, request),
    )

    # A key the form would ignore is an error, never a silent no-op
    rejected = reject_unconsumed_keys(form, normalized_data, get_readonly_field_names(model_admin, request, obj))
    if rejected:
        raise WriteRejected(rejected)

    if not form.is_valid():
        raise WriteRejected(
            {
                "error": "Validation failed",
                "code": "validation_error",
                "validation_errors": format_form_errors(form.errors),
            }
        )

    if model_admin is None:
        if inlines:
            raise WriteRejected({"error": "inlines require a registered ModelAdmin"})
        return form.save(), None

    new_obj = model_admin.save_form(request, form, change=change)
    inline_write = prepare_inline_formsets(new_obj, model_admin, inlines, request, change)
    if inline_write.errors:
        raise WriteRejected(
            {
                "error": "Inline operations failed; nothing was saved",
                "code": "inline_error",
                "inlines": {"errors": inline_write.errors},
            }
        )

    with transaction.atomic():
        model_admin.save_model(request, new_obj, form, change)
        model_admin.save_related(request, form, inline_write.formsets, change)

    return new_obj, inline_write.results() if inlines else None
