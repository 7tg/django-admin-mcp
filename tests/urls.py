"""
URL configuration for tests
"""
from django.urls import path, include

urlpatterns = [
    path('api/', include('django_admin_mcp.urls')),
]
