"""Blog admin configuration with MCP integration."""
from django.contrib import admin

from django_admin_mcp import MCPAdminMixin

from .models import Article, Author


@admin.register(Author)
class AuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
    """Author admin with MCP support."""
    list_display = ['name', 'email', 'created_at']
    search_fields = ['name', 'email']
    list_filter = ['created_at']
    mcp_expose = True  # Expose MCP tools for this model


@admin.register(Article)
class ArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
    """Article admin with MCP support."""
    list_display = ['title', 'author', 'is_published', 'published_date', 'created_at']
    search_fields = ['title', 'content']
    list_filter = ['is_published', 'published_date', 'created_at']
    date_hierarchy = 'published_date'
    raw_id_fields = ['author']
    mcp_expose = True  # Expose MCP tools for this model
