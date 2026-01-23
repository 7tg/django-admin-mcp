"""
Tests for CRUD operations via MCP tools
"""

import asyncio

import pytest

from django_admin_mcp import MCPAdminMixin
from tests.models import Author


@pytest.mark.django_db
@pytest.mark.asyncio
class TestCRUDOperations:
    """Test suite for CRUD operations."""

    async def test_create_author(self):
        """Test creating an author via MCP."""
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {
                "data": {
                    "name": "Test Author",
                    "email": "test@example.com",
                    "bio": "Test bio",
                }
            },
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True
        assert "id" in response
        assert response["object"]["name"] == "Test Author"

    async def test_list_authors(self):
        """Test listing authors via MCP."""
        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 1", email="author1@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("list_author", {"limit": 10})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "count" in response
        assert "results" in response
        assert response["count"] >= 1

    async def test_get_author(self):
        """Test getting a specific author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 2", email="author2@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["name"] == "Author 2"
        assert response["email"] == "author2@example.com"

    async def test_update_author(self):
        """Test updating an author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 3", email="author3@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "update_author", {"id": author.id, "data": {"name": "Updated Author"}}
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True
        assert response["object"]["name"] == "Updated Author"

    async def test_delete_author(self):
        """Test deleting an author via MCP."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 4", email="author4@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("delete_author", {"id": author.id})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_get_nonexistent_author(self):
        """Test getting a nonexistent author returns error."""
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": 99999})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "error" in response

    async def test_update_invalid_field(self):
        """Test updating with invalid field returns error."""
        # Create test data
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Author 5", email="author5@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "update_author", {"id": author.id, "data": {"invalid_field": "value"}}
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "error" in response
        assert "Invalid field" in response["error"]

    async def test_create_article_with_author(self):
        """Test creating an article with author relationship."""
        # Create author first
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Article Author", email="articleauthor@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "create_article",
            {
                "data": {
                    "title": "Test Article",
                    "content": "Test content",
                    "author_id": author.id,  # Use author_id for foreign key
                    "is_published": True,
                }
            },
        )

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        # Check if error or success
        if "error" in response:
            # If there's an error, the test should explain what went wrong
            pytest.fail(f"Failed to create article: {response['error']}")
        assert response["success"] is True
        assert response["object"]["title"] == "Test Article"

    async def test_find_models(self):
        """Test finding models via find_models tool."""
        # Call find_models without query
        result = await MCPAdminMixin.handle_tool_call("find_models", {})

        assert len(result) == 1
        import json

        response = json.loads(result[0].text)
        assert "count" in response
        assert "models" in response
        assert response["count"] >= 2  # Should find at least author and article

        # Verify that models are in the results
        model_names = [m["model_name"] for m in response["models"]]
        assert "author" in model_names
        assert "article" in model_names

        # Test with query filter
        result = await MCPAdminMixin.handle_tool_call("find_models", {"query": "author"})

        response = json.loads(result[0].text)
        assert "count" in response
        assert response["count"] >= 1
        model_names = [m["model_name"] for m in response["models"]]
        assert "author" in model_names


@pytest.mark.django_db
@pytest.mark.asyncio
class TestFilteringSearchingOrdering:
    """Test suite for filtering, searching, and ordering operations."""

    async def test_list_with_filters(self):
        """Test listing with filter criteria."""
        import json

        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Alice Smith", email="alice@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Jones", email="bob@example.com"),
        )

        # Filter by exact name
        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"name": "Alice Smith"}})
        response = json.loads(result[0].text)
        assert response["count"] == 1
        assert response["results"][0]["name"] == "Alice Smith"

    async def test_list_with_icontains_filter(self):
        """Test listing with icontains filter lookup."""
        import json

        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Charlie Brown", email="charlie@example.com"),
        )

        # Filter by name containing 'brown' (case-insensitive)
        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"name__icontains": "brown"}})
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        assert any("Brown" in r["name"] for r in response["results"])

    async def test_list_with_search(self):
        """Test listing with search term."""
        import json

        # Create test data
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Searchable Author", email="search@example.com"),
        )

        # Search for 'searchable'
        result = await MCPAdminMixin.handle_tool_call("list_author", {"search": "Searchable"})
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        assert any("Searchable" in r["name"] for r in response["results"])

    async def test_list_with_ordering(self):
        """Test listing with custom ordering."""
        import json

        # Clear existing and create test data with predictable names
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(name__startswith="Order").delete()
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Order Zebra", email="zebra@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Order Alpha", email="alpha@example.com"),
        )

        # Order by name ascending
        result = await MCPAdminMixin.handle_tool_call(
            "list_author",
            {"filters": {"name__icontains": "Order"}, "order_by": ["name"]},
        )
        response = json.loads(result[0].text)
        names = [r["name"] for r in response["results"]]
        assert names.index("Order Alpha") < names.index("Order Zebra")

        # Order by name descending
        result = await MCPAdminMixin.handle_tool_call(
            "list_author",
            {"filters": {"name__icontains": "Order"}, "order_by": ["-name"]},
        )
        response = json.loads(result[0].text)
        names = [r["name"] for r in response["results"]]
        assert names.index("Order Zebra") < names.index("Order Alpha")

    async def test_list_total_count(self):
        """Test that list returns total_count for pagination."""
        import json

        # Create multiple test authors
        for i in range(5):
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda i=i: Author.objects.create(name=f"Count Author {i}", email=f"count{i}@example.com"),
            )

        # Request with limit smaller than total
        result = await MCPAdminMixin.handle_tool_call(
            "list_author", {"filters": {"name__icontains": "Count Author"}, "limit": 2}
        )
        response = json.loads(result[0].text)
        assert response["count"] == 2  # Items returned
        assert response["total_count"] >= 5  # Total matching items

    async def test_list_with_invalid_filter_field(self):
        """Test that invalid filter fields are ignored."""
        import json

        result = await MCPAdminMixin.handle_tool_call("list_author", {"filters": {"invalid_field": "value"}})
        response = json.loads(result[0].text)
        # Should not error, just ignore the invalid filter
        assert "results" in response

    async def test_list_combined_filters_search_ordering(self):
        """Test combining filters, search, and ordering."""
        import json

        from tests.models import Article

        # Create test author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Combined Author", email="combined@example.com"),
        )

        # Create test articles
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(
                title="Published Python Guide",
                content="Python programming",
                author=author,
                is_published=True,
            ),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(
                title="Draft Python Tutorial",
                content="More Python",
                author=author,
                is_published=False,
            ),
        )

        # Filter by is_published, search for 'Python', order by title
        result = await MCPAdminMixin.handle_tool_call(
            "list_article",
            {
                "filters": {"is_published": True},
                "search": "Python",
                "order_by": ["title"],
            },
        )
        response = json.loads(result[0].text)
        assert response["count"] >= 1
        # All results should be published
        assert all(r.get("is_published", True) for r in response["results"])


@pytest.mark.django_db
@pytest.mark.asyncio
class TestDescribeModel:
    """Test suite for describe_<model_name> tool."""

    async def test_describe_author(self):
        """Test describing the Author model."""
        import json

        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        # Check basic model info
        assert response["model_name"] == "author"
        assert "verbose_name" in response
        assert "fields" in response
        assert "relationships" in response
        assert "admin_config" in response

    async def test_describe_fields(self):
        """Test that describe returns correct field metadata."""
        import json

        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        # Find specific fields
        field_names = [f["name"] for f in response["fields"]]
        assert "name" in field_names
        assert "email" in field_names
        assert "bio" in field_names

        # Check field details
        name_field = next(f for f in response["fields"] if f["name"] == "name")
        assert name_field["type"] == "CharField"
        assert name_field["max_length"] == 200
        assert name_field["required"] is True

    async def test_describe_relationships(self):
        """Test that describe returns relationship info."""
        import json

        result = await MCPAdminMixin.handle_tool_call("describe_article", {})
        response = json.loads(result[0].text)

        # Article has FK to Author
        relationships = response["relationships"]
        author_rel = next((r for r in relationships if r["name"] == "author"), None)
        assert author_rel is not None
        assert author_rel["related_model"] == "author"

    async def test_describe_admin_config(self):
        """Test that describe returns admin configuration."""
        import json

        result = await MCPAdminMixin.handle_tool_call("describe_author", {})
        response = json.loads(result[0].text)

        admin_config = response["admin_config"]
        assert "list_display" in admin_config
        assert "search_fields" in admin_config
        assert "ordering" in admin_config

        # Check configured values from conftest.py
        assert "name" in admin_config["list_display"]
        assert "email" in admin_config["list_display"]
        assert "name" in admin_config["search_fields"]
        assert "name" in admin_config["ordering"]


@pytest.mark.django_db
@pytest.mark.asyncio
class TestActionsAndBulk:
    """Test suite for actions and bulk operations."""

    async def test_list_actions(self):
        """Test listing available actions for a model."""
        import json

        result = await MCPAdminMixin.handle_tool_call("actions_author", {})
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert "actions" in response
        # delete_selected should be available by default
        action_names = [a["name"] for a in response["actions"]]
        assert "delete_selected" in action_names

    async def test_action_delete_selected(self):
        """Test executing delete_selected action."""
        import json

        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Me 1", email="delete1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Me 2", email="delete2@example.com"),
        )

        # Execute delete_selected action
        result = await MCPAdminMixin.handle_tool_call(
            "action_author",
            {"action": "delete_selected", "ids": [author1.id, author2.id]},
        )
        response = json.loads(result[0].text)

        assert response["success"] is True
        assert response["action"] == "delete_selected"
        assert response["affected_count"] == 2

        # Verify deletion
        count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(pk__in=[author1.id, author2.id]).count()
        )
        assert count == 0

    async def test_action_missing_params(self):
        """Test action with missing parameters."""
        import json

        # Missing action name
        result = await MCPAdminMixin.handle_tool_call("action_author", {"ids": [1, 2]})
        response = json.loads(result[0].text)
        assert "error" in response

        # Missing ids
        result = await MCPAdminMixin.handle_tool_call("action_author", {"action": "delete_selected"})
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_bulk_create(self):
        """Test bulk create operation."""
        import json

        items = [
            {"name": "Bulk Author 1", "email": "bulk1@example.com"},
            {"name": "Bulk Author 2", "email": "bulk2@example.com"},
            {"name": "Bulk Author 3", "email": "bulk3@example.com"},
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "create", "items": items})
        response = json.loads(result[0].text)

        assert response["operation"] == "create"
        assert response["success_count"] == 3
        assert response["error_count"] == 0

    async def test_bulk_update(self):
        """Test bulk update operation."""
        import json

        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Me 1", email="update1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Me 2", email="update2@example.com"),
        )

        items = [
            {"id": author1.id, "data": {"name": "Updated 1"}},
            {"id": author2.id, "data": {"name": "Updated 2"}},
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "update", "items": items})
        response = json.loads(result[0].text)

        assert response["operation"] == "update"
        assert response["success_count"] == 2

        # Verify updates
        updated1 = await asyncio.get_event_loop().run_in_executor(None, lambda: Author.objects.get(pk=author1.id))
        assert updated1.name == "Updated 1"

    async def test_bulk_delete(self):
        """Test bulk delete operation."""
        import json

        # Create test authors
        author1 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bulk Delete 1", email="bulkdel1@example.com"),
        )
        author2 = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bulk Delete 2", email="bulkdel2@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author", {"operation": "delete", "items": [author1.id, author2.id]}
        )
        response = json.loads(result[0].text)

        assert response["operation"] == "delete"
        assert response["success_count"] == 2

        # Verify deletion
        count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: Author.objects.filter(pk__in=[author1.id, author2.id]).count()
        )
        assert count == 0

    async def test_bulk_with_errors(self):
        """Test bulk operation with some errors."""
        import json

        # First create an author with a specific email
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Existing", email="duplicate@example.com"),
        )

        items = [
            {"name": "Valid Author", "email": "bulkerror@example.com"},
            {
                "name": "Duplicate Email",
                "email": "duplicate@example.com",
            },  # Will fail - duplicate email
        ]

        result = await MCPAdminMixin.handle_tool_call("bulk_author", {"operation": "create", "items": items})
        response = json.loads(result[0].text)

        assert response["success_count"] == 1
        assert response["error_count"] == 1
        assert len(response["results"]["errors"]) == 1


@pytest.mark.django_db
@pytest.mark.asyncio
class TestInlineAndRelated:
    """Test suite for inline and related object operations."""

    async def test_get_with_include_related(self):
        """Test getting an object with related data."""
        import json

        from tests.models import Article

        # Create author with articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Related Author", email="related@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Related Article 1", content="Content 1", author=author),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Related Article 2", content="Content 2", author=author),
        )

        # Get author with related data
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id, "include_related": True})
        response = json.loads(result[0].text)

        assert response["name"] == "Related Author"
        assert "_related" in response
        assert "articles" in response["_related"]
        assert len(response["_related"]["articles"]) == 2

    async def test_get_with_include_inlines(self):
        """Test getting an object with inline data."""
        import json

        from tests.models import Article

        # Create author with articles (which are configured as inlines)
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Inline Author", email="inline@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Inline Article", content="Content", author=author),
        )

        # Get author with inline data
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id, "include_inlines": True})
        response = json.loads(result[0].text)

        assert response["name"] == "Inline Author"
        assert "_inlines" in response
        assert "article" in response["_inlines"]
        assert len(response["_inlines"]["article"]) >= 1

    async def test_related_navigation(self):
        """Test fetching related objects via related_ tool."""
        import json

        from tests.models import Article

        # Create author with articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Nav Author", email="nav@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Nav Article 1", content="Content 1", author=author),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Article.objects.create(title="Nav Article 2", content="Content 2", author=author),
        )

        # Navigate to related articles
        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id, "relation": "articles"})
        response = json.loads(result[0].text)

        assert response["relation"] == "articles"
        assert response["type"] == "many"
        assert response["total_count"] == 2
        assert len(response["results"]) == 2

    async def test_related_with_pagination(self):
        """Test related navigation with pagination."""
        import json

        from tests.models import Article

        # Create author with many articles
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Paginate Author", email="paginate@example.com"),
        )
        for i in range(5):
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda i=i: Article.objects.create(
                    title=f"Paginate Article {i}", content=f"Content {i}", author=author
                ),
            )

        # Get first page
        result = await MCPAdminMixin.handle_tool_call(
            "related_author",
            {"id": author.id, "relation": "articles", "limit": 2, "offset": 0},
        )
        response = json.loads(result[0].text)

        assert response["total_count"] == 5
        assert response["count"] == 2

    async def test_related_invalid_relation(self):
        """Test related navigation with invalid relation name."""
        import json

        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Invalid Author", email="invalid@example.com"),
        )

        result = await MCPAdminMixin.handle_tool_call("related_author", {"id": author.id, "relation": "nonexistent"})
        response = json.loads(result[0].text)

        assert "error" in response


@pytest.mark.django_db
@pytest.mark.asyncio
class TestPermissionChecks:
    """Test suite for permission checking functionality."""

    async def test_superuser_can_do_everything(self):
        """Test that superuser has all permissions."""
        import json

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="superadmin",
                email="superadmin@example.com",
                password="superpass123",
            ),
        )

        # Create an author first
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Perm Test Author", email="permtest@example.com"),
        )

        # Test list (view permission)
        result = await MCPAdminMixin.handle_tool_call("list_author", {}, user=superuser)
        response = json.loads(result[0].text)
        assert "results" in response

        # Test get (view permission)
        result = await MCPAdminMixin.handle_tool_call("get_author", {"id": author.id}, user=superuser)
        response = json.loads(result[0].text)
        assert response["name"] == "Perm Test Author"

        # Test create (add permission)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "New Author", "email": "newauthor@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Test update (change permission)
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author.id, "data": {"name": "Updated Name"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_no_user_allows_all_operations(self):
        """Test that operations work without a user (backwards compatibility)."""
        import json

        # Create an author
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="No User Author", email="nouser@example.com"),
        )

        # Test list without user
        result = await MCPAdminMixin.handle_tool_call("list_author", {}, user=None)
        response = json.loads(result[0].text)
        assert "results" in response

        # Test create without user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Anonymous Create", "email": "anoncreate@example.com"}},
            user=None,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_regular_user_without_permissions(self):
        """Test that regular user without permissions gets denied."""
        import json

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a regular user without any permissions
        regular_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(
                username="regularuser",
                email="regular@example.com",
                password="regularpass123",
            ),
        )

        # Test create without permission (should be denied)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Should Fail", "email": "shouldfail@example.com"}},
            user=regular_user,
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert response.get("code") == "permission_denied"

    async def test_staff_user_with_add_permission(self):
        """Test that staff user with add permission can create."""
        import json

        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        User = get_user_model()

        # Create a staff user
        staff_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(
                username="staffuser",
                email="staff@example.com",
                password="staffpass123",
                is_staff=True,
            ),
        )

        # Add the add_author permission
        def add_permission():
            content_type = ContentType.objects.get_for_model(Author)
            permission = Permission.objects.get(codename="add_author", content_type=content_type)
            staff_user.user_permissions.add(permission)
            staff_user.save()
            # Clear permission cache
            staff_user._perm_cache = {}
            staff_user._user_perm_cache = {}

        await asyncio.get_event_loop().run_in_executor(None, add_permission)

        # Refetch user to get fresh permissions
        staff_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.get(pk=staff_user.pk),
        )

        # Test create with permission (should succeed)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Staff Create", "email": "staffcreate@example.com"}},
            user=staff_user,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

    async def test_bulk_permission_check(self):
        """Test that bulk operations check permissions."""
        import json

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a regular user without permissions
        regular_user = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_user(username="bulkuser", email="bulk@example.com", password="bulkpass123"),
        )

        # Test bulk create without permission (should be denied)
        result = await MCPAdminMixin.handle_tool_call(
            "bulk_author",
            {
                "operation": "create",
                "items": [{"name": "Bulk Fail", "email": "bulkfail@example.com"}],
            },
            user=regular_user,
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert response.get("code") == "permission_denied"


@pytest.mark.django_db
@pytest.mark.asyncio
class TestLogEntryIntegration:
    """Test suite for LogEntry integration."""

    async def test_create_logs_entry(self):
        """Test that creating an object logs an entry."""
        import json

        from django.contrib.admin.models import ADDITION, LogEntry
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logadmin", email="logadmin@example.com", password="logpass123"
            ),
        )

        # Create an author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Logged Author", "email": "logged@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert "error" not in response, f"Got error: {response}"
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=ADDITION,
            ).first(),
        )
        assert log_entry is not None
        assert "Created via MCP" in log_entry.change_message
        assert log_entry.object_repr == "Logged Author"

    async def test_update_logs_entry(self):
        """Test that updating an object logs an entry."""
        import json

        from django.contrib.admin.models import CHANGE, LogEntry
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logupdater",
                email="logupdater@example.com",
                password="logpass123",
            ),
        )

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Update Log Author", email="updatelog@example.com"),
        )

        # Update the author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author.id, "data": {"name": "Updated Log Author"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=CHANGE,
                object_id=str(author.id),
            ).first(),
        )
        assert log_entry is not None
        assert "Changed via MCP" in log_entry.change_message

    async def test_delete_logs_entry(self):
        """Test that deleting an object logs an entry."""
        import json

        from django.contrib.admin.models import DELETION, LogEntry
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="logdeleter",
                email="logdeleter@example.com",
                password="logpass123",
            ),
        )

        # Create an author
        author = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Delete Log Author", email="deletelog@example.com"),
        )
        author_id = author.id

        # Delete the author with the user
        result = await MCPAdminMixin.handle_tool_call(
            "delete_author",
            {"id": author_id},
            user=superuser,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that a LogEntry was created
        log_entry = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: LogEntry.objects.filter(
                user_id=superuser.pk,
                action_flag=DELETION,
                object_id=str(author_id),
            ).first(),
        )
        assert log_entry is not None
        assert "Deleted via MCP" in log_entry.change_message

    async def test_no_log_without_user(self):
        """Test that no LogEntry is created without a user."""
        import json

        from django.contrib.admin.models import LogEntry

        # Get initial count
        initial_count = await asyncio.get_event_loop().run_in_executor(None, LogEntry.objects.count)

        # Create an author without user
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "No Log Author", "email": "nolog@example.com"}},
            user=None,
        )
        response = json.loads(result[0].text)
        assert response["success"] is True

        # Check that no new LogEntry was created
        final_count = await asyncio.get_event_loop().run_in_executor(None, LogEntry.objects.count)
        assert final_count == initial_count


@pytest.mark.django_db
@pytest.mark.asyncio
class TestHistoryTool:
    """Test suite for history_<model_name> tool."""

    async def test_history_returns_log_entries(self):
        """Test that history tool returns LogEntry records."""
        import json

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="histadmin",
                email="histadmin@example.com",
                password="histpass123",
            ),
        )

        # Create an author with the user (will log creation)
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "History Author", "email": "history@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        author_id = response["id"]

        # Update the author (will log change)
        result = await MCPAdminMixin.handle_tool_call(
            "update_author",
            {"id": author_id, "data": {"name": "Updated History Author"}},
            user=superuser,
        )

        # Get history
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": author_id},
        )
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert response["object_id"] == author_id
        assert response["count"] >= 2  # At least create and update
        assert len(response["history"]) >= 2

        # Check that history entries have expected fields
        for entry in response["history"]:
            assert "action" in entry
            assert "action_time" in entry
            assert "user" in entry
            assert "change_message" in entry
            assert entry["user"] == "histadmin"

        # The most recent should be the change, then creation
        assert response["history"][0]["action"] == "changed"
        assert response["history"][1]["action"] == "created"

    async def test_history_not_found(self):
        """Test that history tool returns error for non-existent object."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": 99999},
        )
        response = json.loads(result[0].text)
        assert "error" in response

    async def test_history_requires_id(self):
        """Test that history tool requires id parameter."""
        import json

        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {},
        )
        response = json.loads(result[0].text)
        assert "error" in response
        assert "id parameter is required" in response["error"]

    async def test_history_with_limit(self):
        """Test that history tool respects limit parameter."""
        import json

        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Create a superuser
        superuser = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: User.objects.create_superuser(
                username="limitadmin",
                email="limitadmin@example.com",
                password="limitpass123",
            ),
        )

        # Create an author
        result = await MCPAdminMixin.handle_tool_call(
            "create_author",
            {"data": {"name": "Limit Author", "email": "limit@example.com"}},
            user=superuser,
        )
        response = json.loads(result[0].text)
        author_id = response["id"]

        # Do multiple updates
        for i in range(5):
            await MCPAdminMixin.handle_tool_call(
                "update_author",
                {"id": author_id, "data": {"name": f"Limit Author {i}"}},
                user=superuser,
            )

        # Get history with limit
        result = await MCPAdminMixin.handle_tool_call(
            "history_author",
            {"id": author_id, "limit": 3},
        )
        response = json.loads(result[0].text)

        # Should have at most 3 entries
        assert response["count"] <= 3


@pytest.mark.django_db
@pytest.mark.asyncio
class TestAutocomplete:
    """Test suite for autocomplete tool."""

    async def test_autocomplete_returns_results(self):
        """Test that autocomplete tool returns results."""
        import json
        import uuid

        unique_suffix = uuid.uuid4().hex[:8]

        # Create some authors with unique emails
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="John Doe", email=f"john_{unique_suffix}@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Jane Doe", email=f"jane_{unique_suffix}@example.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Smith", email=f"bob_{unique_suffix}@example.com"),
        )

        # Test autocomplete without term
        result = await MCPAdminMixin.handle_tool_call(
            "autocomplete_author",
            {},
        )
        response = json.loads(result[0].text)

        assert response["model"] == "author"
        assert response["count"] >= 3
        assert "results" in response
        for item in response["results"]:
            assert "id" in item
            assert "text" in item

    async def test_autocomplete_with_search_term(self):
        """Test that autocomplete tool filters by search term."""
        import json

        # Create some authors
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Alice Autocomplete", email="alice@auto.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Bob Autocomplete", email="bob@auto.com"),
        )
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: Author.objects.create(name="Charlie Unique", email="charlie@unique.com"),
        )

        # Search for "Autocomplete"
        result = await MCPAdminMixin.handle_tool_call(
            "autocomplete_author",
            {"term": "Autocomplete"},
        )
        response = json.loads(result[0].text)

        assert response["term"] == "Autocomplete"
        assert response["count"] == 2  # Only Alice and Bob

        # Verify the results contain the expected names
        names = [r["text"] for r in response["results"]]
        assert all("Autocomplete" in name for name in names)
