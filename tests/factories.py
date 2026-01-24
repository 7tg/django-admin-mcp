"""
Factory Boy factories for django-admin-mcp tests.
"""

import factory
from django.contrib.auth import get_user_model

from django_admin_mcp.models import MCPToken

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for creating test users."""

    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")


class MCPTokenFactory(factory.django.DjangoModelFactory):
    """Factory for creating test MCP tokens."""

    class Meta:
        model = MCPToken

    name = factory.Sequence(lambda n: f"Token {n}")
    user = factory.SubFactory(UserFactory)
