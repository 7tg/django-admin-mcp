"""
Test models for testing django-admin-mcp
"""

import uuid

from django.db import models


class Author(models.Model):
    """Test Author model."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)
    attachment = models.FileField(upload_to="attachments/", blank=True)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.name


class Article(models.Model):
    """Test Article model."""

    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="articles")
    published_date = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.title


class Gadget(models.Model):
    """Test model with a sensitive-looking field and nullable relations."""

    title = models.CharField(max_length=1000)
    api_key = models.CharField(max_length=100, blank=True)
    owner = models.ForeignKey(
        Author,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gadgets",
    )
    twin = models.OneToOneField(
        Author,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="twin_gadget",
    )

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.title


class TicketStatus(models.IntegerChoices):
    DRAFT = 1, "Draft"
    ACTIVE = 2, "Active"
    CLOSED = 3, "Closed"


class TicketPriority(models.TextChoices):
    LOW = "low", "Low priority"
    HIGH = "high", "High priority"


class Ticket(models.Model):
    """Test model covering every flavor of choice field (issue #113)."""

    title = models.CharField(max_length=200)
    status = models.IntegerField(choices=TicketStatus.choices, default=TicketStatus.DRAFT)
    priority = models.CharField(max_length=10, choices=TicketPriority.choices, default=TicketPriority.LOW)
    size = models.CharField(max_length=1, choices=[("s", "Small"), ("m", "Medium")], blank=True)
    media = models.CharField(
        max_length=10,
        choices=[("Audio", [("cd", "CD"), ("vinyl", "Vinyl")]), ("unknown", "Unknown")],
        blank=True,
    )
    severity = models.IntegerField(choices=[(1, "Minor"), (2, "Major")], null=True, blank=True)
    # Collision pair: a choice field whose natural sidecar name is taken by a real field
    state = models.IntegerField(choices=[(1, "Open"), (2, "Done")], null=True, blank=True)
    state_display = models.CharField(max_length=20, blank=True)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.title


class CatalogItem(models.Model):
    """Concrete model shared by channel proxy admins."""

    title = models.CharField(max_length=200)
    channel = models.CharField(max_length=1)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.title


class Product(models.Model):
    """Test model with non-editable fields and admin-computed values (issue #117)."""

    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    stock = models.IntegerField(default=0)
    owner = models.ForeignKey(Author, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    internal_code = models.CharField(max_length=50, editable=False, default="")
    stage = models.CharField(max_length=10, choices=[("new", "New"), ("live", "Live")], default="new", editable=False)
    manual = models.FileField(upload_to="manuals/", blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.name

    @property
    def label(self):
        return f"{self.name} ({self.stage})"


class CatalogItemA(CatalogItem):
    """Proxy for channel A rows (admin-scoped via get_queryset)."""

    class Meta:
        proxy = True
        app_label = "tests"


class CatalogItemB(CatalogItem):
    """Proxy for channel B rows (admin-scoped via get_queryset)."""

    class Meta:
        proxy = True
        app_label = "tests"
