"""
List filter resolution for django-admin-mcp.

Turns the ``filters`` argument of ``list_*`` into queryset operations that
mirror what the admin changelist offers (issue #116):

- lookups on the model's own MCP-visible fields;
- relation paths the ModelAdmin declares in ``list_filter`` / ``date_hierarchy``;
- ``SimpleListFilter`` subclasses, addressed by their ``parameter_name``.

Everything else is rejected with an explicit error (issue #111): a filter
that cannot be honored must never yield a success-shaped, unfiltered result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import django
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q
from django.http import HttpRequest

from django_admin_mcp.handlers.base import (
    is_field_visible,
    resolve_field_visibility,
    resolve_related_admin,
)

logger = logging.getLogger(__name__)

# Lookups allowed in list filters: the ones the admin's own list filters and
# date hierarchy generate. Anything else (regex, search, ...) is rejected to
# prevent resource-intensive queries.
SAFE_FILTER_LOOKUPS = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "range",
        "isnull",
        "date",
        "year",
        "month",
        "day",
    }
)

# Date-part lookups, valid on date fields only ("date" needs a DateTimeField).
DATE_PART_LOOKUPS = frozenset({"date", "year", "month", "day"})

# Comparisons that may follow a date part (e.g. release_date__year__gte).
DATE_PART_COMPARISONS = frozenset({"exact", "gt", "gte", "lt", "lte", "in", "range"})

# Upper bound on the choices describe_* embeds per filter.
MAX_DESCRIBED_CHOICES = 100


class InvalidFilterError(ValueError):
    """A list filter or ordering parameter was rejected (issue #111)."""


def _queryable_field_names(model: type[models.Model], model_admin: Any = None) -> set[str]:
    """
    Names of the model's own fields a caller may filter and order by.

    Only the model's own fields that are visible over MCP (plus the primary
    key): filtering or ordering on a field hidden by mcp_fields /
    mcp_exclude_fields would let a caller recover its value one comparison
    at a time, and reverse relations would probe models the caller may not
    be able to view.
    """
    names = set()
    for model_field in model._meta.get_fields():
        if model_field.auto_created and not model_field.concrete:
            continue  # reverse relation
        if getattr(model_field, "primary_key", False) or is_field_visible(model_admin, model_field.name):
            names.add(model_field.name)
    return names


@dataclass
class DeclaredFilters:
    """What a ModelAdmin declares as filterable on its changelist."""

    # Field paths from list_filter (plain strings and (field, FilterClass) tuples), in order
    field_paths: list[str] = field(default_factory=list)
    # SimpleListFilter subclasses keyed by parameter_name, in order
    simple_filters: dict[str, type[SimpleListFilter]] = field(default_factory=dict)
    date_hierarchy: str | None = None

    @property
    def paths(self) -> set[str]:
        """Every declared field path, date_hierarchy included."""
        paths = set(self.field_paths)
        if self.date_hierarchy:
            paths.add(self.date_hierarchy)
        return paths


def get_list_filter_entries(model_admin: Any, request: HttpRequest | None = None) -> list[Any]:
    """The admin's list_filter, through get_list_filter(request) when a request is available."""
    if model_admin is None:
        return []
    if request is not None and hasattr(model_admin, "get_list_filter"):
        entries = model_admin.get_list_filter(request)
    else:
        entries = getattr(model_admin, "list_filter", None)
    return list(entries or [])


def get_declared_filters(model_admin: Any, request: HttpRequest | None = None) -> DeclaredFilters:
    """
    Collect the filters a ModelAdmin declares.

    list_filter entries may be a field path, a ``(field path, FieldListFilter)``
    tuple, or a ``SimpleListFilter`` subclass. Other filter classes have no
    generic way to be driven outside the changelist and are ignored.
    """
    declared = DeclaredFilters()
    for entry in get_list_filter_entries(model_admin, request):
        if isinstance(entry, (list, tuple)):
            entry = entry[0] if entry else None
        if isinstance(entry, str):
            if entry not in declared.field_paths:
                declared.field_paths.append(entry)
        elif isinstance(entry, type) and issubclass(entry, SimpleListFilter):
            parameter_name = getattr(entry, "parameter_name", None)
            if parameter_name:
                declared.simple_filters.setdefault(parameter_name, entry)

    date_hierarchy = getattr(model_admin, "date_hierarchy", None)
    if isinstance(date_hierarchy, str) and date_hierarchy:
        declared.date_hierarchy = date_hierarchy
    return declared


def _is_reverse(model_field: Any) -> bool:
    return bool(model_field.auto_created and not model_field.concrete)


def _segment_visible(owner_admin: Any, model_field: Any) -> bool:
    """Whether one field of a filter path is visible under its model's admin."""
    if getattr(model_field, "primary_key", False):
        return True
    if _is_reverse(model_field):
        # Reverse relations are never serialized, so an include list does not
        # name them; only an explicit exclude hides one.
        _, excluded = resolve_field_visibility(owner_admin)
        return model_field.name not in (excluded or [])
    return is_field_visible(owner_admin, model_field.name)


def _walk_field_path(model: type[models.Model], parts: list[str]) -> tuple[list[Any], list[str]]:
    """
    Split a filter key into the model fields it traverses and the lookups left over.

    Field names win over lookup names, as in the ORM.
    """
    fields: list[Any] = []
    current: Any = model
    index = 0
    while index < len(parts) and current is not None:
        try:
            model_field = current._meta.get_field(parts[index])
        except FieldDoesNotExist:
            break
        fields.append(model_field)
        index += 1
        related = model_field.related_model if model_field.is_relation else None
        current = related if isinstance(related, type) else None
    return fields, parts[index:]


def _check_field_path(
    model: type[models.Model],
    fields: list[Any],
    model_admin: Any,
    declared_paths: set[str],
    own_fields: set[str],
) -> str | None:
    """
    Decide whether a resolved field path may be filtered on.

    Returns a problem description, or None when the path is allowed.
    """
    names = [f.name for f in fields]
    first = names[0]

    if len(fields) == 1:
        return None if first in own_fields else f"unknown field '{first}'"

    path = "__".join(names)
    parent_path = "__".join(names[:-1])
    not_declared = (
        f"relation path '{path}' is not available (relation filters must be declared "
        f"in the admin's list_filter or date_hierarchy)"
    )

    if path not in declared_paths:
        # The admin's own related filters address a relation by the related
        # primary key (author__id__exact). That names no new column, so it is
        # allowed wherever the relation itself may be filtered.
        parent_allowed = parent_path in declared_paths or (len(fields) == 2 and first in own_fields)
        if not (parent_allowed and getattr(fields[-1], "primary_key", False)):
            return not_declared

    # A declared path still has to respect field visibility on every model
    # it crosses: hidden fields must not be recoverable through a filter.
    owner_admin = model_admin
    for model_field in fields:
        if not _segment_visible(owner_admin, model_field):
            return not_declared
        if model_field.is_relation and model_field.related_model is not None:
            owner_admin = resolve_related_admin(model_field.related_model)
    return None


def _check_lookups(terminal: Any, lookups: list[str]) -> str | None:
    """Validate the lookup suffix of a filter key against the terminal field."""
    allowed = ", ".join(sorted(SAFE_FILTER_LOOKUPS))
    if not lookups:
        return None

    head = lookups[0]
    if head not in SAFE_FILTER_LOOKUPS:
        return f"unsupported lookup '{head}' (allowed lookups: {allowed})"

    if head in DATE_PART_LOOKUPS:
        is_date = isinstance(terminal, models.DateField) and not terminal.is_relation
        if not is_date or (head == "date" and not isinstance(terminal, models.DateTimeField)):
            needs = "a datetime field" if head == "date" else "a date field"
            return f"lookup '{head}' needs {needs}"
        if len(lookups) == 1:
            return None
        if len(lookups) == 2 and lookups[1] in DATE_PART_COMPARISONS:
            return None
        comparisons = ", ".join(sorted(DATE_PART_COMPARISONS))
        return f"unsupported lookup '{'__'.join(lookups[1:])}' after '{head}' (allowed: {comparisons})"

    if len(lookups) > 1:
        return f"unsupported lookup '{'__'.join(lookups)}' (allowed lookups: {allowed})"
    return None


def _check_value(lookup: str, value: Any) -> str | None:
    """Reject values whose shape the lookup would misread or ignore."""
    if lookup == "in" and not isinstance(value, (list, tuple)):
        return "lookup 'in' needs a list of values"
    if lookup == "range" and not (isinstance(value, (list, tuple)) and len(value) == 2):
        return "lookup 'range' needs a list of two values"
    if lookup == "isnull" and not isinstance(value, bool):
        return "lookup 'isnull' needs true or false"
    return None


def _instantiate_simple_filter(
    filter_class: type[SimpleListFilter],
    value: Any,
    model: type[models.Model],
    model_admin: Any,
    request: HttpRequest | None,
) -> SimpleListFilter:
    """Build a SimpleListFilter the way the changelist does for one query parameter."""
    params: dict[str, Any] = {}
    if value is not None:
        # Django 5.0 switched changelist params to lists of values
        params[str(filter_class.parameter_name)] = [value] if django.VERSION >= (5, 0) else value
    filter_factory: Any = filter_class
    return filter_factory(request, params, model, model_admin)


def _resolve_simple_filter(
    filter_class: type[SimpleListFilter],
    value: Any,
    model: type[models.Model],
    model_admin: Any,
    request: HttpRequest | None,
) -> tuple[SimpleListFilter | None, str | None]:
    """
    Validate a SimpleListFilter value and build the filter.

    The value must be one of the filter's own lookups(): a SimpleListFilter
    typically ignores values it does not recognize, which would hand back an
    unfiltered result.
    """
    if value is None or isinstance(value, (list, tuple, dict)):
        return None, "needs a single value"

    raw = str(value)
    spec = _instantiate_simple_filter(filter_class, raw, model, model_admin, request)
    choices = [str(choice) for choice, _label in spec.lookup_choices]
    if raw not in choices:
        listed = ", ".join(f"'{c}'" for c in choices) or "none available"
        return None, f"invalid value '{raw}' (choices: {listed})"
    return spec, None


@dataclass
class ResolvedFilters:
    """Validated list filters, ready to apply to a queryset."""

    query: Q = field(default_factory=Q)
    simple_filters: list[SimpleListFilter] = field(default_factory=list)
    needs_distinct: bool = False
    request: HttpRequest | None = None

    def apply(self, queryset: models.QuerySet) -> models.QuerySet:
        """Apply the filters to a queryset."""
        if self.query:
            queryset = queryset.filter(self.query)
        for spec in self.simple_filters:
            apply_filter: Any = spec.queryset
            filtered = apply_filter(self.request, queryset)
            if filtered is not None:
                queryset = filtered
        if self.needs_distinct:
            queryset = queryset.distinct()
        return queryset


def resolve_list_filters(
    model: type[models.Model],
    filters: Any,
    model_admin: Any = None,
    request: HttpRequest | None = None,
    *,
    allow_simple_filters: bool = True,
) -> ResolvedFilters:
    """
    Validate ``filters`` against what the model and its admin allow.

    May run database queries (a SimpleListFilter's lookups()), so call it
    from a synchronous context.

    Args:
        model: The Django model class.
        filters: Mapping of filter key to value.
        model_admin: Optional ModelAdmin with field visibility and list_filter
            / date_hierarchy configuration.
        request: Optional request, passed to get_list_filter() and to
            SimpleListFilter instances.
        allow_simple_filters: Accept SimpleListFilter parameter names.

    Raises:
        InvalidFilterError: Naming every rejected key.
    """
    if not isinstance(filters, dict):
        raise InvalidFilterError("Invalid filters — expected an object mapping filter names to values")

    declared = get_declared_filters(model_admin, request)
    declared_paths = declared.paths
    own_fields = _queryable_field_names(model, model_admin)

    resolved = ResolvedFilters(request=request)
    problems = []
    for key, value in filters.items():
        if not isinstance(key, str):
            problems.append(f"'{key}': filter names must be strings")
            continue

        if allow_simple_filters and key in declared.simple_filters:
            spec, problem = _resolve_simple_filter(declared.simple_filters[key], value, model, model_admin, request)
            if spec is None:
                problems.append(f"'{key}': {problem}")
            else:
                resolved.simple_filters.append(spec)
            continue

        fields, lookups = _walk_field_path(model, key.split("__"))
        if not fields:
            problems.append(f"'{key}': unknown field '{key.split('__')[0]}'")
            continue

        problem = (
            _check_field_path(model, fields, model_admin, declared_paths, own_fields)
            or _check_lookups(fields[-1], lookups)
            or _check_value(lookups[-1] if lookups else "exact", value)
        )
        if problem:
            problems.append(f"'{key}': {problem}")
            continue

        resolved.query &= Q(**{key: value})
        if any(f.many_to_many or f.one_to_many for f in fields):
            resolved.needs_distinct = True

    if problems:
        raise InvalidFilterError("Invalid filters — " + "; ".join(problems))
    return resolved


def _build_filter_query(
    model: type[models.Model],
    filters: dict[str, Any],
    model_admin: Any = None,
    request: HttpRequest | None = None,
) -> Q:
    """
    Build a Q object from field filter parameters.

    Supports ``field`` / ``field__<lookup>`` on the model's own MCP-visible
    fields and on relation paths declared in the admin's list_filter /
    date_hierarchy, with the lookups in SAFE_FILTER_LOOKUPS. SimpleListFilter
    parameters cannot be expressed as a Q and are rejected here; use
    resolve_list_filters() for the full behavior.

    Raises:
        InvalidFilterError: For unknown or hidden fields, undeclared relation
            paths, and disallowed lookups. Silently dropping these would
            hand the caller a success-shaped but unfiltered result set.
    """
    return resolve_list_filters(model, filters, model_admin, request, allow_simple_filters=False).query


def _choices(pairs: Any) -> dict[str, Any]:
    """Format (value, label) pairs for describe_*, capped at MAX_DESCRIBED_CHOICES."""
    pairs = list(pairs)
    out: dict[str, Any] = {
        "choices": [{"value": value, "label": str(label)} for value, label in pairs[:MAX_DESCRIBED_CHOICES]]
    }
    if len(pairs) > MAX_DESCRIBED_CHOICES:
        out["choices_truncated"] = True
    return out


def describe_filters(
    model: type[models.Model], model_admin: Any, request: HttpRequest | None = None
) -> list[dict[str, Any]]:
    """
    List the admin-declared filters ``list_*`` accepts, for describe_*.

    Each entry carries the filter key (``name``) and its ``kind``:

    - ``field``: a field or relation path taking the standard lookups, with
      the terminal field ``type``, its ``choices`` when it defines any, and
      ``date_hierarchy: true`` for the admin's date hierarchy field;
    - ``parameter``: a SimpleListFilter, with its ``title`` and the
      ``choices`` from lookups().

    Declared entries that are not usable over MCP (hidden fields) are left
    out. May run database queries; call from a synchronous context.
    """
    declared = get_declared_filters(model_admin, request)
    declared_paths = declared.paths
    own_fields = _queryable_field_names(model, model_admin)

    field_entries: dict[str, dict[str, Any]] = {}

    def field_entry(path: str) -> dict[str, Any] | None:
        fields, lookups = _walk_field_path(model, path.split("__"))
        if not fields or lookups:
            return None
        if _check_field_path(model, fields, model_admin, declared_paths, own_fields):
            return None
        terminal = fields[-1]
        entry: dict[str, Any] = {
            "name": path,
            "kind": "field",
            "type": getattr(terminal, "get_internal_type", lambda: "Unknown")(),
        }
        flat_choices = getattr(terminal, "flatchoices", None)
        if flat_choices:
            entry.update(_choices(flat_choices))
        return entry

    result: list[dict[str, Any]] = []
    simple_by_class = {cls: name for name, cls in declared.simple_filters.items()}
    for raw in get_list_filter_entries(model_admin, request):
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        if isinstance(raw, str):
            if raw in field_entries:
                continue
            entry = field_entry(raw)
            if entry is not None:
                field_entries[raw] = entry
                result.append(entry)
        elif isinstance(raw, type) and raw in simple_by_class:
            name = simple_by_class.pop(raw)
            entry = {"name": name, "kind": "parameter", "title": str(getattr(raw, "title", name))}
            try:
                spec = _instantiate_simple_filter(raw, None, model, model_admin, request)
            except Exception:
                # A filter whose lookups() fails must not take describe_* down
                # with it; list_* reports the failure when the filter is used.
                logger.exception("Could not resolve choices for list filter %s", name)
            else:
                entry.update(_choices(spec.lookup_choices))
            result.append(entry)

    if declared.date_hierarchy:
        entry = field_entries.get(declared.date_hierarchy) or field_entry(declared.date_hierarchy)
        if entry is not None:
            entry["date_hierarchy"] = True
            if declared.date_hierarchy not in field_entries:
                result.append(entry)

    return result
