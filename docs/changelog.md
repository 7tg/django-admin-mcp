# Changelog

All notable changes to Django Admin MCP are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- URL path duplication when mounting at custom path (e.g., `path("mcp/", ...)` produced `/mcp/mcp/` instead of `/mcp/`) ([#68](https://github.com/7tg/django-admin-mcp/issues/68))

### Added
- Comprehensive MkDocs Material documentation
- Getting started guides
- Tool reference documentation
- Example conversations and use cases

## [0.1.0] - 2024-01-15

### Added
- Initial release
- `MCPAdminMixin` for exposing Django admin models
- Token-based authentication with `MCPToken` model
- CRUD operations: `list_*`, `get_*`, `create_*`, `update_*`, `delete_*`
- Model introspection: `describe_*`, `find_models`
- Admin actions: `actions_*`, `action_*`, `bulk_*`
- Relationships: `related_*`, `history_*`, `autocomplete_*`
- Full Django admin permission integration
- Support for Django 3.2, 4.0, 4.1, 4.2, 5.0
- Support for Python 3.10, 3.11, 3.12

### Security
- Bearer token authentication
- Token expiration (default 90 days)
- Django permission checking on all operations
- Principle of least privilege (tokens start with no permissions)

---

## Version History

| Version | Release Date | Python | Django |
|---------|--------------|--------|--------|
| 0.1.0 | 2024-01-15 | 3.10+ | 3.2+ |

---

## Upgrade Guide

### From Pre-release to 0.1.0

If you were using a pre-release version:

1. Update the package:
   ```bash
   pip install --upgrade django-admin-mcp
   ```

2. Run migrations:
   ```bash
   python manage.py migrate django_admin_mcp
   ```

3. Recreate any tokens (token format may have changed)

---

## Deprecation Policy

- Features are deprecated for at least one minor version before removal
- Deprecated features will emit warnings
- Migration guides are provided for breaking changes
