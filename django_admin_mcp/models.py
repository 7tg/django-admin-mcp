"""
Models for django-admin-mcp authentication
"""

import secrets
from datetime import timedelta
from django.db import models
from django.utils import timezone


class MCPToken(models.Model):
    """
    Authentication token for MCP HTTP interface.
    
    Each token provides access to specific MCP tools and can be enabled/disabled.
    Tokens can have an expiry date or be indefinite (expires_at=None).
    """
    name = models.CharField(
        max_length=200,
        help_text="A descriptive name for this token (e.g., 'Production API', 'Dev Testing')"
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="The authentication token (auto-generated)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this token is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Token expiration date (leave empty for indefinite tokens)"
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this token was used"
    )
    
    # Sentinel to track if expires_at was explicitly set
    _EXPIRES_AT_NOT_SET = object()
    
    class Meta:
        verbose_name = "MCP Token"
        verbose_name_plural = "MCP Tokens"
        ordering = ['-created_at']
    
    def __init__(self, *args, **kwargs):
        """Track if expires_at is explicitly set."""
        # Check if expires_at is in kwargs before calling super
        self._expires_at_explicit = 'expires_at' in kwargs
        super().__init__(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.token[:8]}...)"
    
    def save(self, *args, **kwargs):
        """Generate token and set default expiry on first save."""
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        
        # Set default expiry to 90 days only for new tokens where expires_at wasn't explicitly set
        if self.pk is None and not self._expires_at_explicit and self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(days=90)
        
        super().save(*args, **kwargs)
    
    def mark_used(self):
        """Mark token as recently used."""
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])
    
    def is_expired(self):
        """Check if token has expired."""
        if self.expires_at is None:
            return False  # Indefinite tokens never expire
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        """Check if token is valid (active and not expired)."""
        return self.is_active and not self.is_expired()
