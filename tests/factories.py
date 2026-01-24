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

    @factory.post_generation
    def get_plaintext_token(obj, create, extracted, **kwargs):
        """Store plaintext token as an attribute for tests."""
        if create:
            # The token is automatically generated and hashed on save
            # Get the plaintext token if available
            plaintext = obj.get_plaintext_token()
            if plaintext:
                # Store it as a test attribute so tests can use it
                obj.plaintext_token = plaintext
            else:
                # Fallback for legacy tokens
                obj.plaintext_token = obj.token if obj.token else None
