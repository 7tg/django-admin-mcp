"""
Test models for testing django-admin-mcp
"""

from django.db import models


class Author(models.Model):
    """Test Author model."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)

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


class CatalogItem(models.Model):
    """Concrete model shared by channel proxy admins."""

    title = models.CharField(max_length=200)
    channel = models.CharField(max_length=1)

    class Meta:
        app_label = "tests"

    def __str__(self):
        return self.title


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
