"""
URL configuration for tests
"""

from django.urls import include, path

urlpatterns = [
    path("api/", include("django_admin_mcp.urls")),
]
