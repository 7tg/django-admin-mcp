"""
Inline (related-row) machinery for the CRUD handlers.

Serializes, validates, and writes the rows of a parent object's admin
inlines: per-operation permission checks, InlineModelAdmin field
restrictions, and min_num/max_num enforcement.
"""

from typing import Any

from django.db import models
from django.forms import ModelForm
from django.forms.models import modelform_factory
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    build_admin_form,
    check_inline_permission,
    check_permission,
    format_form_errors,
    get_admin_queryset,
    resolve_registered_admin,
    safe_error_message,
    serialize_instance,
)


def _get_inline_data(obj: models.Model, admin: Any, request: HttpRequest) -> dict[str, list[dict[str, Any]]]:
    """
    Get inline related objects for a model instance.

    Inlines the requesting user may not view are omitted — per the inline's
    own ``has_view_permission`` and, when the inline model has a registered
    admin, that admin's too — and rows come from the registered admin's
    queryset scope (issue #91). Rows of inline models without a registered
    admin are serialized under the inline's ``fields``/``exclude``.

    Args:
        obj: The parent model instance.
        admin: The ModelAdmin instance with inline definitions.
        request: HttpRequest with user for permission checking.

    Returns:
        Dictionary mapping inline model names to list of serialized instances.
    """
    inlines_data: dict[str, list] = {}

    if not admin:
        return inlines_data

    inlines = getattr(admin, "inlines", [])
    for inline_class in inlines:
        if not hasattr(inline_class, "model"):
            continue

        inline_model = inline_class.model
        fk_name = getattr(inline_class, "fk_name", None)

        # Omit inlines the user may not view (issue #91)
        inline_admin = resolve_registered_admin(inline_model)
        if not check_inline_permission(inline_class, admin, request, obj, "view"):
            continue
        if not check_permission(request, inline_admin, "view"):
            continue

        # Find the FK field that points to our parent model
        fk_field = None
        for field in inline_model._meta.get_fields():
            if hasattr(field, "related_model") and field.related_model is type(obj):
                if fk_name is None or field.name == fk_name:
                    fk_field = field
                    break

        if fk_field:
            # Get related objects within the inline admin's queryset scope
            related_name = fk_field.name
            filter_kwargs = {related_name: obj}
            related_objects = get_admin_queryset(inline_model, inline_admin, request).filter(**filter_kwargs)
            inlines_data[inline_model._meta.model_name] = [
                serialize_instance(related_obj, inline_admin or inline_class) for related_obj in related_objects
            ]

    return inlines_data


def _build_inline_form_class(inline_class, inline_model, parent_admin, request, parent_obj):
    """
    Resolve the form class for an inline, honoring its field configuration.

    Mirrors Django's formset construction: the instantiated inline's
    ``get_formset()`` applies ``fields``, ``exclude``, and ``readonly_fields``
    (issue #105). When get_formset needs request context we don't have (e.g.
    no user on the synthetic request), fall back to a modelform_factory form
    built from the inline's declared configuration.
    """
    # Deferred import: admin utils require the app registry to be ready
    from django.contrib.admin.sites import site  # noqa: PLC0415
    from django.contrib.admin.utils import flatten  # noqa: PLC0415

    try:
        inline_instance = inline_class(parent_admin.model, getattr(parent_admin, "admin_site", site))
        return inline_instance.get_formset(request, parent_obj).form
    except Exception:
        custom_form = getattr(inline_class, "form", None)
        if custom_form is not None and custom_form is not ModelForm:
            return custom_form
        readonly = [f for f in (getattr(inline_class, "readonly_fields", None) or []) if isinstance(f, str)]
        exclude = list(getattr(inline_class, "exclude", None) or []) + readonly
        declared = getattr(inline_class, "fields", None)
        if declared:
            allowed = [f for f in flatten(declared) if f not in exclude]
            return modelform_factory(inline_model, fields=allowed)
        return modelform_factory(inline_model, fields="__all__", exclude=exclude or None)


def _invalid_inline_keys(item_data, form_class, readonly_fields, fk_name):
    """
    Split an inline item's data keys into readonly and unknown violations.

    Keys outside the inline form's fields must be rejected — not silently
    dropped by the form — matching the top-level update guards (issue #105).
    """
    allowed = set(form_class.base_fields) | {fk_name, "id", "_delete"}
    readonly_attempted = sorted(k for k in item_data if k in readonly_fields)
    unknown = [k for k in item_data if k not in allowed and k not in readonly_fields]
    return readonly_attempted, unknown


def _update_inlines(
    obj: models.Model,
    admin: Any,
    inlines_data: dict[str, list],
    request: HttpRequest,
) -> dict[str, Any]:
    """
    Update inline related objects for a model instance with form validation.

    Uses the inline's form class for validation when available, otherwise
    falls back to auto-generated ModelForm. Checks permissions on the inline
    model for each operation (add, change, delete).

    Args:
        obj: The parent model instance.
        admin: The ModelAdmin instance with inline definitions.
        inlines_data: Dictionary of inline updates per model.
        request: HttpRequest with user for permission checking.

    Returns:
        Results dictionary with created, updated, deleted, and errors lists.
    """
    results: dict[str, list] = {"created": [], "updated": [], "deleted": [], "errors": []}

    if not admin or not inlines_data:
        return results

    inlines = getattr(admin, "inlines", [])
    for inline_class in inlines:
        if not hasattr(inline_class, "model"):
            continue

        inline_model = inline_class.model
        inline_model_name = inline_model._meta.model_name

        if inline_model_name not in inlines_data:
            continue

        # Find the FK field
        fk_field = None
        for field in inline_model._meta.get_fields():
            if hasattr(field, "related_model") and field.related_model is type(obj):
                fk_field = field
                break

        if not fk_field:
            continue

        # Enforce InlineModelAdmin min_num/max_num on the resulting object count,
        # mirroring formset validation in the Django admin (issues #61, #62)
        inline_items = inlines_data[inline_model_name]
        existing_count = inline_model.objects.filter(**{fk_field.name: obj}).count()
        additions = sum(1 for item in inline_items if not item.get("id") and not item.get("_delete", False))
        deletions = sum(1 for item in inline_items if item.get("id") and item.get("_delete", False))
        resulting_count = existing_count + additions - deletions

        max_num = getattr(inline_class, "max_num", None)
        if max_num is not None and resulting_count > max_num:
            results["errors"].append(
                {
                    "model": inline_model_name,
                    "id": None,
                    "error": (
                        f"Cannot have more than {max_num} {inline_model_name} objects "
                        f"(would result in {resulting_count})"
                    ),
                    "code": "max_num_exceeded",
                }
            )
            continue

        min_num = getattr(inline_class, "min_num", None)
        if min_num is not None and resulting_count < min_num:
            results["errors"].append(
                {
                    "model": inline_model_name,
                    "id": None,
                    "error": (
                        f"Cannot have fewer than {min_num} {inline_model_name} objects "
                        f"(would result in {resulting_count})"
                    ),
                    "code": "min_num_violated",
                }
            )
            continue

        # Get the form class for the inline, honoring the inline admin's
        # fields / exclude / readonly_fields configuration (issue #105)
        inline_form_class = _build_inline_form_class(inline_class, inline_model, admin, request, obj)
        readonly_fields = {f for f in (getattr(inline_class, "readonly_fields", None) or []) if isinstance(f, str)}

        for item in inline_items:
            try:
                item_id = item.get("id")
                item_data = item.get("data", item)
                delete = item.get("_delete", False)

                if delete and item_id:
                    # Check delete permission on inline model
                    if not check_inline_permission(inline_class, admin, request, obj, "delete"):
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"Permission denied: cannot delete {inline_model_name}",
                                "code": "permission_denied",
                            }
                        )
                        continue

                    # Delete existing inline — scoped to the parent so another
                    # parent's children can't be deleted by pk (issue #92)
                    deleted_count, _ = inline_model.objects.filter(pk=item_id, **{fk_field.name: obj}).delete()
                    if deleted_count:
                        results["deleted"].append({"model": inline_model_name, "id": item_id})
                    else:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"{inline_model_name} not found for this parent",
                                "code": "not_found",
                            }
                        )
                elif item_id:
                    # Check change permission on inline model
                    if not check_inline_permission(inline_class, admin, request, obj, "change"):
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"Permission denied: cannot change {inline_model_name}",
                                "code": "permission_denied",
                            }
                        )
                        continue

                    # Update existing inline with form validation — scoped to
                    # the parent (issue #92)
                    try:
                        inline_obj = inline_model.objects.get(pk=item_id, **{fk_field.name: obj})
                    except inline_model.DoesNotExist:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"{inline_model_name} not found for this parent",
                                "code": "not_found",
                            }
                        )
                        continue

                    # Reject readonly / undeclared fields instead of letting the
                    # form silently drop them (issue #105)
                    update_data = {k: v for k, v in item_data.items() if k not in ["id", "_delete"]}
                    readonly_attempted, unknown = _invalid_inline_keys(
                        update_data, inline_form_class, readonly_fields, fk_field.name
                    )
                    if readonly_attempted:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"Cannot update readonly fields: {', '.join(readonly_attempted)}",
                                "readonly_fields": readonly_attempted,
                            }
                        )
                        continue
                    if unknown:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": f"Invalid field: {unknown[0]}",
                            }
                        )
                        continue

                    # Fields the caller did not send keep the row's values (issue #114)
                    form = build_admin_form(inline_form_class, update_data, instance=inline_obj)
                    if form.is_valid():
                        form.save()
                        results["updated"].append({"model": inline_model_name, "id": item_id})
                    else:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": item_id,
                                "error": "Validation failed",
                                "validation_errors": format_form_errors(form.errors),
                            }
                        )
                else:
                    # Check add permission on inline model
                    if not check_inline_permission(inline_class, admin, request, obj, "add"):
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": None,
                                "error": f"Permission denied: cannot add {inline_model_name}",
                                "code": "permission_denied",
                            }
                        )
                        continue

                    # Create new inline with form validation
                    create_data = {k: v for k, v in item_data.items() if k not in ["id", "_delete"]}
                    readonly_attempted, unknown = _invalid_inline_keys(
                        create_data, inline_form_class, readonly_fields, fk_field.name
                    )
                    if readonly_attempted:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": None,
                                "error": f"Cannot update readonly fields: {', '.join(readonly_attempted)}",
                                "readonly_fields": readonly_attempted,
                            }
                        )
                        continue
                    if unknown:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": None,
                                "error": f"Invalid field: {unknown[0]}",
                            }
                        )
                        continue

                    create_data[fk_field.name] = obj.pk  # Set FK to parent

                    form = build_admin_form(inline_form_class, create_data)
                    # Formset-derived forms exclude the parent FK; set it on the
                    # instance so saving still attaches to the parent
                    setattr(form.instance, fk_field.name, obj)
                    if form.is_valid():
                        new_obj = form.save()
                        results["created"].append({"model": inline_model_name, "id": new_obj.pk})
                    else:
                        results["errors"].append(
                            {
                                "model": inline_model_name,
                                "id": None,
                                "error": "Validation failed",
                                "validation_errors": format_form_errors(form.errors),
                            }
                        )
            except Exception as e:
                results["errors"].append(
                    {
                        "model": inline_model_name,
                        "id": item.get("id"),
                        "error": safe_error_message(e),
                    }
                )

    return results
