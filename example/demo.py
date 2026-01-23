#!/usr/bin/env python
"""
Quick start script to demonstrate django-admin-mcp functionality.

This script:
1. Sets up the Django environment
2. Creates sample data (authors and articles)
3. Demonstrates how MCP tools can be used programmatically
"""

import asyncio
import os

import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'example_project.settings')
django.setup()

from datetime import datetime

from asgiref.sync import sync_to_async
from blog.models import Article, Author

from django_admin_mcp import MCPAdminMixin, get_registered_models


def create_sample_data():
    """Create sample data in the database."""
    # Clear existing data
    Article.objects.all().delete()
    Author.objects.all().delete()

    # Create authors
    author1 = Author.objects.create(
        name="Jane Doe",
        email="jane@example.com",
        bio="Technology writer and blogger"
    )
    print(f"   ✓ Created author: {author1.name}")

    author2 = Author.objects.create(
        name="John Smith",
        email="john@example.com",
        bio="Science fiction author"
    )
    print(f"   ✓ Created author: {author2.name}")

    # Create articles
    article1 = Article.objects.create(
        title="Getting Started with Django",
        content="Django is a high-level Python web framework...",
        author=author1,
        is_published=True,
        published_date=datetime.now()
    )
    print(f"   ✓ Created article: {article1.title}")

    article2 = Article.objects.create(
        title="Introduction to MCP",
        content="Model Context Protocol enables AI assistants...",
        author=author1,
        is_published=True,
        published_date=datetime.now()
    )
    print(f"   ✓ Created article: {article2.title}")

    article3 = Article.objects.create(
        title="Future of AI",
        content="The future of artificial intelligence...",
        author=author2,
        is_published=False
    )
    print(f"   ✓ Created article: {article3.title}")

    return article1.id, article3.id


async def demonstrate_mcp_tools():
    """Demonstrate MCP tool functionality."""
    print("=" * 60)
    print("Django Admin MCP - Quick Start Demo")
    print("=" * 60)

    # Show registered models
    print("\n1. Registered Models")
    print("-" * 60)
    registered = get_registered_models()
    for model_name, info in registered.items():
        print(f"   ✓ {model_name}: {info['model'].__name__}")

    # Create sample data
    print("\n2. Creating Sample Data")
    print("-" * 60)

    article1_id, article3_id = await sync_to_async(create_sample_data)()

    # Demonstrate MCP tool calls
    print("\n3. MCP Tool Demonstrations")
    print("-" * 60)

    # List authors
    print("\n   a) List Authors (using MCP tool)")
    result = await MCPAdminMixin.handle_tool_call('list_author', {'limit': 10})
    print(f"      {result[0].text}")

    # Get specific article
    print("\n   b) Get Article by ID (using MCP tool)")
    result = await MCPAdminMixin.handle_tool_call('get_article', {'id': article1_id})
    print(f"      {result[0].text}")

    # Update article
    print("\n   c) Update Article (using MCP tool)")
    result = await MCPAdminMixin.handle_tool_call('update_article', {
        'id': article3_id,
        'data': {'is_published': True}
    })
    print(f"      {result[0].text}")

    # List published articles
    print("\n   d) List All Articles (using MCP tool)")
    result = await MCPAdminMixin.handle_tool_call('list_article', {'limit': 10})
    print(f"      {result[0].text}")

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nTo run the MCP server:")
    print("  python manage.py run_mcp_server")
    print("\nAvailable MCP tools:")
    for model_name in registered.keys():
        print(f"  - list_{model_name}")
        print(f"  - get_{model_name}")
        print(f"  - create_{model_name}")
        print(f"  - update_{model_name}")
        print(f"  - delete_{model_name}")
    print()


if __name__ == '__main__':
    asyncio.run(demonstrate_mcp_tools())
