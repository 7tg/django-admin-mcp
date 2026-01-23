"""
URL configuration for example_project.
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('django_admin_mcp.urls')),
]
