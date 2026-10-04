"""
Pytest configuration for django-admin-mcp tests
"""

import pytest
from django.contrib import admin
from pytest_factoryboy import register

from tests.factories import MCPTokenFactory, UserFactory

# Register factories as fixtures
register(UserFactory)
register(MCPTokenFactory)


def _register_filter_admins():
    """Register the admins exercising list_filter / date_hierarchy (issue #116)."""
    # Deferred import: must wait for Django app registry to be ready
    from django_admin_mcp import MCPAdminMixin  # noqa: PLC0415
    from tests.models import Category, Product  # noqa: PLC0415

    _unregister_filter_admins()

    class PriceBandFilter(admin.SimpleListFilter):
        title = "price band"
        parameter_name = "band"

        def lookups(self, request, model_admin):
            return [("cheap", "Under 10"), ("pricey", "10 and over")]

        def queryset(self, request, queryset):
            if self.value() == "cheap":
                return queryset.filter(price__lt=10)
            if self.value() == "pricey":
                return queryset.filter(price__gte=10)
            return queryset

    @admin.register(Category)
    class CategoryAdmin(MCPAdminMixin, admin.ModelAdmin):
        """Category admin hiding internal_code from MCP."""

        mcp_expose = True
        mcp_exclude_fields = ["internal_code"]

    @admin.register(Product)
    class ProductAdmin(MCPAdminMixin, admin.ModelAdmin):
        """Product admin declaring relation filters, a SimpleListFilter and a date hierarchy."""

        mcp_expose = True
        mcp_exclude_fields = ["cost_code"]
        list_filter = [
            "size",
            "category__slug",
            "customer__is_staff",
            ("category__name", admin.AllValuesFieldListFilter),
            "labels__name",
            PriceBandFilter,
            # Declared, yet hidden over MCP: must stay unfilterable
            "category__internal_code",
            "cost_code",
        ]
        date_hierarchy = "release_date"


def _unregister_filter_admins():
    from tests.models import Category, Product  # noqa: PLC0415

    for model in (Category, Product):
        if model in admin.site._registry:
            admin.site.unregister(model)


@pytest.fixture(scope="session", autouse=True)
def django_setup_with_admin(django_db_setup, django_db_blocker):
    """Register admin classes after Django is set up."""
    with django_db_blocker.unblock():
        # Deferred import: must wait for Django app registry to be ready
        from django_admin_mcp import MCPAdminMixin  # noqa: PLC0415
        from tests.models import Article, Author, CatalogItemA, CatalogItemB, Gadget, Ticket  # noqa: PLC0415

        # Clear any existing registrations
        for model in (Author, Article, CatalogItemA, CatalogItemB, Gadget, Ticket):
            if model in admin.site._registry:
                admin.site.unregister(model)

        # Define inline for Author -> Articles
        class ArticleInline(admin.TabularInline):
            model = Article
            extra = 0

        @admin.register(Author)
        class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Author admin with MCP support."""

            list_display = ["name", "email"]
            search_fields = ["name", "email"]
            ordering = ["name"]
            inlines = [ArticleInline]
            mcp_expose = True  # Expose MCP tools

        @admin.register(Article)
        class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Article admin with MCP support."""

            list_display = ["title", "author", "is_published"]
            search_fields = ["title", "content"]
            ordering = ["-published_date", "title"]
            mcp_expose = True  # Expose MCP tools

        @admin.register(Gadget)
        class GadgetAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Gadget admin with MCP support (sensitive field, nullable relations)."""

            mcp_expose = True

        @admin.register(Ticket)
        class TicketAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Ticket admin with MCP support (choice fields, issue #113)."""

            mcp_expose = True

        @admin.register(CatalogItemA)
        class CatalogItemAAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Proxy admin scoped to channel A via get_queryset."""

            mcp_expose = True
            search_fields = ["title"]

            def get_queryset(self, request):
                return super().get_queryset(request).filter(channel="A")

        @admin.register(CatalogItemB)
        class CatalogItemBAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Proxy admin scoped to channel B via get_queryset."""

            mcp_expose = True
            search_fields = ["title"]

            def get_queryset(self, request):
                return super().get_queryset(request).filter(channel="B")

        _register_filter_admins()

        yield

        _unregister_filter_admins()

        # Cleanup (optional, as this is session-scoped)
        for model in (Author, Article, CatalogItemA, CatalogItemB, Gadget, Ticket):
            if model in admin.site._registry:
                admin.site.unregister(model)
