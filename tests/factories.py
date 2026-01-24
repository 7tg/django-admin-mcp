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
    def capture_plaintext(obj, create, extracted, **kwargs):
        """Capture plaintext token as an attribute for tests.

        The plaintext token is only available immediately after creation,
        so we capture it here for use in tests.
        """
        if create:
            # The token is automatically generated and hashed on save
            # Get the plaintext token before it's cleared
            plaintext = obj.get_plaintext_token()
            if plaintext:
                # Store it as a test attribute so tests can use it
                obj.plaintext_token = plaintext
            else:
                # Fallback for legacy tokens (migration compatibility)
                obj.plaintext_token = obj.token if obj.token else None
