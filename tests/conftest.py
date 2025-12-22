"""
Pytest configuration for django-admin-mcp tests
"""

import pytest
from django.contrib import admin


@pytest.fixture(scope="session", autouse=True)
def django_setup_with_admin(django_db_setup, django_db_blocker):
    """Register admin classes after Django is set up."""
    with django_db_blocker.unblock():
        from django_admin_mcp import MCPAdminMixin
        from tests.models import Article, Author

        # Clear any existing registrations
        if Author in admin.site._registry:
            admin.site.unregister(Author)
        if Article in admin.site._registry:
            admin.site.unregister(Article)

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

        yield

        # Cleanup (optional, as this is session-scoped)
        if Author in admin.site._registry:
            admin.site.unregister(Author)
        if Article in admin.site._registry:
            admin.site.unregister(Article)
