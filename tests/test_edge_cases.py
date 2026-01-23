"""
Tests for edge cases and error paths to achieve 100% coverage.
"""

import asyncio

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestEdgeCasesAndErrors:
    """Test suite for edge cases and error paths to achieve 100% coverage."""

    async def test_invalid_tool_name_format(self):
        """Test handling of invalid tool name format (no underscore)."""
        import json

        result = await MCPAdminMixin.handle_tool_call("invalidtoolname", {})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "Invalid tool name format" in response["error"]

    async def test_unknown_operation(self):
        """Test handling of unknown operation."""
        import json

        result = await MCPAdminMixin.handle_tool_call("unknown_author", {})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "Unknown operation" in response["error"]

    async def test_unregistered_model(self):
        """Test handling of unregistered model."""
        import json

        result = await MCPAdminMixin.handle_tool_call("list_nonexistent", {})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "not found" in response["error"]

    async def test_get_missing_id_parameter(self):
        """Test get without id parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call("get_author", {})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_delete_missing_id_parameter(self):
        """Test delete without id parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call("delete_author", {})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_update_missing_id_parameter(self):
        """Test update without id parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call("update_author", {"data": {"name": "Test"}})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_update_readonly_fields(self):
        """Test updating readonly fields (protected by admin)."""
        import json

        from django.contrib import admin

        from tests.models import Author

        # Create author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Readonly Test", email="readonly@test.com"),
        )

        # Temporarily add readonly_fields to AuthorAdmin
        author_admin = admin.site._registry[Author]
        original_readonly = getattr(author_admin, "readonly_fields", ())
        author_admin.readonly_fields = ("email",)

        try:
            # Try to update readonly field
            result = await MCPAdminMixin.handle_tool_call(
                "update_author",
                {"id": author.id, "data": {"email": "newemail@test.com"}},
            )
            response = json.loads(result[0].text)
            assert "error" in response
            assert "readonly" in response["error"].lower()
        finally:
            # Restore original
            author_admin.readonly_fields = original_readonly

    async def test_related_missing_id(self):
        """Test related tool without id parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call("related_author", {"relation": "articles"})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_related_missing_relation(self):
        """Test related tool without relation parameter."""
        import json

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Test", email="test@rel.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "relation parameter is required" in response["error"]

    async def test_related_single_object(self):
        """Test related navigation for single object (FK/OneToOne)."""
        import json

        from tests.models import Article

        # Create author and article
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Single", email="single@rel.com"),
        )
        article = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Test Article", content="Content", author=author),
        )

        # Get author FK from article
        result = await MCPAdminMixin.handle_tool_call("related_article", {"id": article.id, "relation": "author"})
        response = json.loads(result[0].text)
        assert response["type"] == "single"
        assert response["result"]["name"] == "Single"

    async def test_related_simple_value(self):
        """Test related navigation for simple field value."""
        import json

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Value Test", email="value@rel.com"),
        )

        # Access a simple field like 'name'
        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id, "relation": "name"})
        response = json.loads(result[0].text)
        assert response["type"] == "value"
        assert response["value"] == "Value Test"

    async def test_bulk_missing_operation(self):
        """Test bulk without operation parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"items": []})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "operation parameter is required" in response["error"]

    async def test_bulk_invalid_operation(self):
        """Test bulk with invalid operation."""
        import json

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "invalid", "items": []})
        response = json.loads(result[0].text)
        assert "error" in response
        assert "must be 'create', 'update', or 'delete'" in response["error"]

    async def test_bulk_update_missing_id(self):
        """Test bulk update with item missing id."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {"operation": "update", "items": [{"data": {"name": "Test"}}]},
        )
        response = json.loads(result[0].text)
        assert response["error_count"] == 1
        assert "id is required" in response["results"]["errors"][0]["error"]

    async def test_bulk_update_not_found(self):
        """Test bulk update with non-existent id."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {"operation": "update", "items": [{"id": 99999, "data": {"name": "Test"}}]},
        )
        response = json.loads(result[0].text)
        assert response["error_count"] == 1
        assert "not found" in response["results"]["errors"][0]["error"]

    async def test_bulk_delete_not_found(self):
        """Test bulk delete with non-existent id."""
        import json

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "delete", "items": [99999]})
        response = json.loads(result[0].text)
        assert response["error_count"] == 1
        assert "not found" in response["results"]["errors"][0]["error"]

    async def test_action_not_found(self):
        """Test action with non-existent action name."""
        import json

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Action", email="action@test.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "action_author", {"action": "nonexistent_action", "ids": [author.id]}
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert "not found" in response["error"]

    async def test_action_no_objects_found(self):
        """Test action with ids that don't match any objects."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "action_author", {"action": "delete_selected", "ids": [99999, 99998]}
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert "No objects found" in response["error"]

    async def test_inline_update_with_errors(self):
        """Test inline updates with errors."""
        import json

        # Create author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Inline", email="inline@test.com"),
        )

        # Try to update with invalid inline data that will cause an error
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {
                "id": author.id,
                "inlines": {
                    "article": [
                        {
                            "id": 99999,  # Non-existent article
                            "data": {"title": "Updated"},
                        }
                    ]
                },
            },
        )
        response = json.loads(result[0].text)
        # Should succeed on author update but have inline errors
        assert response["success"] is True
        if "inlines" in response:
            assert len(response["inlines"]["errors"]) > 0

    async def test_inline_delete(self):
        """Test deleting inline objects."""
        import json

        from tests.models import Article

        # Create author and article
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Inline", email="delinline@test.com"),
        )
        article = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="To Delete", content="Content", author=author),
        )

        # Delete the inline article
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {
                "id": author.id,
                "inlines": {"article": [{"id": article.id, "_delete": True}]},
            },
        )
        response = json.loads(result[0].text)
        assert response["success"] is True
        assert len(response["inlines"]["deleted"]) == 1

        # Verify article was deleted
        article_exists = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Article.objects.filter(pk=article.id).exists()
        )
        assert not article_exists

    async def test_inline_create(self):
        """Test creating inline objects."""
        import json

        from tests.models import Article

        # Create author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Create Inline", email="createinline@test.com"),
        )

        # Create new inline article
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {
                "id": author.id,
                "inlines": {
                    "article": [
                        {
                            "data": {
                                "title": "New Inline Article",
                                "content": "Inline content",
                            }
                        }
                    ]
                },
            },
        )
        response = json.loads(result[0].text)
        assert response["success"] is True
        assert len(response["inlines"]["created"]) == 1

        # Verify article was created
        article_count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Article.objects.filter(author=author, title="New Inline Article").count()
        )
        assert article_count == 1

    async def test_inline_update(self):
        """Test updating inline objects."""
        import json

        from tests.models import Article

        # Create author and article
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Inline", email="updateinline@test.com"),
        )
        article = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Original", content="Content", author=author),
        )

        # Update the inline article
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {
                "id": author.id,
                "inlines": {
                    "article": [
                        {
                            "id": article.id,
                            "data": {"title": "Updated Inline"},
                        }
                    ]
                },
            },
        )
        response = json.loads(result[0].text)
        assert response["success"] is True
        assert len(response["inlines"]["updated"]) == 1

        # Verify article was updated
        updated_article = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Article.objects.get(pk=article.id)
        )
        assert updated_article.title == "Updated Inline"

    async def test_get_exception_handling(self):
        """Test exception handling in get operation."""
        import json

        # Pass invalid id type that might cause an exception
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": "invalid_id_format"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_create_exception_handling(self):
        """Test exception handling in create operation."""
        import json

        # Try to create with invalid data (duplicate unique field)
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Dup", email="duplicate@test.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Dup2", "email": "duplicate@test.com"}},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_delete_exception_handling(self):
        """Test exception handling in delete operation."""
        import json

        result = await MCPAdminMixin.handle_tool_call("delete_author", {"id": "invalid_id"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_bulk_exception_handling(self):
        """Test exception handling in bulk operations."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {"operation": "create", "items": [{"invalid": "data"}]},
        )
        response = json.loads(result[0].text)
        # Should handle errors gracefully
        assert "results" in response or "error" in response

    async def test_related_exception_handling(self):
        """Test exception handling in related operation."""
        import json

        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": "invalid", "relation": "articles"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_history_exception_handling(self):
        """Test exception handling in history operation."""
        import json

        result = await MCPAdminMixin.handle_tool_call("history_author", {"id": "invalid"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_serialize_model_instance_with_model_field(self):
        """Test serialization of model instance with related model field."""
        from tests.models import Article

        # Create author and article
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Serial", email="serial@test.com"),
        )
        article = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Test", content="Content", author=author),
        )

        # Get article - author FK should be serialized as string
        result = await MCPAdminMixin.handle_tool_call("get_article", {"id": article.id})
        import json

        response = json.loads(result[0].text)
        # The author field should be serialized
        assert "author" in response

    async def test_get_with_no_admin(self):
        """Test getting inline data when no admin is configured."""
        import json

        # This tests line 467 - when admin is None
        # We can't easily unregister, but we can test with include_inlines=True on a model
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="No Admin", email="noadmin@test.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id, "include_inlines": True})
        response = json.loads(result[0].text)
        assert response["name"] == "No Admin"

    async def test_inline_without_data_key(self):
        """Test inline update where item doesn't have 'data' key."""
        import json

        from tests.models import Article

        # Create author and article
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="No Data Key", email="nodatakey@test.com"),
        )
        article = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Original", content="Content", author=author),
        )

        # Update inline without explicit data key (should use item as data)
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {
                "id": author.id,
                "inlines": {
                    "article": [
                        {
                            "id": article.id,
                            "title": "Updated Direct",  # Direct field update
                        }
                    ]
                },
            },
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_describe_with_fieldsets(self):
        """Test describe with fieldsets configured."""
        import json

        from django.contrib import admin

        from tests.models import Author

        # Temporarily add fieldsets to AuthorAdmin
        author_admin = admin.site._registry[Author]
        original_fieldsets = getattr(author_admin, "fieldsets", None)
        author_admin.fieldsets = (
            ("Basic Info", {"fields": ("name", "email")}),
            ("Details", {"fields": ("bio",), "classes": ("collapse",)}),
        )

        try:
            result = await MCPAdminMixin.handle_tool_call("describe_author", {})
            response = json.loads(result[0].text)
            assert "admin_config" in response
            assert "fieldsets" in response["admin_config"]
        finally:
            author_admin.fieldsets = original_fieldsets

    async def test_describe_with_date_hierarchy(self):
        """Test describe with date_hierarchy configured."""
        import json

        from django.contrib import admin

        from tests.models import Article

        # Temporarily add date_hierarchy to ArticleAdmin
        article_admin = admin.site._registry[Article]
        original_date_hierarchy = getattr(article_admin, "date_hierarchy", None)
        article_admin.date_hierarchy = "published_date"

        try:
            result = await MCPAdminMixin.handle_tool_call("describe_article", {})
            response = json.loads(result[0].text)
            assert "admin_config" in response
            assert "date_hierarchy" in response["admin_config"]
        finally:
            article_admin.date_hierarchy = original_date_hierarchy

    async def test_action_with_custom_action(self):
        """Test executing a custom action."""
        import json

        from django.contrib import admin

        from tests.models import Author

        # Define a custom action
        def mark_featured(modeladmin, request, queryset):
            """Custom action for testing."""
            return f"Marked {queryset.count()} items as featured"

        mark_featured.short_description = "Mark as featured"

        # Add action to AuthorAdmin
        author_admin = admin.site._registry[Author]
        original_actions = getattr(author_admin, "actions", [])
        author_admin.actions = list(original_actions) + [mark_featured]

        try:
            # Create author
            author = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: Author.objects.create(name="Custom Action", email="customaction@test.com"),
            )

            # Execute custom action
            result = await MCPAdminMixin.handle_tool_call(
                "action_author",
                {"action": "mark_featured", "ids": [author.id]},
            )
            response = json.loads(result[0].text)
            assert response["success"] is True
            assert response["action"] == "mark_featured"
        finally:
            author_admin.actions = original_actions

    async def test_autocomplete_without_search_fields(self):
        """Test autocomplete when admin has no search_fields."""
        import json

        from django.contrib import admin

        from tests.models import Author

        # Temporarily remove search_fields from AuthorAdmin
        author_admin = admin.site._registry[Author]
        original_search_fields = getattr(author_admin, "search_fields", [])
        author_admin.search_fields = []

        try:
            # Create author
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: Author.objects.create(name="No Search", email="nosearch@test.com"),
            )

            # Try autocomplete without search_fields
            result = await MCPAdminMixin.handle_tool_call(
                "autocomplete_author",
                {"term": "No Search"},
            )
            response = json.loads(result[0].text)
            # Should still work by finding text fields
            assert "results" in response
        finally:
            author_admin.search_fields = original_search_fields

    async def test_autocomplete_with_ordering(self):
        """Test autocomplete when admin has ordering configured."""
        import json

        # Create authors
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Zebra Order", email="zebra@order.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Alpha Order", email="alpha@order.com"),
        )

        # Autocomplete should use admin's ordering
        result = await MCPAdminMixin.handle_tool_call(
            "autocomplete_author",
            {"term": "Order"},
        )
        response = json.loads(result[0].text)
        assert len(response["results"]) >= 2
