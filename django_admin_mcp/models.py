"""
Models for django-admin-mcp authentication
"""

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import models
from django.utils import timezone


class MCPToken(models.Model):
    """
    Authentication token for MCP HTTP interface.

    Each token provides access to specific MCP tools and can be enabled/disabled.
    Tokens can have an expiry date or be indefinite (expires_at=None).

    Permissions are managed through direct permissions and groups assigned to the token,
    NOT inherited from the linked user. The user field is used only for audit logging
    (actions taken via this token are logged under the user in Django admin history).
    """

    name = models.CharField(
        max_length=200,
        help_text="A descriptive name for this token (e.g., 'Production API', 'Dev Testing')",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        null=True,
        blank=True,
        help_text="DEPRECATED: Token is now hashed. This field will be removed in future versions.",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        null=True,
        blank=True,
        help_text="SHA-256 hash of the authentication token",
    )
    salt = models.CharField(
        max_length=32,
        editable=False,
        null=True,
        blank=True,
        help_text="Salt used for token hashing",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_tokens",
        help_text="User for audit logging (actions are logged under this user)",
    )
    is_active = models.BooleanField(default=True, help_text="Whether this token is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Token expiration date (leave empty for indefinite tokens)",
    )
    last_used_at = models.DateTimeField(null=True, blank=True, help_text="Last time this token was used")
    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="mcp_tokens",
        help_text="Groups this token belongs to for permission management",
    )
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="mcp_tokens",
        help_text="Specific permissions granted to this token",
    )

    class Meta:
        verbose_name = "MCP Token"
        verbose_name_plural = "MCP Tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "token_hash"], name="mcp_token_active_hash_idx"),
        ]

    def __init__(self, *args, **kwargs):
        """Track if expires_at is explicitly set."""
        # Check if expires_at is in kwargs before calling super
        self._expires_at_explicit = "expires_at" in kwargs
        # Store the plaintext token temporarily for return after save
        self._plaintext_token = None
        super().__init__(*args, **kwargs)

    def __str__(self):
        # Use first 8 chars of hash for display since token is hashed
        if self.token_hash:
            return f"{self.name} ({self.token_hash[:8]}...)"
        elif self.token:
            # Legacy: still showing token for backward compatibility
            return f"{self.name} ({self.token[:8]}...)"
        return f"{self.name}"

    def save(self, *args, **kwargs):
        """Generate token, hash it with salt, and set default expiry on first save."""
        if not self.token_hash:
            # Generate a new token
            plaintext_token = secrets.token_urlsafe(48)

            # Generate a unique salt for this token
            self.salt = secrets.token_urlsafe(16)

            # Hash the token with the salt
            self.token_hash = self._hash_token(plaintext_token, self.salt)

            # Store plaintext token temporarily so it can be returned to user once
            self._plaintext_token = plaintext_token

            # Clear the legacy token field (don't store plaintext)
            self.token = None

        # Set default expiry to 90 days only for new tokens where expires_at wasn't explicitly set
        if self._should_set_default_expiry():
            self.expires_at = timezone.now() + timedelta(days=90)

        super().save(*args, **kwargs)

    @staticmethod
    def _hash_token(token: str, salt: str) -> str:
        """
        Hash a token using SHA-256 with salt.

        Args:
            token: The plaintext token
            salt: The salt to use for hashing

        Returns:
            Hexadecimal hash string
        """
        # Combine salt and token, then hash
        salted_token = f"{salt}{token}".encode()
        return hashlib.sha256(salted_token).hexdigest()

    def verify_token(self, provided_token: str) -> bool:
        """
        Verify a provided token against the stored hash using constant-time comparison.

        Args:
            provided_token: The plaintext token to verify

        Returns:
            True if token matches, False otherwise
        """
        if not self.token_hash or not self.salt:
            # Legacy: fallback to plaintext comparison if hash not available
            if self.token:
                return hmac.compare_digest(self.token, provided_token)
            return False

        # Hash the provided token with the stored salt
        provided_hash = self._hash_token(provided_token, self.salt)

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(self.token_hash, provided_hash)

    def _should_set_default_expiry(self):
        """Check if default expiry should be set for new token."""
        return self.pk is None and not self._expires_at_explicit and self.expires_at is None

    def get_plaintext_token(self) -> str | None:
        """
        Get the plaintext token. Only available immediately after creation.

        Returns:
            The plaintext token if available, None otherwise.

        Note:
            This should only be called once after token creation to display to the user.
            After that, the plaintext token is lost forever (by design).
        """
        token = self._plaintext_token
        # Clear the token after first retrieval for security
        self._plaintext_token = None
        return token

    def mark_used(self):
        """Mark token as recently used."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    def is_expired(self):
        """Check if token has expired."""
        if self.expires_at is None:
            return False  # Indefinite tokens never expire
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if token is valid (active and not expired)."""
        return self.is_active and not self.is_expired()

    def has_perm(self, perm):
        """
        Check if token has a specific permission.

        Args:
            perm: Permission string in format 'app_label.codename' (e.g., 'blog.change_article')
                  or Permission object

        Returns:
            bool: True if token has permission, False otherwise
        """
        # Parse permission if it's a string
        if isinstance(perm, str):
            if "." in perm:
                app_label, codename = perm.split(".", 1)
            else:
                # If no app_label, we can't check it
                return False
        else:
            app_label = perm.content_type.app_label
            codename = perm.codename

        # Check direct permissions
        if self.permissions.filter(content_type__app_label=app_label, codename=codename).exists():
            return True

        # Check group permissions
        if self.groups.filter(
            permissions__content_type__app_label=app_label,
            permissions__codename=codename,
        ).exists():
            return True

        # Default: deny access (principle of least privilege)
        return False

    def has_perms(self, perm_list):
        """
        Check if token has all permissions in the list.

        Args:
            perm_list: List of permission strings

        Returns:
            bool: True if token has all permissions, False otherwise
        """
        return all(self.has_perm(perm) for perm in perm_list)

    def get_all_permissions(self):
        """
        Get all permissions available to this token.

        Returns:
            set: Set of permission strings in 'app_label.codename' format
        """
        perms = set()

        # Add direct permissions
        for perm in self.permissions.select_related("content_type").all():
            perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        # Add group permissions
        for group in self.groups.prefetch_related("permissions__content_type").all():
            for perm in group.permissions.all():
                perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        return perms
