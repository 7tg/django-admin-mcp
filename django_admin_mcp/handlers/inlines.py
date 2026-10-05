"""
Inline (related-row) machinery for the CRUD handlers.

Serializes the rows of a parent object's admin inlines, and validates
inline writes into the admin's own formsets: per-operation permission
checks, InlineModelAdmin field restrictions, and min_num/max_num
enforcement. Saving is the caller's, through ``ModelAdmin.save_related()``.
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from django.core.exceptions import NON_FIELD_ERRORS
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.forms import ModelForm
from django.forms.formsets import (
    DELETION_FIELD_NAME,
    INITIAL_FORM_COUNT,
    MAX_NUM_FORM_COUNT,
    MIN_NUM_FORM_COUNT,
    ORDERING_FIELD_NAME,
    TOTAL_FORM_COUNT,
)
from django.forms.models import inlineformset_factory, modelform_factory
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    check_inline_permission,
    check_permission,
    format_form_errors,
    get_admin_queryset,
    get_prepopulated_fields,
    get_readonly_field_names,
    is_missing_id,
    normalize_fk_fields,
    reject_unconsumed_keys,
    resolve_registered_admin,
    safe_error_message,
    serialize_instance,
    shape_admin_form,
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


def _fallback_inline_form_class(inline_class, inline_model):
    """Build an inline's form class from its declared configuration alone."""
    # Deferred import: admin utils require the app registry to be ready
    from django.contrib.admin.utils import flatten  # noqa: PLC0415

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


def _instantiate_inline(inline_class, parent_admin):
    """Instantiate an InlineModelAdmin class, or return None when it cannot be."""
    # Deferred import: the admin site requires the app registry to be ready
    from django.contrib.admin.sites import site  # noqa: PLC0415

    try:
        return inline_class(parent_admin.model, getattr(parent_admin, "admin_site", site))
    except Exception:
        return None


def _build_inline_formset_class(inline_class, inline_model, parent_admin, request, parent_obj, inline=None):
    """
    Resolve the formset class the admin would use for an inline.

    The instantiated inline's ``get_formset()`` applies ``fields``,
    ``exclude``, ``readonly_fields`` (issue #105), the inline's own form and
    formset classes, and its permissions. When get_formset needs request
    context we don't have (e.g. no user on the synthetic request), fall back
    to a plain inline formset over a form built from the inline's declared
    configuration.
    """
    if inline is None:
        inline = _instantiate_inline(inline_class, parent_admin)
    if inline is not None:
        try:
            return inline.get_formset(request, parent_obj)
        except Exception:  # noqa: S110  (falls through to the declared-configuration formset)
            pass
    return inlineformset_factory(
        parent_admin.model,
        inline_model,
        form=_fallback_inline_form_class(inline_class, inline_model),
        fk_name=getattr(inline_class, "fk_name", None),
        extra=0,
        can_delete=True,
    )


# Keys of one inline operation: {"id": ..., "data": {...}, "_delete": bool}
_ROW_KEYS = frozenset({"id", "data", "_delete"})


@dataclass
class _Row:
    """One inline operation requested by the caller."""

    index: int
    op: str  # "add", "change" or "delete"
    item_id: Any
    data: dict[str, Any]
    instance: models.Model | None = None
    form: Any = None
    failed: bool = False


@dataclass
class InlineWrite:
    """
    The inline part of one parent write, validated and ready to save.

    ``formsets`` are bound admin formsets holding only the rows the caller
    named; hand them to ``ModelAdmin.save_related()``, which saves each one
    through ``save_formset()``. Nothing may be saved while ``errors`` is not
    empty.
    """

    formsets: list[Any] = dataclass_field(default_factory=list)
    errors: list[dict[str, Any]] = dataclass_field(default_factory=list)
    _rows: list[tuple[str, _Row]] = dataclass_field(default_factory=list)

    def results(self) -> dict[str, list]:
        """Report what the saved formsets did, in the caller's order per inline."""
        results: dict[str, list] = {"created": [], "updated": [], "deleted": [], "errors": []}
        for model_name, row in sorted(self._rows, key=lambda entry: entry[1].index):
            if row.op == "delete":
                results["deleted"].append({"model": model_name, "id": row.item_id})
            elif row.op == "change":
                results["updated"].append({"model": model_name, "id": row.item_id})
            elif row.form.instance.pk is not None and not row.form.instance._state.adding:
                results["created"].append({"model": model_name, "id": row.form.instance.pk})
        return results


def _inline_error(model_name: str | None, error: str, row: _Row | None = None, **extra: Any) -> dict[str, Any]:
    """One entry of the ``inlines.errors`` list."""
    entry: dict[str, Any] = {"model": model_name, "id": row.item_id if row else None}
    if row is not None:
        entry["index"] = row.index
        row.failed = True
    entry["error"] = error
    entry.update(extra)
    return entry


def _find_inline_row(queryset: models.QuerySet, item_id: Any) -> models.Model | None:
    """Look a row up by primary key; an id of the wrong type is simply not found."""
    try:
        return queryset.filter(pk=item_id).first()
    except (ValueError, TypeError, DjangoValidationError):
        return None


def _parse_inline_rows(
    items: list,
    model_name: str,
    inline_class: Any,
    admin: Any,
    request: HttpRequest,
    permission_obj: models.Model | None,
    existing: models.QuerySet,
    can_delete: bool,
    errors: list[dict[str, Any]],
) -> list[_Row]:
    """Turn the caller's operations into rows, checking shape, permission and ownership."""
    rows: list[_Row] = []
    seen: set[Any] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(
                {"model": model_name, "id": None, "index": index, "error": "Inline operation must be an object"}
            )
            continue

        item_id = item.get("id")
        delete = bool(item.get("_delete", False))
        has_id = not is_missing_id(item_id)
        row = _Row(index=index, op="delete" if delete else ("change" if has_id else "add"), item_id=item_id, data={})

        if "data" in item:
            stray = sorted(set(item) - _ROW_KEYS)
            if stray or not isinstance(item["data"], dict):
                message = f"Invalid key: {stray[0]}" if stray else "data must be an object"
                errors.append(_inline_error(model_name, message, row))
                continue
            row.data = dict(item["data"])
        else:
            row.data = dict(item)
        for key in ("id", "_delete"):
            row.data.pop(key, None)

        if delete and not has_id:
            errors.append(_inline_error(model_name, "id is required to delete", row))
            continue
        if delete and row.data:
            errors.append(_inline_error(model_name, "Cannot combine _delete with data", row))
            continue

        # Per-operation permission on the inline model
        if not check_inline_permission(inline_class, admin, request, permission_obj, row.op) or (
            delete and not can_delete
        ):
            errors.append(
                _inline_error(
                    model_name, f"Permission denied: cannot {row.op} {model_name}", row, code="permission_denied"
                )
            )
            continue

        if has_id:
            # Scoped to the parent so another parent's rows can't be reached by pk (issue #92)
            row.instance = _find_inline_row(existing, item_id)
            if row.instance is None:
                errors.append(
                    _inline_error(model_name, f"{model_name} not found for this parent", row, code="not_found")
                )
                continue
            if row.instance.pk in seen:
                errors.append(_inline_error(model_name, f"Duplicate operation for {model_name} {item_id}", row))
                continue
            seen.add(row.instance.pk)

        rows.append(row)
    return rows


def _check_inline_count(
    rows: list[_Row],
    model_name: str,
    inline: Any,
    inline_class: Any,
    request: HttpRequest,
    permission_obj: models.Model | None,
    existing_count: int,
) -> dict[str, Any] | None:
    """
    Enforce the inline's min_num/max_num on the resulting row count (issues #61, #62).

    The formset only holds the rows the caller named, so its own counting
    cannot see the rows left untouched; the count is checked here instead.
    """
    additions = sum(1 for row in rows if row.op == "add")
    deletions = sum(1 for row in rows if row.op == "delete")
    resulting_count = existing_count + additions - deletions

    if inline is not None:
        max_num = inline.get_max_num(request, permission_obj)
        min_num = inline.get_min_num(request, permission_obj)
    else:
        max_num = getattr(inline_class, "max_num", None)
        min_num = getattr(inline_class, "min_num", None)

    if max_num is not None and resulting_count > max_num:
        return _inline_error(
            model_name,
            f"Cannot have more than {max_num} {model_name} objects (would result in {resulting_count})",
            code="max_num_exceeded",
        )
    if min_num is not None and resulting_count < min_num:
        return _inline_error(
            model_name,
            f"Cannot have fewer than {min_num} {model_name} objects (would result in {resulting_count})",
            code="min_num_violated",
        )
    return None


def _bind_inline_formset(
    formset_class: Any, inline_model: Any, parent_obj: models.Model, rows: list[_Row]
) -> tuple[Any, set[str]]:
    """
    Bind the admin's formset to the caller's rows.

    Synthesises the POST data the admin change form would submit: the
    management form, then one form per row — existing rows first, as the
    formset expects, each identified by its hidden primary key — with
    ``DELETE`` set on the rows to remove. Rows the caller did not name are
    left out of the formset entirely, so they are neither validated nor
    saved.
    """
    rows.sort(key=lambda row: row.instance is None)  # stable: existing rows first
    initial = sum(1 for row in rows if row.instance is not None)
    prefix = formset_class.get_default_prefix()
    pk_name = inline_model._meta.pk.name
    reserved = {pk_name, DELETION_FIELD_NAME, ORDERING_FIELD_NAME}

    post: dict[str, Any] = {
        f"{prefix}-{TOTAL_FORM_COUNT}": len(rows),
        f"{prefix}-{INITIAL_FORM_COUNT}": initial,
        f"{prefix}-{MIN_NUM_FORM_COUNT}": 0,
        f"{prefix}-{MAX_NUM_FORM_COUNT}": 1000,
    }
    for position, row in enumerate(rows):
        row.data = normalize_fk_fields(inline_model, row.data)
        for key, value in row.data.items():
            # Bookkeeping fields are ours to fill: a caller-supplied DELETE
            # would bypass the delete permission check above
            if key not in reserved:
                post[f"{prefix}-{position}-{key}"] = value
        if row.instance is not None:
            post[f"{prefix}-{position}-{pk_name}"] = row.instance.pk
        if row.op == "delete":
            post[f"{prefix}-{position}-{DELETION_FIELD_NAME}"] = "on"

    formset = formset_class(
        data=post,
        instance=parent_obj,
        prefix=prefix,
        queryset=inline_model._default_manager.filter(pk__in=[row.instance.pk for row in rows if row.instance]),
    )
    # Counted over every row of the parent by _check_inline_count() instead
    formset.validate_min = False
    formset.validate_max = False
    for row, form in zip(rows, formset.forms, strict=True):
        row.form = form
    return formset, reserved


def _validate_inline_formset(
    formset: Any,
    rows: list[_Row],
    model_name: str,
    readonly_fields: set[str],
    reserved: set[str],
    prepopulated_fields: dict[str, Any],
    errors: list[dict[str, Any]],
) -> None:
    """Shape, key-check and validate each row's form, collecting every error."""
    for row in rows:
        form = row.form
        shape_admin_form(
            form, instance=row.instance, prepopulated_fields=prepopulated_fields if row.op == "add" else None
        )
        if row.op == "delete":
            continue
        # Reject readonly / undeclared fields instead of letting the form
        # silently drop them (issue #105)
        rejected = reject_unconsumed_keys(form, row.data, readonly_fields, skip_fields=tuple(reserved))
        if rejected:
            errors.append(_inline_error(model_name, rejected.pop("error"), row, **rejected))
        if row.op == "add":
            # A formset skips an extra form that looks untouched. The caller
            # asked for this row, so it is validated and saved regardless.
            form.empty_permitted = False
            form.has_changed = lambda: True

    formset.is_valid()

    for row in rows:
        if row.failed:
            continue
        if row.op == "delete":
            # The admin's inline form refuses to delete protected rows
            protect = getattr(row.form, "hand_clean_DELETE", None)
            try:
                if callable(protect):
                    protect()
            except DjangoValidationError as e:
                errors.append(_inline_error(model_name, " ".join(e.messages), row, code="protected"))
        elif row.form.errors:
            errors.append(
                _inline_error(
                    model_name, "Validation failed", row, validation_errors=format_form_errors(row.form.errors)
                )
            )

    non_form_errors = formset.non_form_errors()
    if non_form_errors:
        errors.append(
            _inline_error(
                model_name,
                "Validation failed",
                validation_errors=format_form_errors({NON_FIELD_ERRORS: list(non_form_errors)}),
            )
        )


def prepare_inline_formsets(
    parent_obj: models.Model,
    admin: Any,
    inlines_data: Any,
    request: HttpRequest,
    change: bool,
) -> InlineWrite:
    """
    Validate a parent's inline operations into bound admin formsets (issue #118).

    Mirrors ``ModelAdmin._create_formsets()`` + ``all_valid()``: the formsets
    come from each inline's ``get_formset()``, so the inline's form, formset
    class, ``fields`` / ``exclude`` / ``get_readonly_fields()`` (issue #105)
    and cross-row validation all apply. Nothing is written here. The caller
    saves through ``ModelAdmin.save_related()`` only when ``errors`` is empty,
    which makes the parent and its inline rows succeed or fail together.

    On top of the formset's own validation, each operation is checked against
    the inline's add/change/delete permission, existing rows are looked up
    within the parent (issue #92), and min_num/max_num are enforced on the
    resulting row count (issues #61, #62).

    Args:
        parent_obj: The parent instance; unsaved when ``change`` is False.
        admin: The parent's ModelAdmin.
        inlines_data: ``{inline model name: [operation, ...]}`` from the caller.
        request: HttpRequest with user for permission checking.
        change: True for an update, False for a create.

    Returns:
        InlineWrite with the formsets to save and any errors found.
    """
    write = InlineWrite()
    if not inlines_data:
        return write
    if not isinstance(inlines_data, dict):
        write.errors.append(_inline_error(None, "inlines must be an object mapping inline model names to lists"))
        return write

    # The admin hands its hooks the parent on change and None on add
    permission_obj = parent_obj if change else None
    get_inlines = getattr(admin, "get_inlines", None)
    inline_classes = get_inlines(request, permission_obj) if callable(get_inlines) else getattr(admin, "inlines", [])
    by_name: dict[str, Any] = {}
    for inline_class in inline_classes:
        if hasattr(inline_class, "model"):
            by_name.setdefault(inline_class.model._meta.model_name, inline_class)

    for model_name, items in inlines_data.items():
        inline_class = by_name.get(model_name)
        if inline_class is None:
            write.errors.append(_inline_error(model_name, f"Unknown inline: {model_name}", code="unknown_inline"))
            continue
        if not isinstance(items, list):
            write.errors.append(_inline_error(model_name, "Inline operations must be a list"))
            continue

        try:
            inline_model = inline_class.model
            inline = _instantiate_inline(inline_class, admin)
            formset_class = _build_inline_formset_class(
                inline_class, inline_model, admin, request, permission_obj, inline=inline
            )
            fk_name = formset_class.fk.name
            if change:
                existing = inline_model._default_manager.filter(**{fk_name: parent_obj})
            else:
                existing = inline_model._default_manager.none()

            rows = _parse_inline_rows(
                items,
                model_name,
                inline_class,
                admin,
                request,
                permission_obj,
                existing,
                bool(getattr(formset_class, "can_delete", False)),
                write.errors,
            )
            count_error = _check_inline_count(
                rows, model_name, inline, inline_class, request, permission_obj, existing.count()
            )
            if count_error:
                write.errors.append(count_error)

            formset, reserved = _bind_inline_formset(formset_class, inline_model, parent_obj, rows)
            if inline is not None:
                readonly_fields = get_readonly_field_names(inline, request, permission_obj)
                prepopulated_fields = get_prepopulated_fields(inline, request)
            else:
                declared = getattr(inline_class, "readonly_fields", None) or []
                readonly_fields = {entry for entry in declared if isinstance(entry, str)}
                prepopulated_fields = dict(getattr(inline_class, "prepopulated_fields", None) or {})
            _validate_inline_formset(
                formset, rows, model_name, readonly_fields, reserved, prepopulated_fields, write.errors
            )
        except Exception as e:
            write.errors.append(_inline_error(model_name, safe_error_message(e)))
            continue

        write.formsets.append(formset)
        write._rows.extend((model_name, row) for row in rows)

    return write
