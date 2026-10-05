"""
Tests for list_* filters that reproduce the admin changelist (issue #116):
the wider lookup set, relation paths declared in list_filter / date_hierarchy,
SimpleListFilter parameters, and the describe_* filter listing.
"""

import datetime
import json
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.db.models import Q

from django_admin_mcp.handlers import create_mock_request, handle_describe, handle_list
from django_admin_mcp.handlers.crud import InvalidFilterError, _build_filter_query
from django_admin_mcp.handlers.filters import resolve_list_filters
from tests.models import Article, Author, Category, Label, Widget


def _seed():
    toys = Category.objects.create(name="Toys", slug="toys", internal_code="T-SECRET")
    books = Category.objects.create(name="Books", slug="books", internal_code="B-SECRET")
    staff = User.objects.create_user("f116_staff", is_staff=True)
    plain = User.objects.create_user("f116_plain")
    red = Label.objects.create(name="red")
    round_ = Label.objects.create(name="round")

    robot = Widget.objects.create(
        name="Robot",
        price=Decimal("5.00"),
        size="s",
        release_date=datetime.date(2026, 3, 14),
        created_at=datetime.datetime(2026, 3, 14, 12, 0, tzinfo=datetime.timezone.utc),
        cost_code="alpha",
        category=toys,
        customer=staff,
    )
    Widget.objects.create(
        name="Rocket",
        price=Decimal("25.00"),
        size="l",
        release_date=datetime.date(2025, 7, 1),
        created_at=datetime.datetime(2025, 7, 1, 12, 0, tzinfo=datetime.timezone.utc),
        cost_code="beta",
        category=toys,
        customer=plain,
    )
    Widget.objects.create(
        name="Novel",
        price=Decimal("12.00"),
        size="s",
        release_date=datetime.date(2026, 9, 2),
        cost_code="beta",
        category=books,
    )
    robot.labels.add(red, round_)


@pytest.fixture
def request_():
    user = User.objects.create_superuser("f116_admin", "f116@example.com", "admin")
    return create_mock_request(user)


@pytest.fixture
def seeded(db):
    _seed()


async def _list(request, filters, **extra):
    result = await handle_list("widget", {"filters": filters, "order_by": ["name"], **extra}, request)
    return json.loads(result[0].text)


async def _names(request, filters):
    data = await _list(request, filters)
    assert "error" not in data, data
    return [r["name"] for r in data["results"]]


async def _error(request, filters):
    data = await _list(request, filters)
    assert "error" in data, f"expected an error for {filters}, got {data}"
    assert "results" not in data
    return data["error"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestWiderLookupSet:
    async def test_string_lookups(self, seeded, request_):
        assert await _names(request_, {"name__startswith": "Ro"}) == ["Robot", "Rocket"]
        assert await _names(request_, {"name__istartswith": "ro"}) == ["Robot", "Rocket"]
        assert await _names(request_, {"name__endswith": "et"}) == ["Rocket"]
        assert await _names(request_, {"name__iendswith": "ET"}) == ["Rocket"]
        assert await _names(request_, {"name__iexact": "novel"}) == ["Novel"]

    async def test_range_lookup(self, seeded, request_):
        assert await _names(request_, {"price__range": [10, 20]}) == ["Novel"]

    async def test_date_part_lookups(self, seeded, request_):
        assert await _names(request_, {"release_date__year": 2026}) == ["Novel", "Robot"]
        assert await _names(request_, {"release_date__year": 2026, "release_date__month": 3}) == ["Robot"]
        assert await _names(request_, {"release_date__day": 1}) == ["Rocket"]
        assert await _names(request_, {"created_at__date": "2026-03-14"}) == ["Robot"]

    async def test_date_part_with_comparison(self, seeded, request_):
        assert await _names(request_, {"release_date__year__gte": 2026}) == ["Novel", "Robot"]
        assert await _names(request_, {"release_date__month__in": [7, 9]}) == ["Novel", "Rocket"]

    async def test_date_part_on_non_date_field_is_rejected(self, seeded, request_):
        assert "name__year" in await _error(request_, {"name__year": 2026})
        assert "release_date__date" in await _error(request_, {"release_date__date": "2026-03-14"})

    async def test_regex_and_unknown_lookups_still_rejected(self, seeded, request_):
        assert "name__regex" in await _error(request_, {"name__regex": ".*"})
        assert "name__search" in await _error(request_, {"name__search": "x"})
        # Text lookups cannot be chained after a date part
        assert "release_date__year__regex" in await _error(request_, {"release_date__year__regex": "2"})
        assert "release_date__year__contains" in await _error(request_, {"release_date__year__contains": "2"})

    async def test_malformed_values_are_rejected(self, seeded, request_):
        assert "price__range" in await _error(request_, {"price__range": 10})
        assert "price__range" in await _error(request_, {"price__range": [1, 2, 3]})
        assert "id__in" in await _error(request_, {"id__in": "12"})
        assert "category__isnull" in await _error(request_, {"category__isnull": "yes"})

    async def test_filters_must_be_an_object(self, seeded, request_):
        result = await handle_list("widget", {"filters": ["name"]}, request_)
        data = json.loads(result[0].text)
        assert "error" in data
        assert "results" not in data


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestDeclaredRelationPaths:
    async def test_declared_relation_path(self, seeded, request_):
        assert await _names(request_, {"category__slug": "toys"}) == ["Robot", "Rocket"]
        assert await _names(request_, {"customer__is_staff": True}) == ["Robot"]

    async def test_declared_path_accepts_lookups(self, seeded, request_):
        assert await _names(request_, {"category__slug__startswith": "bo"}) == ["Novel"]
        assert await _names(request_, {"category__slug__in": ["toys", "books"]}) == ["Novel", "Robot", "Rocket"]

    async def test_tuple_entry_declares_its_field_path(self, seeded, request_):
        assert await _names(request_, {"category__name": "Books"}) == ["Novel"]

    async def test_multi_valued_path_does_not_duplicate_rows(self, seeded, request_):
        data = await _list(request_, {"labels__name__in": ["red", "round"]})
        assert [r["name"] for r in data["results"]] == ["Robot"]
        assert data["total_count"] == 1

    async def test_undeclared_relation_path_is_rejected(self, seeded, request_):
        # Same relation, sibling field the admin never declared
        assert "customer__email" in await _error(request_, {"customer__email": "x@example.com"})
        assert "customer__password__startswith" in await _error(request_, {"customer__password__startswith": "pbkdf2"})
        assert "category__widgets__name" in await _error(request_, {"category__widgets__name": "Robot"})
        # A declared path is not a licence to keep traversing
        assert "labels__widgets__name" in await _error(request_, {"labels__widgets__name": "Robot"})

    async def test_declared_path_is_not_a_prefix_for_other_fields(self, seeded, request_):
        assert "category__slug__name" in await _error(request_, {"category__slug__name": "x"})

    async def test_hidden_terminal_field_stays_unfilterable(self, seeded, request_):
        """category__internal_code is declared, but CategoryAdmin hides the field."""
        for filters in (
            {"category__internal_code": "T-SECRET"},
            {"category__internal_code__startswith": "T"},
        ):
            assert "category__internal_code" in await _error(request_, filters)

    async def test_hidden_own_field_stays_unfilterable(self, seeded, request_):
        """cost_code is in list_filter, but WidgetAdmin hides it."""
        assert "cost_code" in await _error(request_, {"cost_code": "alpha"})
        assert "cost_code__startswith" in await _error(request_, {"cost_code__startswith": "a"})

    async def test_hidden_relation_blocks_declared_path(self, seeded, request_):
        """Hiding the FK itself makes every path through it unfilterable."""
        model_admin = admin.site._registry[Widget]
        original = model_admin.mcp_exclude_fields
        model_admin.mcp_exclude_fields = ["cost_code", "category"]
        try:
            assert "category__slug" in await _error(request_, {"category__slug": "toys"})
        finally:
            model_admin.mcp_exclude_fields = original

    async def test_related_pk_of_visible_fk(self, seeded, request_):
        """The admin's own RelatedFieldListFilter parameter form (fk__id__exact)."""
        toys = await sync_to_async(Category.objects.get)(slug="toys")
        assert await _names(request_, {"category__id__exact": toys.pk}) == ["Robot", "Rocket"]
        assert await _names(request_, {"category__id": toys.pk}) == ["Robot", "Rocket"]

    async def test_partial_failure_never_returns_rows(self, seeded, request_):
        error = await _error(request_, {"category__slug": "toys", "customer__email": "x", "name__regex": "."})
        assert "customer__email" in error
        assert "name__regex" in error

    async def test_get_list_filter_is_honoured(self, seeded, request_):
        """Paths come from get_list_filter(request), not the bare attribute."""
        model_admin = admin.site._registry[Widget]
        model_admin.get_list_filter = lambda request: ["size"]
        try:
            assert "category__slug" in await _error(request_, {"category__slug": "toys"})
            assert "band" in await _error(request_, {"band": "cheap"})
        finally:
            del model_admin.get_list_filter

    async def test_date_hierarchy_relation_path(self, seeded, request_):
        """A date_hierarchy spanning a relation is a declared path too."""
        model_admin = admin.site._registry[Widget]
        model_admin.date_hierarchy = "customer__date_joined"
        try:
            year = datetime.datetime.now(tz=datetime.timezone.utc).year
            assert await _names(request_, {"customer__date_joined__year": year}) == ["Robot", "Rocket"]
        finally:
            model_admin.date_hierarchy = "release_date"

    async def test_view_only_user_can_use_declared_filters(self, seeded):
        @sync_to_async
        def make_request():
            user = User.objects.create_user("f116_viewer", is_staff=True)
            user.user_permissions.add(Permission.objects.get(codename="view_widget"))
            return create_mock_request(user)

        request = await make_request()
        assert await _names(request, {"category__slug": "books"}) == ["Novel"]


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestSimpleListFilter:
    async def test_parameter_name_applies_filter_queryset(self, seeded, request_):
        assert await _names(request_, {"band": "cheap"}) == ["Robot"]
        assert await _names(request_, {"band": "pricey"}) == ["Novel", "Rocket"]

    async def test_combines_with_field_filters(self, seeded, request_):
        assert await _names(request_, {"band": "pricey", "category__slug": "toys"}) == ["Rocket"]

    async def test_unknown_choice_is_an_error_not_an_unfiltered_list(self, seeded, request_):
        error = await _error(request_, {"band": "free"})
        assert "band" in error
        assert "cheap" in error and "pricey" in error

    async def test_non_scalar_value_is_rejected(self, seeded, request_):
        assert "band" in await _error(request_, {"band": ["cheap"]})
        assert "band" in await _error(request_, {"band": None})

    async def test_lookups_do_not_apply_to_parameters(self, seeded, request_):
        assert "band__in" in await _error(request_, {"band__in": ["cheap"]})

    async def test_undeclared_simple_filter_is_unknown(self, seeded, request_):
        """Author's admin declares no filter called 'band'."""
        result = await handle_list("author", {"filters": {"band": "cheap"}}, request_)
        data = json.loads(result[0].text)
        assert "band" in data["error"]


@pytest.mark.django_db
class TestBuildFilterQueryCompat:
    """The Q-building helper keeps its signature and its strict defaults."""

    def test_without_admin_relation_paths_stay_rejected(self):
        with pytest.raises(InvalidFilterError, match="author__email"):
            _build_filter_query(Article, {"author__email": "x@example.com"})
        with pytest.raises(InvalidFilterError, match="category__slug"):
            _build_filter_query(Widget, {"category__slug": "toys"})

    def test_with_admin_declared_paths_build_a_query(self):
        model_admin = admin.site._registry[Widget]
        assert _build_filter_query(Widget, {"category__slug": "toys"}, model_admin) != Q()

    def test_simple_filter_parameter_cannot_become_a_q(self):
        model_admin = admin.site._registry[Widget]
        with pytest.raises(InvalidFilterError, match="band"):
            _build_filter_query(Widget, {"band": "cheap"}, model_admin)

    def test_resolve_without_request_uses_list_filter_attribute(self):
        model_admin = admin.site._registry[Widget]
        resolved = resolve_list_filters(Widget, {"band": "cheap", "size": "s"}, model_admin)
        assert resolved.apply(Widget.objects.all()).count() == 0

    def test_new_lookups_accepted_on_plain_models(self):
        for filters in ({"name__startswith": "a"}, {"name__iexact": "a"}, {"id__range": [1, 2]}):
            assert _build_filter_query(Author, filters) != Q()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestDescribeFilters:
    async def _filters(self, request, model_name="widget"):
        result = await handle_describe(model_name, {}, request)
        data = json.loads(result[0].text)
        assert "error" not in data, data
        return data["admin_config"]["filters"]

    async def test_lists_usable_filters(self, seeded, request_):
        filters = {f["name"]: f for f in await self._filters(request_)}
        assert list(filters) == [
            "size",
            "category__slug",
            "customer__is_staff",
            "category__name",
            "labels__name",
            "band",
            "release_date",
        ]
        assert filters["category__slug"] == {"name": "category__slug", "kind": "field", "type": "SlugField"}
        assert filters["customer__is_staff"]["type"] == "BooleanField"
        assert filters["release_date"] == {
            "name": "release_date",
            "kind": "field",
            "type": "DateField",
            "date_hierarchy": True,
        }

    async def test_choice_field_lists_choices(self, seeded, request_):
        filters = {f["name"]: f for f in await self._filters(request_)}
        assert filters["size"]["choices"] == [{"value": "s", "label": "Small"}, {"value": "l", "label": "Large"}]

    async def test_simple_filter_lists_lookups(self, seeded, request_):
        filters = {f["name"]: f for f in await self._filters(request_)}
        assert filters["band"] == {
            "name": "band",
            "kind": "parameter",
            "title": "price band",
            "choices": [{"value": "cheap", "label": "Under 10"}, {"value": "pricey", "label": "10 and over"}],
        }

    async def test_hidden_fields_are_not_listed(self, seeded, request_):
        names = [f["name"] for f in await self._filters(request_)]
        assert "category__internal_code" not in names
        assert "cost_code" not in names

    async def test_every_listed_filter_is_accepted_by_list(self, seeded, request_):
        for entry in await self._filters(request_):
            value = entry["choices"][0]["value"] if entry.get("choices") else "2026-01-01"
            if entry.get("type") == "BooleanField":
                value = True
            data = await _list(request_, {entry["name"]: value})
            assert "error" not in data, (entry, data)

    async def test_failing_lookups_do_not_break_describe(self, seeded, request_):
        class BrokenFilter(admin.SimpleListFilter):
            title = "broken"
            parameter_name = "broken"

            def lookups(self, request, model_admin):
                raise RuntimeError("boom")

            def queryset(self, request, queryset):
                return queryset

        model_admin = admin.site._registry[Widget]
        model_admin.get_list_filter = lambda request: [BrokenFilter, "size"]
        try:
            filters = await self._filters(request_)
            assert filters[0] == {"name": "broken", "kind": "parameter", "title": "broken"}
            # Using the broken filter is an error, never an unfiltered list
            data = await _list(request_, {"broken": "x"})
            assert "error" in data and "results" not in data
        finally:
            del model_admin.get_list_filter

    async def test_long_choice_lists_are_truncated(self, seeded, request_):
        class ManyFilter(admin.SimpleListFilter):
            title = "many"
            parameter_name = "many"

            def lookups(self, request, model_admin):
                return [(str(i), f"Choice {i}") for i in range(150)]

            def queryset(self, request, queryset):
                return queryset

        model_admin = admin.site._registry[Widget]
        model_admin.get_list_filter = lambda request: [ManyFilter]
        try:
            entry = (await self._filters(request_))[0]
            assert len(entry["choices"]) == 100
            assert entry["choices_truncated"] is True
        finally:
            del model_admin.get_list_filter

    async def test_admin_without_filters(self, seeded, request_):
        assert await self._filters(request_, "author") == []

    async def test_describe_uses_get_list_filter(self, seeded, request_):
        model_admin = admin.site._registry[Widget]
        model_admin.get_list_filter = lambda request: ["size"]
        try:
            result = await handle_describe("widget", {}, request_)
            config = json.loads(result[0].text)["admin_config"]
            assert config["list_filter"] == ["size"]
            assert [f["name"] for f in config["filters"]] == ["size", "release_date"]
        finally:
            del model_admin.get_list_filter
