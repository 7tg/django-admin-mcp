"""Seed a deterministic MCP token, its user and sample data.

Used by the Docker image so that an MCP client (or Glama's introspection)
can reach the server with a token known in advance:

    python manage.py seed_mcp_token --token mcp_<key>.<secret>

Idempotent: re-running updates the token's secret and grants in place.
"""

from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError

from blog.models import Article, Author
from django_admin_mcp.models import MCPToken


class Command(BaseCommand):
    help = "Create a superuser, an MCP token with a known value and sample blog data"

    def add_arguments(self, parser):
        parser.add_argument("--token", required=True, help="Full token value, mcp_<key>.<secret>")
        parser.add_argument("--username", default="mcp", help="User the token is linked to (default: mcp)")
        parser.add_argument("--no-sample-data", action="store_true", help="Skip creating authors and articles")

    def handle(self, *args, **options):
        parsed = MCPToken.parse_token(options["token"])
        if not parsed:
            raise CommandError("--token must look like mcp_<key>.<secret>")
        key, secret = parsed
        if len(key) > MCPToken._meta.get_field("token_key").max_length:
            raise CommandError("token key part is too long (max 16 characters)")

        user = self._ensure_user(options["username"])
        token = self._ensure_token(user, key, secret)
        self.stdout.write(self.style.SUCCESS(f"MCP token ready: {token} (user: {user.username})"))

        if not options["no_sample_data"]:
            self._ensure_sample_data()
            self.stdout.write(self.style.SUCCESS("Sample data ready"))

    def _ensure_user(self, username):
        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True, "is_active": True},
        )
        if created:
            # No password: this user only caps the token, it never logs in.
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user

    def _ensure_token(self, user, key, secret):
        # Set the key and hash ourselves so save() does not generate a random one.
        salt = key[:32]
        token, _ = MCPToken.objects.update_or_create(
            token_key=key,
            defaults={
                "name": "Seeded token",
                "user": user,
                "salt": salt,
                "token_hash": MCPToken._hash_token(secret, salt),
                "is_active": True,
                "expires_at": None,
            },
        )
        # The token can only exercise what it is granted, capped by the user.
        token.permissions.set(Permission.objects.all())
        return token

    def _ensure_sample_data(self):
        jane, _ = Author.objects.get_or_create(
            email="jane@example.com", defaults={"name": "Jane Doe", "bio": "Technology writer and blogger"}
        )
        john, _ = Author.objects.get_or_create(
            email="john@example.com", defaults={"name": "John Smith", "bio": "Science fiction author"}
        )
        now = datetime.now(tz=timezone.utc)
        Article.objects.get_or_create(
            title="Getting Started with Django",
            defaults={
                "content": "Django is a high-level Python web framework...",
                "author": jane,
                "is_published": True,
                "published_date": now,
            },
        )
        Article.objects.get_or_create(
            title="Introduction to MCP",
            defaults={
                "content": "The Model Context Protocol lets agents call tools...",
                "author": jane,
                "is_published": True,
                "published_date": now,
            },
        )
        Article.objects.get_or_create(
            title="Draft: Space Opera",
            defaults={"content": "Work in progress.", "author": john, "is_published": False},
        )
