"""
Pytest configuration for django-admin-mcp tests
"""
import pytest
from django.contrib import admin


@pytest.fixture(scope='session', autouse=True)
def django_setup_with_admin(django_db_setup, django_db_blocker):
    """Register admin classes after Django is set up."""
    with django_db_blocker.unblock():
        from tests.models import Article, Author
        from django_admin_mcp import MCPAdminMixin
        
        # Clear any existing registrations
        if Author in admin.site._registry:
            admin.site.unregister(Author)
        if Article in admin.site._registry:
            admin.site.unregister(Article)
        
        @admin.register(Author)
        class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Author admin with MCP support."""
            list_display = ['name', 'email']
        
        @admin.register(Article)
        class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
            """Article admin with MCP support."""
            list_display = ['title', 'author', 'is_published']
        
        yield
        
        # Cleanup (optional, as this is session-scoped)
        if Author in admin.site._registry:
            admin.site.unregister(Author)
        if Article in admin.site._registry:
            admin.site.unregister(Article)
