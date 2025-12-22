"""
URL patterns for django-admin-mcp HTTP interface
"""

from django.urls import path

from django_admin_mcp import views

app_name = "django_admin_mcp"

urlpatterns = [
    path("mcp/", views.mcp_endpoint, name="mcp_endpoint"),
    path("health/", views.mcp_health, name="health"),
]
