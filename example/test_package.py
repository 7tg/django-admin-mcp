#!/usr/bin/env python
"""
Simple test script to verify the django-admin-mcp package works correctly.
"""

import os
import sys

import django

# Add the parent directory to the path so we can import django_admin_mcp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'example_project.settings')
django.setup()

# Now test the package
from blog.models import Article, Author

from django_admin_mcp import MCPAdminMixin, get_registered_models, get_server


def test_package():
    """Test the package functionality."""
    print("Testing django-admin-mcp package...")

    # Test 1: Check that models are registered
    print("\n1. Checking registered models...")
    registered = get_registered_models()
    print(f"   Registered models: {list(registered.keys())}")
    assert 'article' in registered, "Article model should be registered"
    assert 'author' in registered, "Author model should be registered"
    print("   ✓ Models registered successfully")

    # Test 2: Check MCP server instance
    print("\n2. Checking MCP server...")
    server = get_server()
    assert server is not None, "MCP server should be created"
    print(f"   ✓ MCP server created: {server.name}")

    # Test 3: Check tools generation
    print("\n3. Checking tool generation...")
    article_tools = MCPAdminMixin.get_mcp_tools(Article)
    author_tools = MCPAdminMixin.get_mcp_tools(Author)

    print(f"   Article tools: {[t.name for t in article_tools]}")
    print(f"   Author tools: {[t.name for t in author_tools]}")

    expected_article_tools = ['list_article', 'get_article', 'create_article', 'update_article', 'delete_article']
    expected_author_tools = ['list_author', 'get_author', 'create_author', 'update_author', 'delete_author']

    actual_article_tools = [t.name for t in article_tools]
    actual_author_tools = [t.name for t in author_tools]

    assert actual_article_tools == expected_article_tools, f"Expected {expected_article_tools}, got {actual_article_tools}"
    assert actual_author_tools == expected_author_tools, f"Expected {expected_author_tools}, got {actual_author_tools}"
    print("   ✓ Tools generated correctly")

    # Test 4: Verify tool schemas
    print("\n4. Checking tool schemas...")
    for tool in article_tools:
        assert tool.inputSchema is not None, f"Tool {tool.name} should have an input schema"
        assert 'type' in tool.inputSchema, f"Tool {tool.name} schema should have a type"
    print("   ✓ Tool schemas are valid")

    print("\n✅ All tests passed!")

if __name__ == '__main__':
    try:
        test_package()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
