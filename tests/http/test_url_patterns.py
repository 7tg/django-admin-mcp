"""
Tests for URL pattern configuration.

Verifies that django_admin_mcp.urls does not include a prefix,
allowing users to control the mount point entirely.
See: https://github.com/7tg/django-admin-mcp/issues/68
"""

from django.urls import resolve, reverse


class TestURLPatterns:
    """Test that URL patterns follow Django conventions."""

    def test_mcp_endpoint_no_path_duplication(self):
        """URLs should not duplicate path when mounted at a custom prefix.

        When mounting at path("mcp/", include("django_admin_mcp.urls")),
        the endpoint should be at /mcp/, not /mcp/mcp/.
        """
        url = reverse("django_admin_mcp:mcp_endpoint")
        # tests/urls.py mounts at "api/", so the URL should be /api/
        # not /api/mcp/ (which would indicate an internal mcp/ prefix)
        assert url == "/api/"

    def test_health_endpoint_path(self):
        """Health endpoint should be at mount_point/health/."""
        url = reverse("django_admin_mcp:health")
        assert url == "/api/health/"

    def test_mcp_endpoint_resolves(self):
        """The MCP endpoint should resolve at the mount point root."""
        match = resolve("/api/")
        assert match.url_name == "mcp_endpoint"
        assert match.namespace == "django_admin_mcp"

    def test_health_endpoint_resolves(self):
        """The health endpoint should resolve at mount_point/health/."""
        match = resolve("/api/health/")
        assert match.url_name == "health"
        assert match.namespace == "django_admin_mcp"
