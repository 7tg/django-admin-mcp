"""
Tests for field filtering in serialize_instance.

Tests that serialize_instance respects:
- mcp_fields and mcp_exclude_fields attributes
- Django admin's fields and exclude attributes (as fallback)
- Proper filtering of sensitive fields
"""

import pytest
from django.contrib import admin

from django_admin_mcp import MCPAdminMixin
from django_admin_mcp.handlers import get_model_admin, serialize_instance
from tests.models import Article, Author


@pytest.mark.django_db
class TestFieldFiltering:
    """Tests for field filtering in serialize_instance."""

    def test_serialize_without_filtering(self):
        """Test that all fields are included when no filtering is specified."""
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Test bio")
        _, model_admin = get_model_admin("author")
        result = serialize_instance(author, model_admin)

        # Should include all fields
        assert "id" in result
        assert "name" in result
        assert "email" in result
        assert "bio" in result

    def test_mcp_fields_includes_only_specified_fields(self):
        """Test that mcp_fields limits serialization to specified fields."""

        # Create a temporary admin with mcp_fields
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_fields = ["name", "email"]

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should only include specified fields
        assert "name" in result
        assert "email" in result
        assert "bio" not in result
        assert "id" not in result  # id is not in mcp_fields

    def test_mcp_exclude_fields_removes_specified_fields(self):
        """Test that mcp_exclude_fields removes specified fields."""

        # Create a temporary admin with mcp_exclude_fields
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_exclude_fields = ["bio"]

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should include all fields except bio
        assert "id" in result
        assert "name" in result
        assert "email" in result
        assert "bio" not in result

    def test_mcp_fields_takes_precedence_over_admin_fields(self):
        """Test that mcp_fields takes precedence over Django admin's fields."""

        # Create a temporary admin with both fields and mcp_fields
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            fields = ["name", "email", "bio"]  # Admin fields
            mcp_fields = ["name", "email"]  # MCP-specific fields (narrower)

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should use mcp_fields, not admin fields
        assert "name" in result
        assert "email" in result
        assert "bio" not in result

    def test_fallback_to_admin_fields(self):
        """Test fallback to Django admin's fields when mcp_fields is not set."""

        # Create a temporary admin with only admin fields
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            fields = ["name", "email"]

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should use admin fields
        assert "name" in result
        assert "email" in result
        assert "bio" not in result
        # Note: 'id' might or might not be included depending on interpretation

    def test_fallback_to_admin_exclude(self):
        """Test fallback to Django admin's exclude when mcp_exclude_fields is not set."""

        # Create a temporary admin with only admin exclude
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            exclude = ["bio"]

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should exclude bio based on admin's exclude
        assert "id" in result
        assert "name" in result
        assert "email" in result
        assert "bio" not in result

    def test_mcp_exclude_takes_precedence_over_admin_exclude(self):
        """Test that mcp_exclude_fields takes precedence over admin exclude."""

        # Create a temporary admin with both exclude and mcp_exclude_fields
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            exclude = ["email"]  # Admin exclude
            mcp_exclude_fields = ["bio"]  # MCP-specific exclude (different)

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # Should use mcp_exclude_fields, not admin exclude
        assert "id" in result
        assert "name" in result
        assert "email" in result  # NOT excluded because mcp_exclude_fields takes precedence
        assert "bio" not in result

    def test_with_related_fields(self):
        """Test field filtering with related fields."""

        # Create a temporary admin with field filtering for Article
        class TestArticleAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_exclude_fields = ["content"]

        author = Author.objects.create(name="Test Author", email="test@example.com")
        article = Article.objects.create(
            title="Test Article", content="Secret content", author=author, is_published=True
        )

        model_admin = TestArticleAdmin(Article, admin.site)
        result = serialize_instance(article, model_admin)

        # Should include fields except content
        assert "id" in result
        assert "title" in result
        assert "author" in result
        assert "is_published" in result
        assert "content" not in result

    def test_both_mcp_fields_and_exclude(self):
        """Test behavior when both mcp_fields and mcp_exclude_fields are set."""

        # Create a temporary admin with both
        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_fields = ["id", "name", "email", "bio"]
            mcp_exclude_fields = ["bio"]  # Exclude takes precedence

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Secret bio")

        result = serialize_instance(author, model_admin)

        # mcp_fields includes bio, but mcp_exclude_fields removes it
        assert "id" in result
        assert "name" in result
        assert "email" in result
        assert "bio" not in result

    def test_empty_mcp_fields_includes_nothing(self):
        """Test that empty mcp_fields list results in no fields."""

        class TestAuthorAdmin(MCPAdminMixin, admin.ModelAdmin):
            mcp_expose = True
            mcp_fields = []

        model_admin = TestAuthorAdmin(Author, admin.site)
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Test bio")

        result = serialize_instance(author, model_admin)

        # Empty mcp_fields should result in no fields
        assert result == {}

    def test_none_model_admin_includes_all_fields(self):
        """Test that None model_admin includes all fields (backwards compatibility)."""
        author = Author.objects.create(name="Test Author", email="test@example.com", bio="Test bio")
        result = serialize_instance(author, None)

        # Should include all fields when model_admin is None
        assert "id" in result
        assert "name" in result
        assert "email" in result
        assert "bio" in result
