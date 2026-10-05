"""
Tests for non-editable field and computed admin value serialization (issue #117).

Covers:
- serialize_instance returns ``editable=False`` concrete fields (auto_now
  timestamps, UUIDs, ...) under the usual visibility rules
- get_* returns computed ``readonly_fields`` entries and list_* returns
  computed ``list_display`` entries under a separate ``_computed`` key
- hidden fields stay hidden, whether non-editable or named in
  ``readonly_fields`` / ``list_display``
- a failing callable never fails the response
"""

import contextlib
import json
import uuid
from decimal import Decimal

import pytest
from asgiref.sync import sync_to_async
from django.contrib import admin
from django.contrib.auth.models import User
from django.utils.html import format_html

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import (
    create_mock_request,
    handle_get,
    handle_list,
    handle_related,
    json_response,
    serialize_instance,
)
from django_admin_mcp.handlers.base import get_computed_entries, serialize_computed_fields
from django_admin_mcp.models import MCPToken
from tests.models import Author, Product


def unique_id():
    """Generate a unique identifier for test data."""
    return uuid.uuid4().hex[:8]


def make_author():
    uid = unique_id()
    return Author.objects.create(name=f"Owner {uid}", email=f"owner_{uid}@example.com")


def make_product(**overrides):
    defaults = {"name": f"Product {unique_id()}", "price": Decimal("10.00"), "cost": Decimal("4.00"), "stock": 3}
    defaults.update(overrides)
    return Product.objects.create(**defaults)


def upper_name(obj):
    return obj.name.upper()


class ProductAdmin(MCPAdminMixin, admin.ModelAdmin):
    mcp_expose = True
    list_display = ["name", "price", "in_stock", "margin", upper_name, "label"]
    readonly_fields = ["uuid", "created_at", "updated_at", "margin", "badge"]

    @admin.display(boolean=True)
    def in_stock(self, obj):
        return obj.stock > 0

    def margin(self, obj):
        return obj.price - obj.cost

    def badge(self, obj):
        return format_html("<b>{}</b>", obj.name)


@contextlib.contextmanager
def registered_admin(admin_class, model=Product):
    """Temporarily register ``admin_class`` as the MCP admin for ``model``."""
    registry = MCPAdminMixin._registered_models
    model_name = model._meta.model_name
    previous = registry.pop(model_name, None)
    model_admin = admin_class(model, admin.site)
    registry[model_name] = {"model": model, "admin": model_admin}
    try:
        yield model_admin
    finally:
        if previous is None:
            registry.pop(model_name, None)
        else:
            registry[model_name] = previous


@pytest.mark.django_db
class TestSerializeNonEditableFields:
    """serialize_instance returns editable=False concrete fields."""

    def test_non_editable_fields_serialized(self):
        product = make_product()
        result = serialize_instance(product, ProductAdmin(Product, admin.site))
        assert result["uuid"] == product.uuid
        assert result["created_at"] == product.created_at
        assert result["updated_at"] == product.updated_at
        assert result["internal_code"] == ""
        # editable fields are unaffected
        assert result["id"] == product.pk
        assert result["name"] == product.name
        assert result["owner"] is None
        # computed values are only attached by get_* / list_*
        assert "_computed" not in result

    def test_non_editable_fields_are_json_serializable(self):
        product = make_product()
        data = json.loads(json_response(serialize_instance(product))[0].text)
        assert data["uuid"] == str(product.uuid)
        assert data["created_at"]

    def test_non_editable_choice_field_gets_display_sidecar(self):
        result = serialize_instance(make_product())
        assert result["stage"] == "new"
        assert result["stage_display"] == "New"

    def test_non_editable_filefield_serializes_to_string(self):
        result = serialize_instance(make_product())
        assert result["manual"] == ""
        assert isinstance(result["manual"], str)

    def test_mcp_exclude_fields_hides_non_editable(self):
        class Admin(MCPAdminMixin, admin.ModelAdmin):
            mcp_exclude_fields = ["uuid", "internal_code", "stage"]

        result = serialize_instance(make_product(), Admin(Product, admin.site))
        assert "uuid" not in result
        assert "internal_code" not in result
        assert "stage" not in result
        assert "stage_display" not in result
        assert "created_at" in result

    def test_mcp_fields_limits_non_editable(self):
        class Admin(MCPAdminMixin, admin.ModelAdmin):
            mcp_fields = ["name", "created_at"]

        result = serialize_instance(make_product(), Admin(Product, admin.site))
        assert set(result) == {"name", "created_at"}

    def test_admin_fields_fallback_limits_non_editable(self):
        class Admin(MCPAdminMixin, admin.ModelAdmin):
            fields = ["name", "price"]

        result = serialize_instance(make_product(), Admin(Product, admin.site))
        assert set(result) == {"name", "price"}

    def test_admin_exclude_fallback_hides_non_editable(self):
        class Admin(MCPAdminMixin, admin.ModelAdmin):
            exclude = ["internal_code"]

        result = serialize_instance(make_product(), Admin(Product, admin.site))
        assert "internal_code" not in result
        assert "uuid" in result


@pytest.mark.django_db
class TestSerializeComputedFields:
    """serialize_computed_fields evaluates declared non-field admin entries."""

    def test_evaluates_admin_methods_callables_and_model_attributes(self):
        product = make_product(name="widget")
        model_admin = ProductAdmin(Product, admin.site)
        result = serialize_computed_fields(product, model_admin, model_admin.list_display)
        assert result == {
            "in_stock": True,
            "margin": Decimal("6.00"),
            "upper_name": "WIDGET",
            "label": "widget (new)",
        }

    def test_model_field_entries_are_not_computed(self):
        model_admin = ProductAdmin(Product, admin.site)
        entries = ["name", "uuid", "owner", "owner_id", "pk", "margin"]
        assert set(serialize_computed_fields(make_product(), model_admin, entries)) == {"margin"}

    def test_hidden_field_named_as_entry_stays_hidden(self):
        class Admin(ProductAdmin):
            mcp_exclude_fields = ["cost", "owner", "internal_code"]

        product = make_product(owner=make_author())
        model_admin = Admin(Product, admin.site)
        # Field names and FK column names never become computed values
        entries = ["cost", "owner", "owner_id", "internal_code", "in_stock"]
        assert serialize_computed_fields(product, model_admin, entries) == {"in_stock": True}

    def test_excluded_computed_name_is_hidden(self):
        class Admin(ProductAdmin):
            mcp_exclude_fields = ["margin", "upper_name"]

        model_admin = Admin(Product, admin.site)
        result = serialize_computed_fields(make_product(), model_admin, model_admin.list_display)
        assert set(result) == {"in_stock", "label"}

    def test_include_list_limits_computed_names(self):
        class Admin(ProductAdmin):
            mcp_fields = ["name", "margin"]

        model_admin = Admin(Product, admin.site)
        result = serialize_computed_fields(make_product(), model_admin, model_admin.list_display)
        assert set(result) == {"margin"}

    def test_relation_traversal_and_dunder_entries_are_skipped(self):
        product = make_product(owner=make_author())
        model_admin = ProductAdmin(Product, admin.site)
        result = serialize_computed_fields(product, model_admin, ["__str__", "owner__email", "in_stock"])
        assert result == {"in_stock": True}

    def test_reverse_accessor_is_not_computed(self):
        class Admin(MCPAdminMixin, admin.ModelAdmin):
            pass

        assert serialize_computed_fields(make_author(), Admin(Author, admin.site), ["products", "articles"]) == {}

    def test_failing_callable_yields_none(self):
        class Admin(ProductAdmin):
            def broken(self, obj):
                raise RuntimeError("boom")

        model_admin = Admin(Product, admin.site)
        result = serialize_computed_fields(make_product(), model_admin, ["broken", "missing_attr", "in_stock"])
        assert result == {"broken": None, "missing_attr": None, "in_stock": True}

    def test_values_are_json_safe(self):
        class Admin(ProductAdmin):
            def owner_obj(self, obj):
                return obj.owner

            def tags(self, obj):
                return ["a", {"k": object()}, ("b",)]

        owner = make_author()
        model_admin = Admin(Product, admin.site)
        result = serialize_computed_fields(make_product(owner=owner), model_admin, ["badge", "owner_obj", "tags"])
        assert result["owner_obj"] == owner.name
        assert isinstance(result["badge"], str)
        assert result["tags"][0] == "a"
        assert isinstance(result["tags"][1]["k"], str)
        assert result["tags"][2] == ["b"]
        data = json.loads(json_response({"_computed": result})[0].text)
        assert data["_computed"]["badge"].startswith("<b>")

    def test_no_admin_returns_empty(self):
        assert serialize_computed_fields(make_product(), None, ["label"]) == {}

    def test_get_computed_entries_falls_back_to_attribute(self):
        class Plain:
            list_display = ["a"]

        assert get_computed_entries(Plain(), "list_display", None) == ["a"]
        assert get_computed_entries(None, "list_display", None) == []


@pytest.mark.asyncio
@pytest.mark.django_db
class TestComputedEndToEnd:
    """Non-editable and computed values flow through get_* / list_*."""

    async def _request(self):
        def _create():
            uid = unique_id()
            user = User.objects.create_superuser(username=f"admin_{uid}", email=f"{uid}@example.com", password="pw")
            return create_mock_request(user)

        return await sync_to_async(_create)()

    async def _get(self, model_name, obj, request, **extra):
        result = await handle_get(model_name, {"id": obj.pk, **extra}, request)
        return json.loads(result[0].text)

    async def _list_row(self, model_name, obj, request):
        result = await handle_list(model_name, {"filters": {"id": obj.pk}}, request)
        return json.loads(result[0].text)["results"][0]

    async def test_get_returns_non_editable_and_computed_readonly(self):
        product = await sync_to_async(make_product)(name="widget")
        request = await self._request()
        with registered_admin(ProductAdmin):
            data = await self._get("product", product, request)
        assert data["uuid"] == str(product.uuid)
        assert data["created_at"]
        assert data["updated_at"]
        # readonly_fields computed entries only; list_display-only columns are not in get
        assert data["_computed"] == {"margin": "6.00", "badge": "<b>widget</b>"}

    async def test_list_returns_non_editable_and_computed_list_display(self):
        product = await sync_to_async(make_product)(name="widget")
        request = await self._request()
        with registered_admin(ProductAdmin):
            row = await self._list_row("product", product, request)
        assert row["uuid"] == str(product.uuid)
        assert row["created_at"]
        assert row["_computed"] == {
            "in_stock": True,
            "margin": "6.00",
            "upper_name": "WIDGET",
            "label": "widget (new)",
        }

    async def test_no_computed_key_without_computed_entries(self):
        author = await sync_to_async(make_author)()
        request = await self._request()
        assert "_computed" not in await self._get("author", author, request)
        assert "_computed" not in await self._list_row("author", author, request)

    async def test_dynamic_getters_are_used(self):
        class Admin(ProductAdmin):
            def get_readonly_fields(self, request, obj=None):
                return ["margin"] if obj is not None else []

            def get_list_display(self, request):
                return ["name", "in_stock"]

        product = await sync_to_async(make_product)()
        request = await self._request()
        with registered_admin(Admin):
            get_data = await self._get("product", product, request)
            row = await self._list_row("product", product, request)
        assert get_data["_computed"] == {"margin": "6.00"}
        assert row["_computed"] == {"in_stock": True}

    async def test_failing_getter_does_not_fail_response(self):
        class Admin(ProductAdmin):
            def get_readonly_fields(self, request, obj=None):
                raise RuntimeError("boom")

            def get_list_display(self, request):
                raise RuntimeError("boom")

        product = await sync_to_async(make_product)()
        request = await self._request()
        with registered_admin(Admin):
            get_data = await self._get("product", product, request)
            row = await self._list_row("product", product, request)
        assert get_data["name"] == product.name
        assert "_computed" not in get_data
        assert row["name"] == product.name
        assert "_computed" not in row

    async def test_failing_callable_does_not_fail_response(self):
        class Admin(ProductAdmin):
            list_display = ["name", "broken", "in_stock"]
            readonly_fields = ["broken", "margin"]

            def broken(self, obj):
                raise RuntimeError("boom")

        product = await sync_to_async(make_product)()
        request = await self._request()
        with registered_admin(Admin):
            get_data = await self._get("product", product, request)
            row = await self._list_row("product", product, request)
        assert get_data["_computed"] == {"broken": None, "margin": "6.00"}
        assert row["_computed"] == {"broken": None, "in_stock": True}

    async def test_hidden_fields_stay_hidden_end_to_end(self):
        class Admin(ProductAdmin):
            mcp_exclude_fields = ["cost", "uuid", "margin"]
            list_display = ["name", "cost", "uuid", "margin", "in_stock"]
            readonly_fields = ["cost", "uuid", "margin", "badge"]

        product = await sync_to_async(make_product)(name="widget")
        request = await self._request()
        with registered_admin(Admin):
            get_data = await self._get("product", product, request)
            row = await self._list_row("product", product, request)
        for payload in (get_data, row):
            assert "cost" not in payload
            assert "uuid" not in payload
        assert get_data["_computed"] == {"badge": "<b>widget</b>"}
        assert row["_computed"] == {"in_stock": True}

    async def test_related_rows_include_non_editable_under_visibility(self):
        class Admin(ProductAdmin):
            mcp_exclude_fields = ["internal_code"]

        def _setup():
            owner = make_author()
            return owner, make_product(owner=owner)

        owner, product = await sync_to_async(_setup)()
        request = await self._request()
        with registered_admin(Admin):
            result = await handle_related("author", {"id": owner.pk, "relation": "products"}, request)
            get_data = await self._get("author", owner, request, include_related=True)
        row = json.loads(result[0].text)["results"][0]
        related_row = get_data["_related"]["products"][0]
        for payload in (row, related_row):
            assert payload["uuid"] == str(product.uuid)
            assert "internal_code" not in payload
            # computed values are only served for the object the tool targets
            assert "_computed" not in payload


@pytest.mark.asyncio
@pytest.mark.django_db
class TestMCPTokenComputed:
    """The token admin's computed columns never reveal the hidden token key."""

    async def test_token_preview_is_not_served(self):
        def _setup():
            user = User.objects.create_superuser(username=f"admin_{unique_id()}", password="pw")
            return create_mock_request(user), MCPToken.objects.create(name="T", user=user)

        request, token = await sync_to_async(_setup)()
        get_text = (await handle_get("mcptoken", {"id": token.pk}, request))[0].text
        list_text = (await handle_list("mcptoken", {}, request))[0].text
        for text in (get_text, list_text):
            assert token.token_key not in text
            assert "token_preview" not in text
            assert "regenerate" not in text
        assert "created_at" in json.loads(get_text)
        assert "status_display" in json.loads(list_text)["results"][0]["_computed"]
