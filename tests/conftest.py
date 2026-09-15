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


@pytest.fixture(scope="session", autouse=True)
def django_setup_with_admin(django_db_setup, django_db_blocker):
    """Register admin classes after Django is set up."""
    with django_db_blocker.unblock():
        # Deferred import: must wait for Django app registry to be ready
        from django_admin_mcp import MCPAdminMixin  # noqa: PLC0415
        from tests.models import Article, Author, CatalogItemA, CatalogItemB, Gadget  # noqa: PLC0415

        # Clear any existing registrations
        for model in (Author, Article, CatalogItemA, CatalogItemB, Gadget):
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

        yield

        # Cleanup (optional, as this is session-scoped)
        for model in (Author, Article, CatalogItemA, CatalogItemB, Gadget):
            if model in admin.site._registry:
                admin.site.unregister(model)
