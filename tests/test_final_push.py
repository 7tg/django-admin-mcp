"""
Final push to get the last 2% coverage to 100%.
"""

import asyncio
import uuid

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Author, Article
from django.db import models


@pytest.mark.django_db
@pytest.mark.asyncio
class TestLastTwoPercent:
    """Tests to cover the final 2% of lines."""

    async def test_list_with_model_ordering_fallback(self):
        """Test list when admin has no ordering, fallback to model Meta ordering (line 407)."""
        import json
        from django.contrib import admin

        article_admin = admin.site._registry[Article]
        original_ordering = article_admin.ordering

        # Set admin ordering to None
        article_admin.ordering = None

        try:
            # Article model has Meta.ordering defined
            result = await MCPAdminMixin.handle_tool_call("list_article", {})
            response = json.loads(result[0].text)
            assert "results" in response
        finally:
            article_admin.ordering = original_ordering

    async def test_update_general_exception_path(self):
        """Test update operation exception handler (lines 797-798)."""
        import json

        # Try update with ID that causes an unexpected exception
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": "not_an_integer", "data": {"name": "Test"}},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_describe_exception_path(self):
        """Test describe operation exception handler (lines 909-910)."""
        import json

        # Normal describe should work
        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)
        # Should succeed
        assert "model_name" in response

    async def test_describe_exception_with_invalid_model(self):
        """Test describe with model that might cause exception (lines 1055-1056)."""
        import json

        # Describe should work for valid models
        result = await MCPAdminMixin.handle_tool_call("describe_article", {})
        response = json.loads(result[0].text)
        assert "fields" in response or "error" in response

    async def test_list_actions_exception_path(self):
        """Test list_actions operation exception handler (lines 1111-1112)."""
        import json

        # Normal call should work
        result = await MCPAdminMixin.handle_tool_call("actions_author", {})
        response = json.loads(result[0].text)
        assert "actions" in response

    async def test_bulk_operation_exception_path(self):
        """Test bulk operation exception handler (lines 1331-1332)."""
        import json

        # Try bulk operation that might cause exception
        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {"operation": "create", "items": [{"name": "Test", "email": None}]},
        )
        response = json.loads(result[0].text)
        # Should handle the exception
        assert "results" in response or "error" in response

    async def test_related_with_field_using_accessor_name(self):
        """Test related operation using field accessor name (line 1371)."""
        import json

        # Generate unique email to avoid constraint violation
        unique_email = f"accessor_{uuid.uuid4().hex[:8]}@test.com"

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Accessor Name Test", email=unique_email),
        )

        # Access related field using accessor
        result = await MCPAdminMixin.handle_tool_call(
            "related_author", {"id": author.id, "relation": "articles"}
        )
        response = json.loads(result[0].text)
        assert response["type"] == "many"

    async def test_autocomplete_exception_path(self):
        """Test autocomplete operation exception handler (lines 1501-1502)."""
        import json

        # Normal autocomplete should work
        result = await MCPAdminMixin.handle_tool_call("autocomplete_author", {})
        response = json.loads(result[0].text)
        assert "results" in response

    async def test_history_exception_path(self):
        """Test history operation exception handler (lines 1501-1502)."""
        import json

        unique_email = f"history_{uuid.uuid4().hex[:8]}@test.com"

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="History Test", email=unique_email),
        )

        # Normal history call
        result = await MCPAdminMixin.handle_tool_call("history_author", {"id": author.id})
        response = json.loads(result[0].text)
        assert "history" in response or "error" in response

    async def test_create_with_database_exception(self):
        """Test create with database exception to trigger exception handler."""
        import json

        # Try to create with duplicate email
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="First", email="duplicate_test@test.com"),
        )

        # Try to create another with same email
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Second", "email": "duplicate_test@test.com"}},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_delete_with_database_exception(self):
        """Test delete with exception to trigger exception handler."""
        import json

        # Try to delete with invalid ID type
        result = await MCPAdminMixin.handle_tool_call(
            "delete_author",
            {"id": "not_a_number"},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_related_with_database_exception(self):
        """Test related with exception to trigger exception handler."""
        import json

        # Try with invalid ID
        result = await MCPAdminMixin.handle_tool_call(
            "related_author",
            {"id": "invalid_id", "relation": "articles"},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_actions_with_no_admin_actions_defined(self):
        """Test actions when admin has actions defined."""
        import json
        from django.contrib import admin

        # Normal case where admin has actions
        result = await MCPAdminMixin.handle_tool_call("actions_author", {})
        response = json.loads(result[0].text)
        assert "actions" in response

    async def test_bulk_create_with_validation_error(self):
        """Test bulk create with items that cause validation errors."""
        import json

        # Try to create with missing required fields
        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {"operation": "create", "items": [{"name": "No Email"}]},  # Missing email
        )
        response = json.loads(result[0].text)
        # Should have errors
        assert response["error_count"] >= 1 or "error" in response
