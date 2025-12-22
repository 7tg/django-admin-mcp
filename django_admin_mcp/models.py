"""
Models for django-admin-mcp authentication
"""

import secrets
from django.db import models
from django.utils import timezone


class MCPToken(models.Model):
    """
    Authentication token for MCP HTTP interface.
    
    Each token provides access to specific MCP tools and can be enabled/disabled.
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
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this token was used"
    )
    
    class Meta:
        verbose_name = "MCP Token"
        verbose_name_plural = "MCP Tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.token[:8]}...)"
    
    def save(self, *args, **kwargs):
        """Generate token on first save."""
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)
    
    def mark_used(self):
        """Mark token as recently used."""
        self.last_used_at = timezone.now()
        self.save(update_fields=['last_used_at'])
